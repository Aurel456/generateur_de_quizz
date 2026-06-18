"""Génération de quiz QCM (réutilise generation.quiz_generator).

Deux variantes par opération longue :
- synchrone (`/generate`, `/verify`) : conservée pour la compatibilité et les usages simples ;
- asynchrone (`/generate-async`, `/verify-async`) : renvoie un `job_id`, exécute en tâche
  de fond avec progression + items au fil de l'eau (cf. backend/app/jobs.py et api/jobs.py).
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import (
    dict_to_notion,
    dict_to_question,
    question_to_dict,
    quiz_from_questions,
)
from backend.app.doc_store import DocEntry, doc_store
from backend.app.jobs import Job, job_store
from backend.app.schemas import (
    GenerateQuizFromKnowledgeRequest,
    GenerateQuizRequest,
    ImproveQuestionRequest,
    JobCreatedResponse,
    QuizQuestionDTO,
    QuizResponse,
    VerificationResult,
    VerifyQuizRequest,
    VerifyQuizResponse,
)
from core.llm_service import VISION_MODEL_NAME
from generation.chat_mode import generate_quiz_from_llm_knowledge
from generation.instruction_classifier import classify_user_input
from generation.question_editor import improve_question_with_llm
from generation.quiz_generator import generate_quiz
from generation.quiz_verifier import verify_quiz

router = APIRouter(prefix="/quiz", tags=["quiz"])
log = logging.getLogger(__name__)
_VISION_MODEL = VISION_MODEL_NAME or None


def _resolve_doc(doc_id: str) -> DocEntry:
    entry = doc_store.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")
    return entry


def _resolve_counts(difficulty_counts: dict[str, int]) -> dict[str, int]:
    counts = {k: v for k, v in difficulty_counts.items() if v > 0}
    if not counts:
        raise HTTPException(status_code=400, detail="Indiquez au moins une question à générer.")
    return counts


def _split_instructions(payload, *, job: Job | None = None) -> tuple[str, str]:
    """Sépare la consigne libre en (style, périmètre) si la classification est demandée.

    - périmètre → `user_context` (filtrage des chunks pertinents en amont),
    - style → `user_instructions` (injecté dans le prompt de génération).
    Sinon, la consigne entière sert de style et le périmètre est vide.
    """
    text = (payload.user_instructions or "").strip()
    if not text or not getattr(payload, "classify_instructions", False):
        return text, ""
    gen_instr, chunk_instr = classify_user_input(text)
    if job is not None and chunk_instr:
        job.set_message(f"Périmètre documentaire détecté : {chunk_instr[:120]}")
    return gen_instr, chunk_instr


def _quiz_to_response(quiz) -> QuizResponse:
    return QuizResponse(
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=[QuizQuestionDTO(**question_to_dict(q)) for q in quiz.questions],
    )


def _run_generation(
    entry: DocEntry,
    payload: GenerateQuizRequest,
    counts: dict[str, int],
    *,
    progress_callback=None,
    on_item=None,
    job: Job | None = None,
) -> QuizResponse:
    """Cœur de la génération, partagé par les variantes sync et async."""
    # Seules les notions activées guident la génération.
    notions = [dict_to_notion(n.model_dump()) for n in payload.notions if n.enabled]
    model = _VISION_MODEL if entry.vision else None
    # Streaming incrémental possible hors mode batch (le batch agrège les résultats).
    stream = on_item is not None and not payload.batch_mode
    user_instructions, user_context = _split_instructions(payload, job=job)

    quiz = generate_quiz(
        entry.chunks,
        difficulty_counts=counts,
        num_choices=payload.num_choices,
        num_correct=payload.num_correct,
        variable_correct=payload.variable_correct,
        max_correct=payload.max_correct if payload.variable_correct else None,
        vrai_faux=payload.vrai_faux,
        humor=payload.humor,
        persona=payload.persona,
        user_instructions=user_instructions,
        user_context=user_context,
        difficulty_prompts=payload.difficulty_prompts or None,
        notions=notions or None,
        vision_mode=entry.vision,
        batch_mode=payload.batch_mode,
        model=model,
        progress_callback=progress_callback,
        stream=stream,
        on_item=on_item if stream else None,
    )
    return _quiz_to_response(quiz)


@router.post("/generate", response_model=QuizResponse)
def generate(payload: GenerateQuizRequest) -> QuizResponse:
    entry = _resolve_doc(payload.doc_id)
    counts = _resolve_counts(payload.difficulty_counts)
    try:
        return _run_generation(entry, payload, counts)
    except Exception:
        log.exception("Échec génération du quiz")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération du quiz.")


@router.post("/generate-async", response_model=JobCreatedResponse)
def generate_async(payload: GenerateQuizRequest) -> JobCreatedResponse:
    """Lance la génération en tâche de fond ; suivre via GET /jobs/{job_id}."""
    entry = _resolve_doc(payload.doc_id)  # validation immédiate (404/400 si invalide)
    counts = _resolve_counts(payload.difficulty_counts)

    def task(job: Job) -> dict:
        response = _run_generation(
            entry,
            payload,
            counts,
            progress_callback=job.progress,
            on_item=lambda q: job.add_item(question_to_dict(q)),
            job=job,
        )
        return response.model_dump()

    return JobCreatedResponse(job_id=job_store.submit("quiz", task))


@router.post("/improve-question", response_model=QuizQuestionDTO)
def improve_question(payload: ImproveQuestionRequest) -> QuizQuestionDTO:
    """Améliore une question via une instruction en langage naturel (LLM)."""
    question = dict_to_question(payload.question.model_dump())
    try:
        improved = improve_question_with_llm(question, payload.instruction)
    except Exception:
        log.exception("Échec amélioration de la question")
        raise HTTPException(status_code=502, detail="Erreur lors de l'amélioration de la question.")
    return QuizQuestionDTO(**question_to_dict(improved))


def _run_verification(
    entry: DocEntry,
    payload: VerifyQuizRequest,
    *,
    progress_callback=None,
) -> VerifyQuizResponse:
    quiz = quiz_from_questions([q.model_dump() for q in payload.questions])
    cleaned, results = verify_quiz(quiz, entry.chunks, progress_callback=progress_callback)
    return VerifyQuizResponse(
        questions=[QuizQuestionDTO(**question_to_dict(q)) for q in cleaned.questions],
        results=[
            VerificationResult(question_index=r.question_index, status=r.status) for r in results
        ],
    )


@router.post("/verify", response_model=VerifyQuizResponse)
def verify(payload: VerifyQuizRequest) -> VerifyQuizResponse:
    """Vérifie les questions contre le document source (reformulation/suppression auto)."""
    entry = _resolve_doc(payload.doc_id)
    try:
        return _run_verification(entry, payload)
    except Exception:
        log.exception("Échec vérification du quiz")
        raise HTTPException(status_code=502, detail="Erreur lors de la vérification du quiz.")


@router.post("/verify-async", response_model=JobCreatedResponse)
def verify_async(payload: VerifyQuizRequest) -> JobCreatedResponse:
    entry = _resolve_doc(payload.doc_id)

    def task(job: Job) -> dict:
        return _run_verification(entry, payload, progress_callback=job.progress).model_dump()

    return JobCreatedResponse(job_id=job_store.submit("verify", task))


# ── Quiz sans document (base de connaissance du LLM) ──────────────────────────
def _run_knowledge_generation(
    payload: GenerateQuizFromKnowledgeRequest,
    counts: dict[str, int],
    *,
    progress_callback=None,
) -> QuizResponse:
    notions = [dict_to_notion(n.model_dump()) for n in payload.notions if n.enabled]
    quiz = generate_quiz_from_llm_knowledge(
        topic=payload.topic,
        notions=notions or None,
        additional_context=payload.additional_context,
        difficulty_counts=counts,
        num_choices=payload.num_choices,
        num_correct=payload.num_correct,
        variable_correct=payload.variable_correct,
        max_correct=payload.max_correct if payload.variable_correct else None,
        vrai_faux=payload.vrai_faux,
        batch_mode=payload.batch_mode,
        progress_callback=progress_callback,
    )
    return _quiz_to_response(quiz)


@router.post("/generate-from-knowledge", response_model=QuizResponse)
def generate_from_knowledge(payload: GenerateQuizFromKnowledgeRequest) -> QuizResponse:
    """Génère un quiz à partir de la base de connaissance du LLM, sans document source."""
    counts = _resolve_counts(payload.difficulty_counts)
    try:
        return _run_knowledge_generation(payload, counts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        log.exception("Échec génération quiz (base LLM)")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération du quiz.")


@router.post("/generate-from-knowledge-async", response_model=JobCreatedResponse)
def generate_from_knowledge_async(payload: GenerateQuizFromKnowledgeRequest) -> JobCreatedResponse:
    counts = _resolve_counts(payload.difficulty_counts)

    def task(job: Job) -> dict:
        return _run_knowledge_generation(payload, counts, progress_callback=job.progress).model_dump()

    return JobCreatedResponse(job_id=job_store.submit("quiz", task))
