"""Exports HTML / CSV / Moodle XML / SCENARI (réutilise export.quiz_exporter)."""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.converters import dict_to_acronym, dict_to_exercise, quiz_from_questions
from backend.app.schemas import ExportRequest
from export import quiz_exporter
from export.scenari_exporter import export_scenari_zip

router = APIRouter(prefix="/export", tags=["export"])
log = logging.getLogger(__name__)

_MEDIA = {"html": "text/html", "csv": "text/csv", "moodle": "application/xml", "scenari": "application/zip"}
_EXT = {"html": "html", "csv": "csv", "moodle": "xml", "scenari": "zip"}


@router.post("")
def export(payload: ExportRequest) -> Response:
    quiz = quiz_from_questions([q.model_dump() for q in payload.questions], title=payload.title)
    exercises = [dict_to_exercise(e.model_dump()) for e in payload.exercises]
    acronyms = [dict_to_acronym(a.model_dump()) for a in payload.acronyms]

    try:
        if payload.format == "scenari":
            # Archive ZIP d'items .quiz, contenu selon le périmètre demandé.
            scenari_quiz = quiz if payload.scope in ("quiz", "combined") else None
            scenari_ex = exercises if payload.scope in ("exercises", "combined") else None
            content = export_scenari_zip(scenari_quiz, scenari_ex)
        elif payload.scope == "quiz":
            if payload.format == "html":
                content = quiz_exporter.export_quiz_html(quiz, acronyms)
            elif payload.format == "csv":
                content = quiz_exporter.export_quiz_csv(quiz)
            else:  # moodle
                content = quiz_exporter.export_quiz_moodle_xml(quiz, payload.title)
        elif payload.scope == "exercises":
            if payload.format == "csv":
                content = quiz_exporter.export_exercises_csv(exercises)
            else:
                content = quiz_exporter.export_exercises_html(exercises, acronyms)
        else:  # combined
            if payload.format == "csv":
                content = quiz_exporter.export_combined_csv(quiz, exercises)
            else:
                content = quiz_exporter.export_combined_html(quiz, exercises, acronyms)
    except Exception:
        log.exception("Échec export")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération de l'export.")

    filename = f"{payload.scope}.{_EXT[payload.format]}"
    return Response(
        content=content,
        media_type=_MEDIA[payload.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
