"""
batch_service.py — Service de traitement par lots via l'API Batch OpenAI.
Soumet plusieurs requêtes LLM en une seule fois et attend les résultats.
"""

import io
import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from llm_service import get_client, count_tokens, MODEL_CONTEXT_WINDOW, SYSTEM_PROMPT_MARGIN

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


def _build_messages(req: BatchRequest) -> list:
    """Construit les messages OpenAI pour une requête batch."""
    json_suffix = (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )
    system_content = req.system_prompt + json_suffix

    # Construire le contenu user (texte seul ou multimodal)
    if req.images:
        user_content = [{"type": "text", "text": req.user_prompt}]
        for img_b64 in req.images:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
    else:
        user_content = req.user_prompt

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _estimate_max_tokens(req: BatchRequest) -> Optional[int]:
    """Estime max_tokens si non fourni."""
    if req.max_tokens is not None:
        return req.max_tokens
    prompt_tokens = count_tokens(req.system_prompt) + count_tokens(req.user_prompt) + SYSTEM_PROMPT_MARGIN
    available = MODEL_CONTEXT_WINDOW - prompt_tokens
    return max(available, 100) if available > 0 else None


def create_batch_jsonl(requests: List[BatchRequest]) -> str:
    """
    Sérialise les requêtes en format JSONL pour l'API Batch.

    Chaque ligne est un objet JSON avec :
    - custom_id: identifiant unique
    - method: "POST"
    - url: "/v1/chat/completions"
    - body: paramètres de la requête
    """
    lines = []
    for req in requests:
        messages = _build_messages(req)
        body = {
            "model": req.model,
            "messages": messages,
            "temperature": req.temperature,
        }
        max_tok = _estimate_max_tokens(req)
        if max_tok is not None:
            body["max_tokens"] = max_tok

        line = {
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }
        lines.append(json.dumps(line, ensure_ascii=False))

    return "\n".join(lines)


def submit_batch(jsonl_content: str) -> str:
    """
    Upload le fichier JSONL et crée un batch.

    Returns:
        batch_id (str)
    """
    client = get_client()

    # Upload du fichier JSONL
    jsonl_bytes = jsonl_content.encode("utf-8")
    file_obj = client.files.create(
        file=("batch_requests.jsonl", io.BytesIO(jsonl_bytes)),
        purpose="batch",
    )
    logger.info(f"Fichier batch uploadé : {file_obj.id}")

    # Créer le batch
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    logger.info(f"Batch créé : {batch.id} ({batch.status})")
    return batch.id


def poll_batch(
    batch_id: str,
    progress_callback: Optional[Callable] = None,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> object:
    """
    Attend la fin du batch en interrogeant périodiquement l'API.

    Args:
        batch_id: ID du batch.
        progress_callback: Callback(completed, total) pour le suivi.
        poll_interval: Intervalle de polling en secondes.
        timeout: Timeout global en secondes.

    Returns:
        Objet batch terminé.

    Raises:
        RuntimeError si le batch échoue ou expire.
    """
    client = get_client()
    start_time = time.time()

    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status

        # Progression
        if progress_callback and batch.request_counts:
            completed = batch.request_counts.completed or 0
            total = batch.request_counts.total or 0
            progress_callback(completed, total)

        if status == "completed":
            logger.info(f"Batch {batch_id} terminé avec succès.")
            return batch

        if status in ("failed", "expired", "cancelled"):
            errors = []
            if hasattr(batch, 'errors') and batch.errors:
                errors = [str(e) for e in (batch.errors.data or [])]
            raise RuntimeError(
                f"Batch {batch_id} a échoué avec le statut '{status}'. "
                f"Erreurs : {errors}"
            )

        # Timeout
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise RuntimeError(
                f"Batch {batch_id} n'a pas terminé dans le délai imparti ({timeout}s). "
                f"Statut actuel : {status}"
            )

        time.sleep(poll_interval)


def download_batch_results(batch) -> Dict[str, dict]:
    """
    Télécharge et parse les résultats du batch.

    Returns:
        Dict {custom_id: response_body}
    """
    client = get_client()

    if not batch.output_file_id:
        raise RuntimeError("Le batch n'a pas de fichier de sortie.")

    content = client.files.content(batch.output_file_id)
    raw_text = content.text if hasattr(content, 'text') else content.read().decode("utf-8")

    results = {}
    for line in raw_text.strip().split("\n"):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            custom_id = obj.get("custom_id", "")
            response_body = obj.get("response", {}).get("body", {})
            results[custom_id] = response_body
        except json.JSONDecodeError:
            logger.warning(f"Ligne JSONL invalide dans les résultats batch : {line[:200]}")

    return results


def _parse_json_content(raw: str) -> dict:
    """
    Parse le contenu JSON avec les 3 stratégies de fallback (même logique que call_llm_json).
    """
    # Tentative 1 : parsing direct
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Tentative 2 : extraire d'un bloc markdown ```json ... ```
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Tentative 3 : trouver le premier { ... } ou [ ... ]
    brace_match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Impossible de parser le JSON : {raw[:300]}")


def parse_batch_json_results(results: Dict[str, dict]) -> Dict[str, dict]:
    """
    Extrait et parse le contenu JSON de chaque réponse batch.

    Returns:
        Dict {custom_id: parsed_json_dict}
    """
    parsed = {}
    for custom_id, response_body in results.items():
        try:
            choices = response_body.get("choices", [])
            if not choices:
                logger.warning(f"Pas de choices pour {custom_id}")
                continue
            content = choices[0].get("message", {}).get("content", "")
            parsed[custom_id] = _parse_json_content(content)
        except Exception as e:
            logger.warning(f"Erreur parsing JSON pour {custom_id}: {e}")

    return parsed


def run_batch_json(
    requests: List[BatchRequest],
    progress_callback: Optional[Callable] = None,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> Dict[str, dict]:
    """
    Pipeline complet : create → submit → poll → download → parse.

    Args:
        requests: Liste de BatchRequest.
        progress_callback: Callback(completed, total) pour le suivi.
        poll_interval: Intervalle de polling en secondes.
        timeout: Timeout global en secondes.

    Returns:
        Dict {custom_id: parsed_json_dict}
    """
    if not requests:
        return {}

    # 1. Créer le JSONL
    jsonl = create_batch_jsonl(requests)

    # 2. Soumettre
    batch_id = submit_batch(jsonl)

    # 3. Attendre la fin
    batch = poll_batch(batch_id, progress_callback, poll_interval, timeout)

    # 4. Télécharger les résultats
    results = download_batch_results(batch)

    # 5. Parser le JSON
    return parse_batch_json_results(results)
