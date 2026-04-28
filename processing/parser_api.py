"""
parser_api.py — Client pour l'API externe "Document Parser API pour Qwen".

Envoie les documents (PDF, Office, LibreOffice) à un service de parsing
(MinerU/MarkItDown) qui renvoie un payload multimodal déjà formaté pour
le modèle Qwen Vision : séquence ordonnée de blocs texte et image_url.

Utilisé comme alternative au rendu PyMuPDF local en mode vision :
au lieu de ne voir que des images, le LLM reçoit l'interleaving texte+image
produit par le parser (meilleur contexte pour les slides/schémas).
"""

from __future__ import annotations

import logging
import os
import re
from typing import BinaryIO, Dict, List, Optional, Tuple

import requests

from core.llm_service import count_tokens
from processing.document_processor import TextChunk

logger = logging.getLogger(__name__)

PARSER_API_URL = os.getenv("PARSER_API_URL", "http://10.156.226.143:3066/parse-to-qwen")
PARSER_API_TIMEOUT = int(os.getenv("PARSER_API_TIMEOUT", "600"))

# Coût d'image estimé pour le token_count (utilisé pour la répartition des questions)
_ESTIMATED_TOKENS_PER_IMAGE = 1500

_MIME_BY_EXT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "odt": "application/vnd.oasis.opendocument.text",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "txt": "text/plain",
    "md": "text/markdown",
}

_DOC_SEP_RE = re.compile(r"---\s*DOCUMENT\s*:\s*(.+?)\s*---", re.IGNORECASE)
_PAGE_RE = re.compile(r"(?:slide\s*number|page)\s*:?\s*(\d+)", re.IGNORECASE)


def _guess_mime(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return _MIME_BY_EXT.get(ext, "application/octet-stream")


def _post_files(files: List[BinaryIO], min_img_size: int) -> List[Dict]:
    """Appelle l'API /parse-to-qwen et retourne la liste payload."""
    multipart = []
    for f in files:
        try:
            f.seek(0)
        except Exception:
            pass
        name = getattr(f, "name", "document.bin")
        data = f.read()
        try:
            f.seek(0)
        except Exception:
            pass
        multipart.append(("files", (name, data, _guess_mime(name))))

    resp = requests.post(
        PARSER_API_URL,
        files=multipart,
        data={"min_img_size": int(min_img_size)},
        timeout=PARSER_API_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json() or {}
    return body.get("payload", []) or []


def _split_by_document(payload: List[Dict], default_name: str) -> List[Tuple[str, List[Dict]]]:
    """Découpe le payload en groupes par document (sur séparateurs `--- DOCUMENT : ... ---`)."""
    groups: List[Tuple[str, List[Dict]]] = []
    current_name = default_name
    current: List[Dict] = []
    for item in payload:
        if item.get("type") == "text":
            m = _DOC_SEP_RE.search(item.get("text", ""))
            if m:
                if current:
                    groups.append((current_name, current))
                current_name = m.group(1).strip() or default_name
                current = []
                continue
        current.append(item)
    if current:
        groups.append((current_name, current))
    return groups or [(default_name, payload)]


def _chunk_by_images(items: List[Dict], max_images_per_chunk: int) -> List[List[Dict]]:
    """Groupe les items par paquets contenant au plus `max_images_per_chunk` images."""
    if max_images_per_chunk <= 0:
        return [items]
    chunks: List[List[Dict]] = []
    current: List[Dict] = []
    img_count = 0
    for item in items:
        current.append(item)
        if item.get("type") == "image_url":
            img_count += 1
            if img_count >= max_images_per_chunk:
                chunks.append(current)
                current = []
                img_count = 0
    if current:
        chunks.append(current)
    return chunks or [items]


def _extract_text(items: List[Dict]) -> str:
    parts = [it.get("text", "") for it in items if it.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def _extract_images_b64(items: List[Dict]) -> List[str]:
    """Extrait les images base64 nues (sans le préfixe data:...) des items image_url."""
    out: List[str] = []
    for it in items:
        if it.get("type") != "image_url":
            continue
        url = (it.get("image_url") or {}).get("url", "")
        if ";base64," in url:
            out.append(url.split(";base64,", 1)[1])
    return out


def _extract_pages(items: List[Dict]) -> List[int]:
    pages = set()
    for it in items:
        if it.get("type") == "text":
            for m in _PAGE_RE.finditer(it.get("text", "")):
                try:
                    pages.add(int(m.group(1)))
                except ValueError:
                    continue
    return sorted(pages)


def _build_chunk(items: List[Dict], doc_name: str) -> TextChunk:
    text = _extract_text(items)
    images = _extract_images_b64(items)
    pages = _extract_pages(items)
    tokens = count_tokens(text) + len(images) * _ESTIMATED_TOKENS_PER_IMAGE
    return TextChunk(
        text=text or f"[{len(images)} image(s) — parser API]",
        source_pages=pages,
        token_count=tokens,
        source_document=doc_name,
        page_images=images,
        qwen_payload=items,
    )


def extract_with_parser_api(
    files: List[BinaryIO],
    min_img_size: int = 0,
    max_images_per_chunk: int = 10,
) -> List[TextChunk]:
    """
    Envoie chaque fichier à l'API de parsing et retourne une liste de `TextChunk`
    dont le champ `qwen_payload` contient la séquence multimodale prête à être
    envoyée au modèle Qwen Vision.

    Paramètres :
        files: fichiers uploadés (BinaryIO avec attribut `.name`).
        min_img_size: taille minimum des images (px) — passé tel quel à l'API.
        max_images_per_chunk: chunk cap (nombre d'images max par chunk).

    Appelle l'API document par document pour limiter la taille des réponses
    et isoler les erreurs.
    """
    all_chunks: List[TextChunk] = []
    for f in files:
        doc_name = getattr(f, "name", "document")
        try:
            payload = _post_files([f], min_img_size=min_img_size)
        except requests.HTTPError as e:
            logger.error("Parser API %s HTTP %s : %s", doc_name, e.response.status_code, e)
            raise
        except Exception as e:
            logger.error("Parser API %s échec : %s", doc_name, e)
            raise

        if not payload:
            logger.warning("Parser API %s : payload vide", doc_name)
            continue

        for name, items in _split_by_document(payload, default_name=doc_name):
            for sub in _chunk_by_images(items, max_images_per_chunk):
                all_chunks.append(_build_chunk(sub, doc_name=name or doc_name))
    return all_chunks
