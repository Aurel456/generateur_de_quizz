"""Détection d'acronymes (réutilise generation.acronym_detector)."""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.acronym_reference import detect_reference_acronyms
from backend.app.converters import acronym_to_dict, dict_to_acronym
from backend.app.doc_store import doc_store
from backend.app.schemas import (
    AcronymDTO,
    DetectAcronymsRequest,
    DetectAcronymsResponse,
    EditAcronymsRequest,
    EditAcronymsResponse,
)
from generation.acronym_detector import detect_unknown_acronyms_with_llm, edit_acronyms_with_llm

router = APIRouter(prefix="/acronyms", tags=["acronyms"])
log = logging.getLogger(__name__)


@router.post("/detect", response_model=DetectAcronymsResponse)
def detect(payload: DetectAcronymsRequest) -> DetectAcronymsResponse:
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    # 1) Détection par référence (best-effort : le fichier peut être absent).
    acronyms = detect_reference_acronyms(entry.chunks)

    # 2) Détection LLM des acronymes inconnus.
    if payload.use_llm:
        try:
            known = [a.acronym for a in acronyms]
            acronyms += detect_unknown_acronyms_with_llm(entry.chunks, known)
        except Exception:
            log.exception("Échec détection LLM des acronymes")

    return DetectAcronymsResponse(acronyms=[AcronymDTO(**acronym_to_dict(a)) for a in acronyms])


@router.post("/edit", response_model=EditAcronymsResponse)
def edit(payload: EditAcronymsRequest) -> EditAcronymsResponse:
    """Modifie la liste d'acronymes via une instruction en langage naturel (LLM)."""
    current = [dict_to_acronym(a.model_dump()) for a in payload.acronyms]
    try:
        updated, summary = edit_acronyms_with_llm(current, payload.instruction)
    except Exception:
        log.exception("Échec édition des acronymes")
        raise HTTPException(status_code=502, detail="Erreur lors de l'édition des acronymes.")
    return EditAcronymsResponse(
        acronyms=[AcronymDTO(**acronym_to_dict(a)) for a in updated],
        summary=str(summary or ""),
    )
