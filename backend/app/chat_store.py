"""Stockage en mémoire des sessions de chat « mode libre » (ChatSession), par chat_id.

Même logique et mêmes limites que `doc_store` (mono-instance, éviction LRU). Voir
MIGRATION_DSFR.md pour le passage à un stockage partagé en production.
"""
import threading
import time
import uuid

from generation.chat_mode import ChatSession

_MAX = 100


class ChatStore:
    def __init__(self) -> None:
        self._sessions: dict[str, tuple[ChatSession, float]] = {}
        self._lock = threading.Lock()

    def put(self, session: ChatSession, chat_id: str | None = None) -> str:
        chat_id = chat_id or uuid.uuid4().hex[:12]
        with self._lock:
            if len(self._sessions) >= _MAX:
                oldest = min(self._sessions.items(), key=lambda kv: kv[1][1])[0]
                self._sessions.pop(oldest, None)
            self._sessions[chat_id] = (session, time.time())
        return chat_id

    def get(self, chat_id: str) -> ChatSession | None:
        with self._lock:
            entry = self._sessions.get(chat_id)
            return entry[0] if entry else None


chat_store = ChatStore()
