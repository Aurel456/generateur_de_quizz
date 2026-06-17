"""Détection d'acronymes (réutilise generation.acronym_detector)."""
import logging
import os

from fastapi import APIRouter, HTTPException

from backend.app.converters import acronym_to_dict
from backend.app.doc_store import doc_store
from backend.app.schemas import AcronymDTO, DetectAcronymsRequest, DetectAcronymsResponse
from generation.acronym_detector import (
    detect_acronyms_from_text,
    detect_unknown_acronyms_with_llm,
    load_acronym_reference,
)

router = APIRouter(prefix="/acronyms", tags=["acronyms"])
log = logging.getLogger(__name__)

REFERENCE_PATH = os.getenv("ACRONYMS_REFERENCE", "reference_data/acronyms.json")


@router.post("/detect", response_model=DetectAcronymsResponse)
def detect(payload: DetectAcronymsRequest) -> DetectAcronymsResponse:
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    # 1) Détection par référence (best-effort : le fichier peut être absent).
    acronyms = []
    try:
        reference = load_acronym_reference(REFERENCE_PATH)
        acronyms = detect_acronyms_from_text(entry.chunks, reference)
    except FileNotFoundError:
        log.info("Référentiel d'acronymes absent (%s) — détection LLM seule.", REFERENCE_PATH)
    except Exception:
        log.exception("Erreur lecture référentiel acronymes")

    # 2) Détection LLM des acronymes inconnus.
    if payload.use_llm:
        try:
            known = [a.acronym for a in acronyms]
            acronyms += detect_unknown_acronyms_with_llm(entry.chunks, known)
        except Exception:
            log.exception("Échec détection LLM des acronymes")

    return DetectAcronymsResponse(acronyms=[AcronymDTO(**acronym_to_dict(a)) for a in acronyms])
