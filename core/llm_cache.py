"""
llm_cache.py — Cache LLM avec clé SHA256, TTL, LRU eviction et persistence optionnelle.
"""

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# Chemin par défaut pour la persistence du cache
_DEFAULT_CACHE_PATH = os.path.join("shared_data", "llm_cache.json")


class LLMCache:
    """
    Cache en mémoire pour les réponses LLM.

    - Clé = SHA256(system_prompt + user_prompt + model + temperature)
    - LRU eviction quand max_size est atteint
    - TTL optionnel (en secondes)
    - Persistence optionnelle vers fichier JSON
    """

    def __init__(
        self,
        max_size: int = 500,
        ttl: Optional[int] = 3600,
        persist_path: Optional[str] = None,
    ):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = Lock()
        self.max_size = max_size
        self.ttl = ttl
        self.persist_path = persist_path
        if persist_path:
            self._load_from_file()

    @staticmethod
    def _make_key(system_prompt: str, user_prompt: str, model: str, temperature: float) -> str:
        """Génère une clé SHA256 à partir des paramètres de l'appel."""
        raw = f"{system_prompt}|{user_prompt}|{model}|{temperature}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
    ) -> Optional[str]:
        """Retourne la réponse cachée ou None si absent/expiré."""
        key = self._make_key(system_prompt, user_prompt, model, temperature)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            # Vérifier TTL
            if self.ttl and (time.time() - entry["timestamp"]) > self.ttl:
                del self._cache[key]
                return None
            # Déplacer en fin (most recently used)
            self._cache.move_to_end(key)
            logger.debug("Cache HIT pour clé %s", key[:12])
            return entry["response"]

    def put(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        response: str,
    ) -> None:
        """Stocke une réponse dans le cache."""
        key = self._make_key(system_prompt, user_prompt, model, temperature)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = {"response": response, "timestamp": time.time()}
            else:
                self._cache[key] = {"response": response, "timestamp": time.time()}
                # Eviction LRU si nécessaire
                while len(self._cache) > self.max_size:
                    self._cache.popitem(last=False)

    def clear(self) -> None:
        """Vide le cache."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """Retourne les statistiques du cache."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
            }

    def save_to_file(self, path: Optional[str] = None) -> None:
        """Persiste le cache vers un fichier JSON."""
        target = path or self.persist_path or _DEFAULT_CACHE_PATH
        with self._lock:
            data = {k: v for k, v in self._cache.items()}
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.debug("Cache sauvegardé vers %s (%d entrées)", target, len(data))
        except Exception as e:
            logger.warning("Erreur sauvegarde cache : %s", e)

    def _load_from_file(self) -> None:
        """Charge le cache depuis un fichier JSON."""
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for key, entry in data.items():
                # Ignorer les entrées expirées
                if self.ttl and (now - entry.get("timestamp", 0)) > self.ttl:
                    continue
                self._cache[key] = entry
            # Tronquer si trop d'entrées
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
            logger.debug("Cache chargé depuis %s (%d entrées)", self.persist_path, len(self._cache))
        except Exception as e:
            logger.warning("Erreur chargement cache : %s", e)


# Instance globale du cache
_global_cache = LLMCache(
    max_size=500,
    ttl=3600,
    persist_path=_DEFAULT_CACHE_PATH,
)


def get_cache() -> LLMCache:
    """Retourne l'instance globale du cache."""
    return _global_cache
