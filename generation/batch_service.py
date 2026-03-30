"""
batch_service.py — Service de traitement par lots via ThreadPoolExecutor.
Exécute plusieurs requêtes LLM en parallèle sur n'importe quel serveur OpenAI-compatible.
Supporte le dispatch dynamique multi-modèles (les modèles rapides reçoivent plus de requêtes).
"""

import logging
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
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
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Dict[str, dict]:
    """
    Exécute toutes les requêtes LLM en parallèle via ThreadPoolExecutor.
    Backward-compatible : retourne seulement les résultats réussis.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi de progression.
        max_workers: Nombre max de threads parallèles.

    Returns:
        Dict {custom_id: parsed_json_dict} pour les requêtes réussies.
    """
    if not requests:
        return {}

    batch_result = run_batch_json_with_retry(requests, progress_callback, max_workers)
    return batch_result.results


def run_batch_json_with_retry(
    requests: List[BatchRequest],
    progress_callback: Optional[Callable] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_batch_retries: int = 1,
) -> BatchResult:
    """
    Exécute les requêtes LLM en parallèle avec retry au niveau batch.
    Les requêtes échouées sont re-soumises jusqu'à max_batch_retries fois.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi.
        max_workers: Nombre max de threads parallèles.
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

        with ThreadPoolExecutor(max_workers=min(max_workers, len(pending_requests))) as executor:
            future_to_id = {
                executor.submit(_execute_single_request, req): req.custom_id
                for req in pending_requests
            }

            for future in as_completed(future_to_id):
                custom_id, result, error = future.result()
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

        # Préparer les requêtes à re-soumettre
        retry_ids = set(current_failures.keys())
        pending_requests = [r for r in pending_requests if r.custom_id in retry_ids]
        retry_count += 1
        logger.info(
            f"Batch retry {retry_count}: re-soumission de {len(pending_requests)} requêtes échouées"
        )

    return BatchResult(results=all_results, failures=all_failures, retry_count=retry_count)


def run_batch_multi_model(
    requests: List[BatchRequest],
    models: List[str],
    progress_callback: Optional[Callable] = None,
    max_retries: int = 2,
) -> BatchResult:
    """
    Dispatch dynamique multi-modèles : chaque modèle est un worker qui consomme
    les requêtes d'une queue. Dès qu'un modèle termine, il reçoit la suivante.
    Les modèles plus rapides traitent donc plus de requêtes.

    Args:
        requests: Liste de BatchRequest (le champ model sera écrasé par le dispatcher).
        models: Liste de noms de modèles vision disponibles.
        progress_callback: Callback(completed, total).
        max_retries: Retries par requête individuelle.

    Returns:
        BatchResult avec résultats et échecs.
    """
    if not requests:
        return BatchResult()
    if not models:
        return run_batch_json_with_retry(requests, progress_callback)

    total = len(requests)
    work_queue: queue.Queue[BatchRequest] = queue.Queue()
    for req in requests:
        work_queue.put(req)

    all_results: Dict[str, dict] = {}
    all_failures: Dict[str, str] = {}
    completed_count = 0

    if progress_callback:
        progress_callback(0, total)

    def _worker(model_name: str):
        """Un worker par modèle — consomme la queue jusqu'à épuisement."""
        nonlocal completed_count
        worker_results = []
        while True:
            try:
                req = work_queue.get_nowait()
            except queue.Empty:
                break
            req.model = model_name
            custom_id, result, error = _execute_single_request(req, max_retries)
            worker_results.append((custom_id, result, error))
            completed_count += 1
            if progress_callback:
                progress_callback(min(completed_count, total), total)
        return worker_results

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = [executor.submit(_worker, m) for m in models]
        for future in as_completed(futures):
            for custom_id, result, error in future.result():
                if result is not None:
                    all_results[custom_id] = result
                else:
                    all_failures[custom_id] = error or "Erreur inconnue"

    return BatchResult(results=all_results, failures=all_failures)
