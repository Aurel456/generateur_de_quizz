"""
llm_service.py — Client OpenAI pour gtp-oss-120b avec gestion des tokens, retry,
cache SHA256 et tracking des tokens.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from core.llm_cache import get_cache
from core.token_tracker import log_token_usage

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration depuis .env
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://OPENAI_API_BASE:8080/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gtp-oss-120b")
MODEL_CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_WINDOW", "32000"))
TIKTOKEN_ENCODING = os.getenv("TIKTOKEN_ENCODING", "cl100k_base")

# Configuration Vision
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "")
VISION_CONTEXT_WINDOW = int(os.getenv("VISION_CONTEXT_WINDOW", "80000"))

# Marge de sécurité pour les tokens (prompt system + overhead)
SYSTEM_PROMPT_MARGIN = 500
# Ratio de tokens réservé pour la réponse
RESPONSE_TOKEN_RATIO = 0.3

# Encodeur tiktoken (configurable via TIKTOKEN_ENCODING dans .env)
_encoder = tiktoken.get_encoding(TIKTOKEN_ENCODING)

# Client OpenAI
_client = None


def get_client() -> OpenAI:
    """Retourne le client OpenAI (singleton)."""
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=OPENAI_API_BASE,
            api_key=OPENAI_API_KEY
        )
    return _client


def list_models():
    """Liste les modèles disponibles via l'API."""
    client = get_client()
    try:
        return client.models.list().data
    except Exception as e:
        print(f"Erreur lors de la récupération des modèles : {e}")
        return []


def count_tokens(text: str) -> int:
    """Compte les tokens dans un texte."""
    return len(_encoder.encode(text))


def estimate_available_tokens(system_prompt: str, user_prompt: str) -> int:
    """
    Estime les tokens disponibles pour la réponse.

    Returns:
        Nombre de tokens disponibles pour la réponse, ou -1 si le prompt est trop long.
    """
    prompt_tokens = count_tokens(system_prompt) + count_tokens(user_prompt) + SYSTEM_PROMPT_MARGIN
    available = MODEL_CONTEXT_WINDOW - prompt_tokens
    return available if available > 0 else -1


# ── Fonction interne commune ─────────────────────────────────────────────────

def _execute_completion(
    messages: list,
    model: str,
    temperature: float,
    max_tokens: Optional[int] = None,
    retries: int = 3,
    enable_thinking: bool = True,
    caller_name: str = "call_llm",
) -> str:
    """
    Exécute un appel chat.completions.create avec retry, tracking tokens et extra_body.

    Returns:
        Contenu de la réponse (str).
    """
    client = get_client()

    last_error = None
    for attempt in range(retries):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "extra_body": {
                    "enable_thinking": enable_thinking,
                    "chat_template_kwargs": {"enable_thinking": enable_thinking},
                },
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content

            # Token tracking
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, "usage") and response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0
            log_token_usage(caller_name, model, input_tokens, output_tokens)

            return content.strip() if content else ""

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = 2 ** attempt  # Backoff exponentiel : 1, 2, 4 sec
                time.sleep(wait_time)

    raise RuntimeError(
        f"Échec de l'appel LLM ({caller_name}) avec le modèle {model} "
        f"après {retries} tentatives. Dernière erreur : {last_error}"
    )


# ── Parsing JSON résilient ───────────────────────────────────────────────────

def _parse_json_response(raw: str) -> Optional[dict]:
    """Tente de parser une réponse JSON avec plusieurs stratégies de fallback."""
    # Tentative 1 : parsing direct
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Tentative 2 : extraire JSON d'un bloc markdown ```json ... ```
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

    return None


