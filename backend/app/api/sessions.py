"""Sessions de quiz partagées + flux participant (réutilise sessions.session_store).

Le scoring reste CÔTÉ SERVEUR : les bonnes réponses ne sont jamais envoyées au
participant avant sa soumission.
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from fastapi import Query

from backend.app.schemas import (
    CreatePoolSessionRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    ParticipantChoice,
    ParticipantSessionResponse,
    PoolSubsetResponse,
    QuestionCorrection,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
)
from sessions.analytics_core import generate_ai_recommendations
from sessions.session_store import (
    create_pool_session,
    create_session,
    deactivate_session,
    get_next_subset,
    get_session,
    get_session_analytics,
    submit_result,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger(__name__)


def _session_questions(session) -> list[dict]:
    try:
        return json.loads(session.quiz_json).get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        return []


@router.post("", response_model=CreateSessionResponse)
def create(payload: CreateSessionRequest) -> CreateSessionResponse:
    quiz_data = {"title": payload.title, "questions": [q.model_dump() for q in payload.questions]}
    notions_data = [n.model_dump() for n in payload.notions]
    exercises_data = [e.model_dump() for e in payload.exercises]
    try:
        session = create_session(quiz_data, notions_data, payload.title, exercises_data=exercises_data)
    except Exception:
        log.exception("Échec création de session")
        raise HTTPException(status_code=500, detail="Impossible de créer la session.")
    return CreateSessionResponse(session_code=session.session_code, title=session.title)


@router.post("/create-pool", response_model=CreateSessionResponse)
def create_pool(payload: CreatePoolSessionRequest) -> CreateSessionResponse:
    """Crée une session pool : chaque participant tire `subset_size` questions du pool."""
    if payload.subset_size > len(payload.questions):
        raise HTTPException(
            status_code=400,
            detail="La taille du sous-ensemble dépasse le nombre de questions du pool.",
        )
    pool_quiz_data = {"title": payload.title, "questions": [q.model_dump() for q in payload.questions]}
    notions_data = [n.model_dump() for n in payload.notions]
    try:
        session = create_pool_session(
            pool_quiz_data,
            notions_data,
            payload.title,
            subset_size=payload.subset_size,
            pass_threshold=payload.pass_threshold,
        )
    except Exception:
        log.exception("Échec création de session pool")
        raise HTTPException(status_code=500, detail="Impossible de créer la session pool.")
    return CreateSessionResponse(session_code=session.session_code, title=session.title)


@router.post("/{session_code}/deactivate")
def deactivate(session_code: str) -> dict:
    """Ferme une session (plus aucune soumission possible)."""
    ok = deactivate_session(session_code.upper())
    if not ok:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    return {"session_code": session_code.upper(), "is_active": False}


@router.get("/{session_code}", response_model=ParticipantSessionResponse)
def get_participant_view(session_code: str) -> ParticipantSessionResponse:
    session = get_session(session_code.upper())
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")

    questions = [
        ParticipantChoice(
            question=q.get("question", ""),
            choices=q.get("choices", {}),
            difficulty_level=q.get("difficulty_level", ""),
            related_notions=q.get("related_notions", []),
        )
        for q in _session_questions(session)
    ]
    return ParticipantSessionResponse(
        session_code=session.session_code,
        title=session.title,
        is_active=session.is_active,
        is_pool=bool(getattr(session, "pool_json", None)),
        questions=questions,
    )


@router.get("/{session_code}/subset", response_model=PoolSubsetResponse)
def get_pool_subset(
    session_code: str, participant_name: str = Query(..., min_length=1)
) -> PoolSubsetResponse:
    """Sous-ensemble (pool) servi à un participant : questions non encore vues, sans réponses."""
    code = session_code.upper()
    session = get_session(code)
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    subset = get_next_subset(code, participant_name)
    if subset is None:
        raise HTTPException(status_code=400, detail="Cette session n'est pas une session pool.")

    pool_indices = [int(q.get("_pool_index", -1)) for q in subset]
    questions = [
        ParticipantChoice(
            question=q.get("question", ""),
            choices=q.get("choices", {}),
            difficulty_level=q.get("difficulty_level", ""),
            related_notions=q.get("related_notions", []),
        )
        for q in subset
    ]
    return PoolSubsetResponse(
        session_code=code,
        title=session.title,
        is_active=session.is_active,
        pass_threshold=getattr(session, "pass_threshold", 0.7) or 0.7,
        pool_indices=pool_indices,
        questions=questions,
    )


@router.post("/{session_code}/submit", response_model=SubmitAnswersResponse)
def submit(session_code: str, payload: SubmitAnswersRequest) -> SubmitAnswersResponse:
    code = session_code.upper()
    session = get_session(code)
    if session is None:
        raise HTTPException(status_code=404, detail="Session introuvable ou fermée.")

    # Session pool : reconstruire le corrigé du sous-ensemble depuis le pool (stateless).
    override: list[dict] | None = None
    correction_questions = _session_questions(session)
    if payload.pool_indices is not None and getattr(session, "pool_json", None):
        pool_questions = json.loads(session.pool_json)
        override = []
        for idx in payload.pool_indices:
            if 0 <= idx < len(pool_questions):
                q = dict(pool_questions[idx])
                q["_pool_index"] = idx
                override.append(q)
        correction_questions = override

    result = submit_result(code, payload.participant_name, payload.answers, questions_override=override)
    if result is None:
        raise HTTPException(status_code=404, detail="Session introuvable ou fermée.")

    per_question = json.loads(result.per_question_json)
    corrections = []
    for i, q in enumerate(correction_questions):
        # submit_result indexe par _pool_index pour le pool, sinon par position.
        key = str(q["_pool_index"]) if q.get("_pool_index") is not None else str(i)
        corrections.append(
            QuestionCorrection(
                index=i,
                is_correct=bool(per_question.get(key, False)),
                correct_answers=q.get("correct_answers", []),
                explanation=q.get("explanation", ""),
                citation=q.get("citation", ""),
            )
        )
    return SubmitAnswersResponse(score=result.score, total=result.total, corrections=corrections)


@router.get("/{session_code}/analytics")
def analytics(session_code: str) -> dict:
    """Métriques agrégées d'une session (taux par question/notion, classement, global)."""
    data = get_session_analytics(session_code.upper())
    if data is None:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    return data


@router.post("/{session_code}/recommendations")
def recommendations(session_code: str) -> dict:
    """Recommandations pédagogiques générées par LLM à partir des analytics."""
    data = get_session_analytics(session_code.upper())
    if data is None:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    if not data.get("participants"):
        raise HTTPException(status_code=400, detail="Aucun résultat à analyser pour cette session.")
    try:
        return generate_ai_recommendations(data)
    except Exception:
        log.exception("Échec génération des recommandations IA")
        raise HTTPException(status_code=502, detail="Erreur lors de l'analyse IA.")
