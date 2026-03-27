"""
token_tracker.py — Décorateur et utilitaires pour le suivi des tokens LLM.
"""

import logging
import time
from functools import wraps
from threading import Lock
from typing import List

logger = logging.getLogger(__name__)

_lock = Lock()
_call_log: List[dict] = []


def log_token_usage(
    function_name: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Enregistre l'utilisation de tokens pour un appel LLM."""
    entry = {
        "function": function_name,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "timestamp": time.time(),
    }
    with _lock:
        _call_log.append(entry)

    # Incrémenter les stats globales
    try:
        from core.stats_manager import increment_stats
        increment_stats(tokens=output_tokens)
    except Exception:
        pass

    logger.debug(
        "Tokens [%s] %s: in=%d out=%d total=%d",
        model, function_name, input_tokens, output_tokens, input_tokens + output_tokens,
    )


def get_token_summary() -> dict:
    """Retourne un résumé agrégé de l'utilisation des tokens."""
    with _lock:
        if not _call_log:
            return {"total_calls": 0, "total_input": 0, "total_output": 0, "total_tokens": 0}
        return {
            "total_calls": len(_call_log),
            "total_input": sum(e["input_tokens"] for e in _call_log),
            "total_output": sum(e["output_tokens"] for e in _call_log),
            "total_tokens": sum(e["total_tokens"] for e in _call_log),
            "calls": list(_call_log),
        }


def reset_token_log() -> None:
    """Réinitialise le journal des tokens (utile pour les tests)."""
    with _lock:
        _call_log.clear()