# ── Fonctions publiques ──────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    retries: int = 3,
    json_mode: bool = False,
    use_cache: bool = True,
    enable_thinking: bool = True,
) -> str:
    """
    Appel au LLM avec gestion d'erreur, retry, cache et enable_thinking.

    Args:
        system_prompt: Prompt système.
        user_prompt: Prompt utilisateur.
        model: Nom du modèle à utiliser. Si None, utilise MODEL_NAME.
        max_tokens: Nombre max de tokens pour la réponse.
        temperature: Température de génération.
        retries: Nombre de tentatives en cas d'erreur.
        json_mode: Si True, tente de demander du JSON au modèle.
        use_cache: Si True, utilise le cache LLM.
        enable_thinking: Si True, active le raisonnement Qwen.

    Returns:
        Réponse du LLM.
    """
    target_model = model or MODEL_NAME

    # Vérifier le cache
    cache = get_cache()
    if use_cache:
        cached = cache.get(system_prompt, user_prompt, target_model, temperature)
        if cached is not None:
            logger.debug("Cache HIT pour call_llm")
            return cached

    # Calculer les tokens disponibles
    available = estimate_available_tokens(system_prompt, user_prompt)
    if available < 100:
        raise ValueError(
            f"Le prompt est trop long pour le contexte du modèle "
            f"({MODEL_CONTEXT_WINDOW} tokens). "
            f"Tokens disponibles pour la réponse : {available}"
        )

    if max_tokens is not None:
        max_tokens = min(max_tokens, available)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    result = _execute_completion(
        messages=messages,
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=enable_thinking,
        caller_name="call_llm",
    )

    # Stocker dans le cache
    if use_cache and result:
        cache.put(system_prompt, user_prompt, target_model, temperature, result)

    return result


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    retries: int = 3,
    use_cache: bool = True,
    enable_thinking: bool = True,
) -> dict:
    """
    Appel au LLM avec parsing JSON automatique et retry si le JSON est invalide.

    Returns:
        Dict parsé depuis la réponse JSON du LLM.
    """
    json_system = system_prompt + (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )

    last_raw = None
    for attempt in range(retries):
        try:
            raw = call_llm(
                json_system, user_prompt, model, max_tokens, temperature,
                retries=2, use_cache=use_cache, enable_thinking=enable_thinking,
            )
        except Exception as e:
            print(f"LLM call failed (attempt {attempt + 1}/{retries}): {e}")
            continue

        last_raw = raw

        parsed = _parse_json_response(raw)
        if parsed is not None:
            return parsed

        # Invalider le cache pour cette entrée car la réponse n'est pas du JSON valide
        if use_cache:
            cache = get_cache()
            cache_key = cache._make_key(json_system, user_prompt, model or MODEL_NAME, temperature)
            with cache._lock:
                cache._cache.pop(cache_key, None)

        print(f"JSON parse failed (attempt {attempt + 1}/{retries}), retrying LLM call...")

    raise ValueError(
        f"Impossible de parser la réponse JSON après {retries} tentatives.\n"
        f"Dernière réponse brute :\n{(last_raw or '')[:500]}"
    )


def call_llm_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    retries: int = 3,
    enable_thinking: bool = True,
) -> str:
    """
    Appel au LLM avec historique de conversation complet.
    Pas de cache (contexte conversationnel variable).

    Args:
        messages: Liste de dicts [{"role": "system"|"user"|"assistant", "content": "..."}].
        model: Nom du modèle à utiliser. Si None, utilise MODEL_NAME.
        max_tokens: Nombre max de tokens pour la réponse.
        temperature: Température de génération.
        retries: Nombre de tentatives en cas d'erreur.
        enable_thinking: Si True, active le raisonnement Qwen.

    Returns:
        Réponse du LLM (content du dernier message assistant).
    """
    target_model = model or MODEL_NAME

    # Estimer les tokens utilisés par l'historique
    total_prompt_tokens = sum(
        count_tokens(m["content"]) if isinstance(m["content"], str) else 0
        for m in messages
    ) + SYSTEM_PROMPT_MARGIN
    available = MODEL_CONTEXT_WINDOW - total_prompt_tokens
    if available < 100:
        raise ValueError(
            f"L'historique de conversation est trop long pour le contexte du modèle "
            f"({MODEL_CONTEXT_WINDOW} tokens). "
            f"Tokens disponibles pour la réponse : {available}"
        )

    if max_tokens is not None:
        max_tokens = min(max_tokens, available)

    return _execute_completion(
        messages=messages,
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=enable_thinking,
        caller_name="call_llm_chat",
    )


