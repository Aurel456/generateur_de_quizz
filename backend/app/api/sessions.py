"""Sessions de quiz partagées + flux participant (réutilise sessions.session_store).

Le scoring reste CÔTÉ SERVEUR : les bonnes réponses ne sont jamais envoyées au
participant avant sa soumission.
"""
import json
import logging

from fastapi import APIRouter, HTTPException

from backend.app.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    ParticipantChoice,
    ParticipantSessionResponse,
    QuestionCorrection,
    SubmitAnswersRequest,
    SubmitAnswersResponse,
)
from sessions.analytics_core import generate_ai_recommendations
from sessions.session_store import (
    create_session,
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
    try:
        session = create_session(quiz_data, notions_data, payload.title)
    except Exception:
        log.exception("Échec création de session")
        raise HTTPException(status_code=500, detail="Impossible de créer la session.")
    return CreateSessionResponse(session_code=session.session_code, title=session.title)


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
        questions=questions,
    )


@router.post("/{session_code}/submit", response_model=SubmitAnswersResponse)
def submit(session_code: str, payload: SubmitAnswersRequest) -> SubmitAnswersResponse:
    code = session_code.upper()
    result = submit_result(code, payload.participant_name, payload.answers)
    if result is None:
        raise HTTPException(status_code=404, detail="Session introuvable ou fermée.")

    session = get_session(code)
    per_question = json.loads(result.per_question_json)
    corrections = [
        QuestionCorrection(
            index=i,
            is_correct=bool(per_question.get(str(i), False)),
            correct_answers=q.get("correct_answers", []),
            explanation=q.get("explanation", ""),
            citation=q.get("citation", ""),
        )
        for i, q in enumerate(_session_questions(session))
    ]
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
