"""Ateliers formateurs collaboratifs (réutilise sessions.session_store, work_sessions)."""
import json
import logging

from fastapi import APIRouter, HTTPException

from backend.app.schemas import (
    CreateWorkshopRequest,
    ExerciseDTO,
    NotionDTO,
    PublishWorkshopRequest,
    QuizQuestionDTO,
    UpdateWorkshopRequest,
    WorkshopResponse,
    WorkshopSummary,
)
from sessions.session_store import (
    create_work_session,
    get_work_session,
    list_work_sessions,
    publish_work_session,
    update_work_session_draft,
)

router = APIRouter(prefix="/workshops", tags=["workshops"])
log = logging.getLogger(__name__)


def _to_response(ws) -> WorkshopResponse:
    quiz = json.loads(ws.draft_quiz_json or "{}")
    questions = quiz.get("questions", []) if isinstance(quiz, dict) else (quiz or [])
    notions = json.loads(ws.draft_notions_json or "[]")
    exercises = json.loads(ws.draft_exercises_json or "[]")
    return WorkshopResponse(
        work_code=ws.work_code,
        title=ws.title,
        owner_name=ws.owner_name,
        status=ws.status,
        last_modified=ws.last_modified,
        questions=[QuizQuestionDTO(**q) for q in questions],
        exercises=[ExerciseDTO(**e) for e in exercises],
        notions=[NotionDTO(**n) for n in notions],
    )


@router.post("", response_model=WorkshopResponse)
def create(payload: CreateWorkshopRequest) -> WorkshopResponse:
    quiz_data = {"questions": [q.model_dump() for q in payload.questions]}
    ws = create_work_session(
        quiz_data,
        [n.model_dump() for n in payload.notions],
        payload.title,
        owner_name=payload.owner_name,
        exercises_data=[e.model_dump() for e in payload.exercises],
        acronyms_data=[a.model_dump() for a in payload.acronyms],
    )
    return _to_response(ws)


@router.get("", response_model=list[WorkshopSummary])
def list_all() -> list[WorkshopSummary]:
    return [
        WorkshopSummary(
            work_code=ws.work_code,
            title=ws.title,
            owner_name=ws.owner_name,
            status=ws.status,
            last_modified=ws.last_modified,
        )
        for ws in list_work_sessions()
    ]


@router.get("/{work_code}", response_model=WorkshopResponse)
def get_one(work_code: str) -> WorkshopResponse:
    ws = get_work_session(work_code.upper())
    if not ws:
        raise HTTPException(status_code=404, detail="Atelier introuvable.")
    return _to_response(ws)


@router.put("/{work_code}", response_model=WorkshopResponse)
def update(work_code: str, payload: UpdateWorkshopRequest) -> WorkshopResponse:
    code = work_code.upper()
    quiz_data = {"questions": [q.model_dump() for q in payload.questions]}
    ok = update_work_session_draft(
        code,
        quiz_data,
        editor_name=payload.editor_name,
        notions_data=[n.model_dump() for n in payload.notions],
        exercises_data=[e.model_dump() for e in payload.exercises],
        acronyms_data=[a.model_dump() for a in payload.acronyms],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Atelier introuvable.")
    ws = get_work_session(code)
    return _to_response(ws)


@router.post("/{work_code}/publish")
def publish(work_code: str, payload: PublishWorkshopRequest) -> dict:
    session = publish_work_session(
        work_code.upper(),
        session_title=payload.session_title or None,
        pool_mode=payload.pool_mode,
        subset_size=payload.subset_size,
        pass_threshold=payload.pass_threshold,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Atelier introuvable.")
    return {"session_code": session.session_code, "title": session.title}
