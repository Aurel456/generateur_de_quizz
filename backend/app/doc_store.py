"""Stockage en mémoire des documents traités (chunks), indexé par `doc_id`.

Évite de faire transiter par le réseau les chunks (potentiellement volumineux) entre
l'upload, la détection de notions et la génération de quiz : le frontend ne manipule
qu'un identifiant.

Limites assumées (v1) : stockage en mémoire, mono-instance, éviction LRU simple. Pour
la production multi-instances, remplacer par Redis ou un stockage persistant.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field

from processing.document_processor import TextChunk

_MAX_DOCS = 50  # éviction des plus anciens au-delà


@dataclass
class DocEntry:
    doc_id: str
    chunks: list[TextChunk]
    filenames: list[str]
    vision: bool = False
    created_at: float = field(default_factory=time.time)


class DocStore:
    def __init__(self) -> None:
        self._entries: dict[str, DocEntry] = {}
        self._lock = threading.Lock()

    def put(self, chunks: list[TextChunk], filenames: list[str], vision: bool = False) -> str:
        doc_id = uuid.uuid4().hex[:12]
        with self._lock:
            if len(self._entries) >= _MAX_DOCS:
                oldest = min(self._entries.values(), key=lambda e: e.created_at)
                self._entries.pop(oldest.doc_id, None)
            self._entries[doc_id] = DocEntry(doc_id, chunks, filenames, vision=vision)
        return doc_id

    def get(self, doc_id: str) -> DocEntry | None:
        with self._lock:
            return self._entries.get(doc_id)


doc_store = DocStore()
