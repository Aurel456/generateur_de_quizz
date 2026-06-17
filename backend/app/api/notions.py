"""Détection des notions fondamentales (réutilise generation.notion_detector)."""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import dict_to_notion, notion_to_dict
from backend.app.doc_store import doc_store
from backend.app.schemas import (
    DetectNotionsRequest,
    DetectNotionsResponse,
    EditNotionsRequest,
    MergeNotionsRequest,
    MergeNotionsResponse,
    NotionDTO,
)
from generation.notion_detector import detect_notions, edit_notions_with_llm, merge_similar_notions

router = APIRouter(prefix="/notions", tags=["notions"])
log = logging.getLogger(__name__)


# Endpoint synchrone (def) : l'appel LLM est bloquant et FastAPI l'exécute dans un
# threadpool, sans bloquer la boucle asyncio.
@router.post("/detect", response_model=DetectNotionsResponse)
def detect(payload: DetectNotionsRequest) -> DetectNotionsResponse:
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    try:
        notions = detect_notions(entry.chunks, vision_mode=entry.vision)
    except Exception:
        log.exception("Échec détection des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de la détection des notions.")

    return DetectNotionsResponse(notions=[NotionDTO(**notion_to_dict(n)) for n in notions])


@router.post("/edit", response_model=DetectNotionsResponse)
def edit(payload: EditNotionsRequest) -> DetectNotionsResponse:
    """Modifie la liste de notions via une instruction en langage naturel (LLM)."""
    current = [dict_to_notion(n.model_dump()) for n in payload.notions]
    try:
        updated = edit_notions_with_llm(current, payload.instruction)
    except Exception:
        log.exception("Échec édition des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de l'édition des notions.")
    return DetectNotionsResponse(notions=[NotionDTO(**notion_to_dict(n)) for n in updated])


@router.post("/merge", response_model=MergeNotionsResponse)
def merge(payload: MergeNotionsRequest) -> MergeNotionsResponse:
    """Fusionne les notions similaires/redondantes via le LLM."""
    current = [dict_to_notion(n.model_dump()) for n in payload.notions]
    try:
        merged, summary = merge_similar_notions(current)
    except Exception:
        log.exception("Échec fusion des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de la fusion des notions.")
    return MergeNotionsResponse(
        notions=[NotionDTO(**notion_to_dict(n)) for n in merged],
        summary=str(summary or ""),
    )
