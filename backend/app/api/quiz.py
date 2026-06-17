"""Génération de quiz QCM (réutilise generation.quiz_generator)."""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import (
    dict_to_notion,
    dict_to_question,
    question_to_dict,
    quiz_from_questions,
)
from backend.app.doc_store import doc_store
from backend.app.schemas import (
    GenerateQuizRequest,
    ImproveQuestionRequest,
    QuizQuestionDTO,
    QuizResponse,
    VerificationResult,
    VerifyQuizRequest,
    VerifyQuizResponse,
)
from core.llm_service import VISION_MODEL_NAME
from generation.question_editor import improve_question_with_llm
from generation.quiz_generator import generate_quiz
from generation.quiz_verifier import verify_quiz

router = APIRouter(prefix="/quiz", tags=["quiz"])
log = logging.getLogger(__name__)
_VISION_MODEL = VISION_MODEL_NAME or None


@router.post("/generate", response_model=QuizResponse)
def generate(payload: GenerateQuizRequest) -> QuizResponse:
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    counts = {k: v for k, v in payload.difficulty_counts.items() if v > 0}
    if not counts:
        raise HTTPException(status_code=400, detail="Indiquez au moins une question à générer.")

    # Seules les notions activées guident la génération.
    notions = [dict_to_notion(n.model_dump()) for n in payload.notions if n.enabled]
    model = _VISION_MODEL if entry.vision else None

    try:
        quiz = generate_quiz(
            entry.chunks,
            difficulty_counts=counts,
            num_choices=payload.num_choices,
            num_correct=payload.num_correct,
            variable_correct=payload.variable_correct,
            vrai_faux=payload.vrai_faux,
            humor=payload.humor,
            persona=payload.persona,
            user_instructions=payload.user_instructions,
            notions=notions or None,
            vision_mode=entry.vision,
            batch_mode=payload.batch_mode,
            model=model,
        )
    except Exception:
        log.exception("Échec génération du quiz")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération du quiz.")

    return QuizResponse(
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=[QuizQuestionDTO(**question_to_dict(q)) for q in quiz.questions],
    )


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


@router.post("/verify", response_model=VerifyQuizResponse)
def verify(payload: VerifyQuizRequest) -> VerifyQuizResponse:
    """Vérifie les questions contre le document source (reformulation/suppression auto)."""
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    quiz = quiz_from_questions([q.model_dump() for q in payload.questions])
    try:
        cleaned, results = verify_quiz(quiz, entry.chunks)
    except Exception:
        log.exception("Échec vérification du quiz")
        raise HTTPException(status_code=502, detail="Erreur lors de la vérification du quiz.")

    return VerifyQuizResponse(
        questions=[QuizQuestionDTO(**question_to_dict(q)) for q in cleaned.questions],
        results=[
            VerificationResult(question_index=r.question_index, status=r.status) for r in results
        ],
    )