def call_llm_chat_json(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    retries: int = 3,
    enable_thinking: bool = True,
) -> dict:
    """
    Appel au LLM chat avec parsing JSON automatique et retry si le JSON est invalide.

    Returns:
        Dict parsé depuis la réponse JSON du LLM.
    """
    # Ajouter l'instruction JSON au system message s'il existe
    json_messages = []
    json_suffix = (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )
    for m in messages:
        if m["role"] == "system":
            json_messages.append({"role": "system", "content": m["content"] + json_suffix})
        else:
            json_messages.append(m)

    # Si pas de system message, ajouter l'instruction au dernier user message
    if not any(m["role"] == "system" for m in json_messages):
        json_messages.append({"role": "system", "content": json_suffix.strip()})

    last_raw = None
    for attempt in range(retries):
        try:
            raw = call_llm_chat(
                json_messages, model, max_tokens, temperature,
                retries=2, enable_thinking=enable_thinking,
            )
        except Exception as e:
            print(f"LLM chat call failed (attempt {attempt + 1}/{retries}): {e}")
            continue

        last_raw = raw

        parsed = _parse_json_response(raw)
        if parsed is not None:
            return parsed

        print(f"JSON parse failed (chat attempt {attempt + 1}/{retries}), retrying LLM call...")

    raise ValueError(
        f"Impossible de parser la réponse JSON (chat) après {retries} tentatives.\n"
        f"Dernière réponse brute :\n{(last_raw or '')[:500]}"
    )


def call_llm_vision(
    system_prompt: str,
    user_prompt: str,
    images: List[str],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    retries: int = 3,
    enable_thinking: bool = False,
) -> str:
    """
    Appel au LLM avec images (format multimodal OpenAI).
    Pas de cache (images trop volumineuses).
    enable_thinking=False par défaut en mode vision.

    Args:
        system_prompt: Prompt système.
        user_prompt: Prompt utilisateur (texte).
        images: Liste de chaînes base64 JPEG.
        model: Modèle à utiliser. Si None, utilise VISION_MODEL_NAME.
        max_tokens: Nombre max de tokens pour la réponse.
        temperature: Température de génération.
        retries: Nombre de tentatives en cas d'erreur.
        enable_thinking: Si True, active le raisonnement Qwen.

    Returns:
        Réponse du LLM.
    """
    target_model = model or VISION_MODEL_NAME or MODEL_NAME

    # Construire le contenu multimodal avec séparation des pages
    user_content = [{"type": "text", "text": user_prompt}]
    for i, img_b64 in enumerate(images):
        user_content.append({"type": "text", "text": f"--- Page {i + 1} ---"})
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    return _execute_completion(
        messages=messages,
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        enable_thinking=enable_thinking,
        caller_name="call_llm_vision",
    )


def call_llm_vision_json(
    system_prompt: str,
    user_prompt: str,
    images: List[str],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    retries: int = 3,
    enable_thinking: bool = False,
) -> dict:
    """
    Appel au LLM vision avec parsing JSON automatique et retry.
    enable_thinking=False par défaut en mode vision.

    Returns:
        Dict parsé depuis la réponse JSON du LLM.
    """
    json_system = system_prompt + (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )

    last_raw = None
    for attempt in range(retries):
        try:
            raw = call_llm_vision(
                json_system, user_prompt, images, model, max_tokens, temperature,
                retries=2, enable_thinking=enable_thinking,
            )
        except Exception as e:
            print(f"LLM vision call failed (attempt {attempt + 1}/{retries}): {e}")
            continue

        last_raw = raw

        parsed = _parse_json_response(raw)
        if parsed is not None:
            return parsed

        print(f"JSON parse failed (vision attempt {attempt + 1}/{retries}), retrying LLM call...")

    raise ValueError(
        f"Impossible de parser la réponse JSON (vision) après {retries} tentatives.\n"
        f"Dernière réponse brute :\n{(last_raw or '')[:500]}"
    )


def get_model_info(model: Optional[str] = None) -> dict:
    """Retourne les informations sur le modèle configuré."""
    return {
        "model_name": model or MODEL_NAME,
        "api_base": OPENAI_API_BASE,
        "context_window": MODEL_CONTEXT_WINDOW,
        "max_response_tokens": int(MODEL_CONTEXT_WINDOW * RESPONSE_TOKEN_RATIO),
    }
