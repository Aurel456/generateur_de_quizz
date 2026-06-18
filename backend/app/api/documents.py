"""Upload de documents → extraction + chunking (réutilise processing.document_processor).

Le client envoie un ou plusieurs fichiers ; le backend extrait le texte, découpe en
chunks et conserve le résultat en mémoire sous un `doc_id` réutilisé par les étapes
suivantes (notions, quiz).
"""
import io
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.config import settings
from backend.app.converters import chunk_preview
from backend.app.doc_store import doc_store
from backend.app.schemas import DocumentStats, UploadResponse
from processing.document_processor import (
    extract_and_chunk_multiple,
    extract_and_chunk_multiple_vision,
    extract_oneshot_chunks,
)

router = APIRouter(prefix="/documents", tags=["documents"])
log = logging.getLogger(__name__)

ALLOWED_EXT = (".pdf", ".docx", ".pptx", ".odt", ".odp", ".ods", ".txt")


@router.post("", response_model=UploadResponse)
def upload_documents(
    files: list[UploadFile] = File(...),
    vision_mode: bool = Form(False),
    one_shot: bool = Form(False),
    max_tokens: int = Form(0),  # 0 → valeur par défaut (settings.CHUNK_MAX_TOKENS)
    max_images_per_chunk: int = Form(10),
    min_dpi: int = Form(65),
    max_dpi: int = Form(80),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni.")

    buffers: list[io.BytesIO] = []
    filenames: list[str] = []
    for upload in files:
        name = (upload.filename or "").strip()
        if not name.lower().endswith(ALLOWED_EXT):
            raise HTTPException(
                status_code=400,
                detail=f"Format non supporté : {name}. Acceptés : {', '.join(ALLOWED_EXT)}",
            )
        buffer = io.BytesIO(upload.file.read())
        buffer.name = name  # document_processor identifie le type via .name
        buffers.append(buffer)
        filenames.append(name)

    # One-shot et vision s'appuient tous deux sur le modèle vision (images).
    uses_vision = vision_mode or one_shot
    try:
        if one_shot:
            chunks = extract_oneshot_chunks(buffers)
        elif vision_mode:
            chunks = extract_and_chunk_multiple_vision(
                buffers,
                max_images_per_chunk=max_images_per_chunk,
                min_dpi=min_dpi,
                max_dpi=max_dpi,
            )
        else:
            chunks = extract_and_chunk_multiple(
                buffers,
                mode="token",
                max_tokens=max_tokens or settings.CHUNK_MAX_TOKENS,
                overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
            )
    except Exception:
        log.exception("Échec extraction/chunking")
        raise HTTPException(status_code=422, detail="Impossible d'extraire le contenu des fichiers.")

    if not chunks:
        raise HTTPException(status_code=422, detail="Aucun texte exploitable dans les documents.")

    doc_id = doc_store.put(chunks, filenames, vision=uses_vision)

    # Stats par document.
    per_doc: dict[str, DocumentStats] = {}
    for chunk in chunks:
        stats = per_doc.setdefault(
            chunk.source_document, DocumentStats(name=chunk.source_document)
        )
        stats.total_tokens += chunk.token_count
        stats.num_pages = max(stats.num_pages, len(chunk.source_pages))

    return UploadResponse(
        doc_id=doc_id,
        num_chunks=len(chunks),
        total_tokens=sum(c.token_count for c in chunks),
        documents=list(per_doc.values()),
        chunks_preview=[chunk_preview(c) for c in chunks[:8]],
    )
