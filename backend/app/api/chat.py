"""Mode libre : génération par conversation (réutilise generation.chat_mode).

L'état conversationnel (ChatSession) vit dans `chat_store`, indexé par `chat_id`.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.chat_store import chat_store
from backend.app.converters import notion_to_dict, question_to_dict
from backend.app.schemas import (
    ChatGenerateRequest,
    ChatMessageRequest,
    ChatResponse,
    NotionDTO,
    QuizQuestionDTO,
    QuizResponse,
)
from generation.chat_mode import generate_quiz_direct, init_session, process_user_message

router = APIRouter(prefix="/chat", tags=["chat"])
log = logging.getLogger(__name__)


def _response(chat_id: str, message: str, session) -> ChatResponse:
    return ChatResponse(
        chat_id=chat_id,
        message=message,
        state=str(getattr(session.state, "value", session.state)),
        notions=[NotionDTO(**notion_to_dict(n)) for n in session.notions],
        suggested_config=session.suggested_config,
    )


@router.post("/start", response_model=ChatResponse)
def start() -> ChatResponse:
    message, session = init_session()
    chat_id = chat_store.put(session)
    return _response(chat_id, message, session)


@router.post("/{chat_id}/message", response_model=ChatResponse)
def message(chat_id: str, payload: ChatMessageRequest) -> ChatResponse:
    session = chat_store.get(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation inconnue ou expirée.")
    try:
        reply, session = process_user_message(session, payload.message)
    except Exception:
        log.exception("Échec traitement message chat")
        raise HTTPException(status_code=502, detail="Erreur lors du traitement du message.")
    chat_store.put(session, chat_id)
    return _response(chat_id, reply, session)


@router.post("/{chat_id}/generate-quiz", response_model=QuizResponse)
def generate_quiz_from_chat(chat_id: str, payload: ChatGenerateRequest) -> QuizResponse:
    session = chat_store.get(chat_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation inconnue ou expirée.")

    counts = {k: v for k, v in payload.difficulty_counts.items() if v > 0}
    if not counts:
        raise HTTPException(status_code=400, detail="Indiquez au moins une question à générer.")

    try:
        quiz = generate_quiz_direct(
            session,
            difficulty_counts=counts,
            num_choices=payload.num_choices,
            num_correct=payload.num_correct,
            vrai_faux=payload.vrai_faux,
            variable_correct=payload.variable_correct,
        )
    except Exception:
        log.exception("Échec génération quiz (mode libre)")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération du quiz.")

    return QuizResponse(
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=[QuizQuestionDTO(**question_to_dict(q)) for q in quiz.questions],
    )
