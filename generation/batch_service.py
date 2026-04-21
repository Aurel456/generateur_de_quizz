"""
batch_service.py — Service de traitement séquentiel des requêtes LLM.
Exécute les requêtes une par une avec retry individuel.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core.llm_service import call_llm_json, call_llm_vision_json

logger = logging.getLogger(__name__)


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
    enable_thinking: bool = True


@dataclass
class BatchResult:
    """Résultat enrichi d'un batch avec suivi des échecs."""
    results: Dict[str, dict] = field(default_factory=dict)
    failures: Dict[str, str] = field(default_factory=dict)  # custom_id -> erreur
    retry_count: int = 0


def _execute_single_request(req: BatchRequest, max_retries: int = 2) -> tuple:
    """
    Exécute une seule requête LLM avec retry individuel.
    Retourne (custom_id, result_dict ou None, error ou None).
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if req.images:
                result = call_llm_vision_json(
                    system_prompt=req.system_prompt,
                    user_prompt=req.user_prompt,
                    images=req.images,
                    model=req.model,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    enable_thinking=req.enable_thinking,
                )
            else:
                result = call_llm_json(
                    system_prompt=req.system_prompt,
                    user_prompt=req.user_prompt,
                    model=req.model,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    enable_thinking=req.enable_thinking,
                )
            return (req.custom_id, result, None)
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                logger.info(f"Retry {attempt + 1}/{max_retries} pour {req.custom_id}: {e}")

    logger.warning(f"Erreur définitive pour la requête {req.custom_id}: {last_error}")
    return (req.custom_id, None, last_error)


def run_batch_json(
    requests: List[BatchRequest],
    progress_callback: Optional[Callable] = None,
) -> Dict[str, dict]:
    """
    Exécute toutes les requêtes LLM séquentiellement.
    Retourne seulement les résultats réussis.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi de progression.

    Returns:
        Dict {custom_id: parsed_json_dict} pour les requêtes réussies.
    """
    if not requests:
        return {}

    batch_result = run_batch_json_with_retry(requests, progress_callback)
    return batch_result.results


def run_batch_json_with_retry(
    requests: List[BatchRequest],
    progress_callback: Optional[Callable] = None,
    max_batch_retries: int = 1,
) -> BatchResult:
    """
    Exécute les requêtes LLM séquentiellement avec retry au niveau batch.
    Les requêtes échouées sont re-soumises jusqu'à max_batch_retries fois.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi.
        max_batch_retries: Nombre de tentatives de re-soumission des échecs.

    Returns:
        BatchResult avec résultats, échecs et compteur de retries.
    """
    if not requests:
        return BatchResult()

    total = len(requests)
    completed_count = 0
    all_results: Dict[str, dict] = {}
    all_failures: Dict[str, str] = {}
    pending_requests = list(requests)
    retry_count = 0

    if progress_callback:
        progress_callback(0, total)

    for batch_attempt in range(max_batch_retries + 1):
        if not pending_requests:
            break

        current_failures = {}

        for req in pending_requests:
            custom_id, result, error = _execute_single_request(req)
            completed_count += 1

            if result is not None:
                all_results[custom_id] = result
            else:
                current_failures[custom_id] = error or "Erreur inconnue"

            if progress_callback:
                progress_callback(min(completed_count, total), total)

        if not current_failures or batch_attempt >= max_batch_retries:
            all_failures = current_failures
            break

        retry_ids = set(current_failures.keys())
        pending_requests = [r for r in pending_requests if r.custom_id in retry_ids]
        retry_count += 1
        logger.info(
            f"Batch retry {retry_count}: re-soumission de {len(pending_requests)} requêtes échouées"
        )

    return BatchResult(results=all_results, failures=all_failures, retry_count=retry_count)
