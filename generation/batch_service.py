"""
batch_service.py — Service de traitement par lots via ThreadPoolExecutor.
Exécute plusieurs requêtes LLM en parallèle sur n'importe quel serveur OpenAI-compatible.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from core.llm_service import call_llm_json, call_llm_vision_json

logger = logging.getLogger(__name__)

# Nombre de workers par défaut pour le pool de threads
DEFAULT_MAX_WORKERS = 8


@dataclass
class BatchRequest:
    """Représente une requête individuelle dans un batch."""
    custom_id: str
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float = 0.5
    max_tokens: Optional[int] = None
    images: Optional[List[str]] = None  # base64 images pour vision


def _execute_single_request(req: BatchRequest) -> tuple:
    """
    Exécute une seule requête LLM et retourne (custom_id, result_dict ou None, error ou None).
    """
    try:
        if req.images:
            result = call_llm_vision_json(
                system_prompt=req.system_prompt,
                user_prompt=req.user_prompt,
                images=req.images,
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        else:
            result = call_llm_json(
                system_prompt=req.system_prompt,
                user_prompt=req.user_prompt,
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        return (req.custom_id, result, None)
    except Exception as e:
        logger.warning(f"Erreur pour la requête {req.custom_id}: {e}")
        return (req.custom_id, None, str(e))


def run_batch_json(
    requests: List[BatchRequest],
    progress_callback: Optional[Callable] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Dict[str, dict]:
    """
    Exécute toutes les requêtes LLM en parallèle via ThreadPoolExecutor.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi de progression.
        max_workers: Nombre max de threads parallèles.

    Returns:
        Dict {custom_id: parsed_json_dict} pour les requêtes réussies.
    """
    if not requests:
        return {}

    total = len(requests)
    completed_count = 0
    results = {}

    if progress_callback:
        progress_callback(0, total)

    with ThreadPoolExecutor(max_workers=min(max_workers, total)) as executor:
        future_to_id = {
            executor.submit(_execute_single_request, req): req.custom_id
            for req in requests
        }

        for future in as_completed(future_to_id):
            custom_id, result, error = future.result()
            completed_count += 1

            if result is not None:
                results[custom_id] = result
            else:
                logger.warning(f"Requête {custom_id} échouée : {error}")

            if progress_callback:
                progress_callback(completed_count, total)

    return results
