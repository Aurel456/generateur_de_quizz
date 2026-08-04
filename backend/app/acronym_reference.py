"""Détection des acronymes par référentiel (sans LLM).

Partagé par l'upload (détection automatique, comme l'app Streamlit) et par
l'endpoint `/acronyms/detect`. Le référentiel est optionnel : son absence n'est
jamais bloquante, elle réduit simplement la détection à la passe LLM.
"""
import logging
import os

from generation.acronym_detector import (
    Acronym,
    detect_acronyms_from_text,
    load_acronym_reference,
)
from processing.document_processor import TextChunk

log = logging.getLogger(__name__)

REFERENCE_PATH = os.getenv("ACRONYMS_REFERENCE", "reference_data/acronyms.json")


def detect_reference_acronyms(chunks: list[TextChunk]) -> list[Acronym]:
    """Scan regex des chunks contre le référentiel. Renvoie [] si indisponible."""
    try:
        reference = load_acronym_reference(REFERENCE_PATH)
    except FileNotFoundError:
        log.info("Référentiel d'acronymes absent (%s) — détection LLM seule.", REFERENCE_PATH)
        return []
    except Exception:
        log.exception("Erreur lecture référentiel acronymes")
        return []
    try:
        return detect_acronyms_from_text(chunks, reference)
    except Exception:
        log.exception("Erreur détection acronymes par référentiel")
        return []
