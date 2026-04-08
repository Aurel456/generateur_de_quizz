"""
llm_service.py — Client OpenAI pour gtp-oss-120b avec gestion des tokens, retry,
cache SHA256 et tracking des tokens.
"""

import json
import logging
import os
import re
import time
from typing import Callable, Dict, Generator, List, Optional, Tuple

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from core.llm_cache import get_cache
from core.token_tracker import log_token_usage

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration depuis .env — Modèle texte
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://OPENAI_API_BASE:8080/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "OPENAI_API_KEY")
TEXT_MODEL_NAME = os.getenv("TEXT_MODEL_NAME", "Gpt-oss-120b")
TEXT_MODEL_CONTEXT = int(os.getenv("TEXT_MODEL_CONTEXT", "32000"))
TIKTOKEN_ENCODING = os.getenv("TIKTOKEN_ENCODING", "cl100k_base")

# Rétro-compatibilité (anciens noms MODEL_NAME / MODEL_CONTEXT_WINDOW)
if not os.getenv("TEXT_MODEL_NAME") and os.getenv("MODEL_NAME"):
    TEXT_MODEL_NAME = os.getenv("MODEL_NAME")
if not os.getenv("TEXT_MODEL_CONTEXT") and os.getenv("MODEL_CONTEXT_WINDOW"):
    TEXT_MODEL_CONTEXT = int(os.getenv("MODEL_CONTEXT_WINDOW"))

# Configuration Vision — supporte un seul modèle ou une liste JSON
_raw_vision_model = os.getenv("VISION_MODEL_NAME", "")
if _raw_vision_model.strip().startswith("["):
    try:
        VISION_MODEL_NAMES: List[str] = json.loads(_raw_vision_model)
    except json.JSONDecodeError:
        VISION_MODEL_NAMES = [_raw_vision_model] if _raw_vision_model else []
else:
    VISION_MODEL_NAMES = [_raw_vision_model] if _raw_vision_model else []
VISION_MODEL_NAME = VISION_MODEL_NAMES[0] if VISION_MODEL_NAMES else ""
VISION_MODEL_CONTEXT = int(os.getenv("VISION_MODEL_CONTEXT", "262000"))

# Rétro-compat vision (ancien nom VISION_CONTEXT_WINDOW)
if not os.getenv("VISION_MODEL_CONTEXT") and os.getenv("VISION_CONTEXT_WINDOW"):
    VISION_MODEL_CONTEXT = int(os.getenv("VISION_CONTEXT_WINDOW"))

# Constantes One-shot (dérivées de VISION_MODEL_CONTEXT)
ONESHOT_RESERVE_TOKENS = 50000
ONESHOT_DPI = 85
ONESHOT_SLICE_TOKENS = 50000

# Aliases rétro-compatibles pour le code existant
MODEL_NAME = TEXT_MODEL_NAME
MODEL_CONTEXT_WINDOW = TEXT_MODEL_CONTEXT
VISION_CONTEXT_WINDOW = VISION_MODEL_CONTEXT

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


# ── Streaming ────────────────────────────────────────────────────────────────

def _execute_completion_stream(
    messages: list,
    model: str,
    temperature: float,
    max_tokens: Optional[int] = None,
    enable_thinking: bool = True,
    caller_name: str = "call_llm_stream",
) -> Generator[str, None, None]:
    """
    Exécute un appel chat.completions.create en mode streaming.
    Yields les fragments de texte au fur et à mesure.
    """
    client = get_client()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        "extra_body": {
            "enable_thinking": enable_thinking,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
        },
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    stream = client.chat.completions.create(**kwargs)
    total_content = ""
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            total_content += delta
            yield delta

    # Token tracking estimé (le streaming ne fournit pas toujours usage)
    output_tokens = count_tokens(total_content) if total_content else 0
    log_token_usage(caller_name, model, 0, output_tokens)


def call_llm_stream(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    enable_thinking: bool = True,
) -> Generator[str, None, None]:
    """
    Appel LLM en mode streaming. Yields les fragments de texte.
    Pas de cache (le streaming est utilisé pour l'affichage progressif).
    """
    target_model = model or TEXT_MODEL_NAME
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    yield from _execute_completion_stream(
        messages=messages,
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
        caller_name="call_llm_stream",
    )


def call_llm_vision_stream(
    system_prompt: str,
    user_prompt: str,
    images: List[str],
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    enable_thinking: bool = False,
) -> Generator[str, None, None]:
    """
    Appel LLM vision en mode streaming. Yields les fragments de texte.
    """
    target_model = model or VISION_MODEL_NAME or TEXT_MODEL_NAME
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
    yield from _execute_completion_stream(
        messages=messages,
        model=target_model,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
        caller_name="call_llm_vision_stream",
    )


# ── Streaming via API Responses (/v1/responses) ────────────────────────────

# Flag global : désactivé si le serveur ne supporte pas l'API responses
_responses_api_supported = True


def _execute_responses_stream(
    messages: list,
    model: str,
    temperature: float,
    text_format: Optional[type] = None,
    max_tokens: Optional[int] = None,
    caller_name: str = "call_llm_responses_stream",
) -> Generator[str, None, None]:
    """
    Exécute un appel via l'API /v1/responses en mode streaming.
    Utilise text_format (Pydantic BaseModel) pour garantir un JSON valide.
    Yields les fragments de texte au fur et à mesure.
    """
    client = get_client()
    kwargs = {
        "model": model,
        "input": messages,
        "temperature": temperature,
        "stream": True,
    }
    if text_format is not None:
        kwargs["text"] = {"format": {"type": "json_schema", "schema": text_format.model_json_schema()}}
    if max_tokens is not None:
        kwargs["max_output_tokens"] = max_tokens

    total_content = ""
    with client.responses.create(**kwargs) as stream:
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = event.delta
                total_content += delta
                yield delta

    output_tokens = count_tokens(total_content) if total_content else 0
    log_token_usage(caller_name, model, 0, output_tokens)


def call_llm_responses_stream(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    text_format: Optional[type] = None,
    images: Optional[List[str]] = None,
) -> Generator[str, None, None]:
    """
    Appel LLM via API responses en mode streaming.
    Supporte vision (images base64) et structured output (text_format Pydantic).
    """
    target_model = model or TEXT_MODEL_NAME
    messages = [{"role": "system", "content": system_prompt}]

    if images:
        user_content = [{"type": "input_text", "text": user_prompt}]
        for i, img_b64 in enumerate(images):
            user_content.append({"type": "input_text", "text": f"--- Page {i + 1} ---"})
            user_content.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{img_b64}",
            })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    yield from _execute_responses_stream(
        messages=messages,
        model=target_model,
        temperature=temperature,
        text_format=text_format,
        max_tokens=max_tokens,
        caller_name="call_llm_responses_stream",
    )


# ── Extraction JSON incrémentale ────────────────────────────────────────────

def _scan_complete_brace_object(text: str, start: int) -> int:
    """
    À partir de text[start] (qui doit être '{'), retourne l'index du '}' fermant.
    Retourne -1 si l'objet est incomplet (le stream n'a pas encore tout livré).
    Gère les strings avec échappement.
    """
    n = len(text)
    depth = 0
    in_string = False
    escape_next = False
    j = start
    while j < n:
        ch = text[j]
        if escape_next:
            escape_next = False
        elif ch == '\\' and in_string:
            escape_next = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return j
        j += 1
    return -1


def _stream_extract_array_items(
    text: str,
    array_key: str,
    last_pos: int = 0,
) -> Tuple[List[dict], int]:
    """
    Extrait des objets JSON complets depuis un array nommé en cours de streaming.

    Le LLM renvoie typiquement {"questions": [{...}, {...}, ...]}.
    Au lieu d'attendre l'objet racine complet, on cherche directement les items
    à l'intérieur du tableau nommé `array_key`.

    Returns:
        (liste d'objets parsés, nouvel index de scan dans le texte)
    """
    key_pattern = f'"{array_key}"'
    key_pos = text.find(key_pattern)
    if key_pos == -1:
        return [], last_pos

    bracket_pos = text.find('[', key_pos + len(key_pattern))
    if bracket_pos == -1:
        return [], last_pos

    scan_from = max(bracket_pos + 1, last_pos)
    objects: List[dict] = []
    i = scan_from
    n = len(text)

    while i < n:
        # Sauter espaces et virgules séparant les items
        while i < n and text[i] in ' \t\n\r,':
            i += 1
        if i >= n:
            break
        if text[i] == ']':  # Fin du tableau
            break
        if text[i] != '{':
            i += 1
            continue

        found_end = _scan_complete_brace_object(text, i)
        if found_end == -1:
            break  # Item incomplet — attendre plus de données

        candidate = text[i:found_end + 1]
        try:
            obj = json.loads(candidate)
            objects.append(obj)
            i = found_end + 1
        except json.JSONDecodeError:
            i += 1  # Sauter ce '{' et continuer

    return objects, i


def _extract_complete_json_objects(text: str, last_extracted: int = 0) -> Tuple[List[dict], int]:
    """
    Fallback : extrait des objets JSON de niveau racine depuis un texte streamé.
    Utilisé quand array_key est inconnu.
    """
    objects: List[dict] = []
    i = last_extracted
    n = len(text)

    while i < n:
        start = text.find('{', i)
        if start == -1:
            break
        found_end = _scan_complete_brace_object(text, start)
        if found_end == -1:
            break
        candidate = text[start:found_end + 1]
        try:
            obj = json.loads(candidate)
            objects.append(obj)
            i = found_end + 1
        except json.JSONDecodeError:
            i = start + 1

    return objects, i


def call_llm_json_stream(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    enable_thinking: bool = True,
    on_object: Optional[Callable[[dict], None]] = None,
    vision_mode: bool = False,
    images: Optional[List[str]] = None,
    array_key: Optional[str] = None,
    text_format: Optional[type] = None,
) -> dict:
    """
    Appel LLM JSON en mode streaming avec extraction incrémentale des objets.

    Si text_format (Pydantic BaseModel) est fourni ET l'API responses est disponible,
    utilise /v1/responses avec structured output (JSON garanti valide).
    Sinon, fallback vers chat.completions.create classique.

    Accumule le texte streamé et extrait les objets JSON complets au fur et à mesure.
    Appelle on_object(obj) pour chaque objet JSON complet détecté dans un array.

    Returns:
        Le dict complet parsé depuis la réponse finale.
    """
    global _responses_api_supported

    json_system = system_prompt + (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )

    accumulated = ""
    json_text = ""  # Texte sans les blocs <think>, utilisé pour l'extraction
    last_extracted = 0
    _in_think = False
    _used_responses_api = False

    try:
        # ── Tenter l'API responses si text_format est fourni ──────────────
        if text_format is not None and _responses_api_supported:
            try:
                stream_gen = call_llm_responses_stream(
                    system_prompt, user_prompt,
                    model=model, max_tokens=max_tokens,
                    temperature=temperature,
                    text_format=text_format,
                    images=images if (vision_mode and images) else None,
                )
                _used_responses_api = True
            except Exception as e:
                logger.warning(f"API responses indisponible, fallback chat.completions: {e}")
                _responses_api_supported = False
                _used_responses_api = False

        # ── Fallback vers chat.completions ────────────────────────────────
        if not _used_responses_api:
            if vision_mode and images:
                stream_gen = call_llm_vision_stream(
                    json_system, user_prompt, images, model, max_tokens, temperature,
                    enable_thinking=enable_thinking,
                )
            else:
                stream_gen = call_llm_stream(
                    json_system, user_prompt, model, max_tokens, temperature,
                    enable_thinking=enable_thinking,
                )

        for chunk in stream_gen:
            accumulated += chunk

            if _used_responses_api:
                # API responses : pas de <think> blocks, le JSON est garanti valide
                json_text += chunk
            else:
                # chat.completions : filtrer les blocs <think>
                if '<think>' in chunk:
                    _in_think = True
                if '</think>' in accumulated and _in_think:
                    _in_think = False
                    json_text = re.sub(r'<think>.*?</think>', '', accumulated, flags=re.DOTALL)
                    last_extracted = 0
                    continue
                if _in_think:
                    continue
                json_text += chunk

            # Extraction incrémentale des objets JSON
            if on_object:
                if array_key:
                    new_objects, last_extracted = _stream_extract_array_items(json_text, array_key, last_extracted)
                else:
                    new_objects, last_extracted = _extract_complete_json_objects(json_text, last_extracted)
                for obj in new_objects:
                    on_object(obj)

    except Exception as e:
        logger.warning(f"Streaming failed, falling back to non-streaming: {e}")
        # Fallback vers non-streaming
        if vision_mode and images:
            return call_llm_vision_json(
                system_prompt, user_prompt, images, model, max_tokens, temperature,
                enable_thinking=enable_thinking,
            )
        else:
            return call_llm_json(
                system_prompt, user_prompt, model, max_tokens, temperature,
                enable_thinking=enable_thinking,
            )

    # Parse final complet — essayer d'abord le texte nettoyé, puis le brut
    final_text = json_text.strip() or accumulated
    parsed = _parse_json_response(final_text)
    if parsed is None:
        parsed = _parse_json_response(accumulated)
    if parsed is not None:
        return parsed

    raise ValueError(
        f"Impossible de parser la réponse JSON (stream) après streaming.\n"
        f"Réponse brute :\n{accumulated[:500]}"
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
            cache_key = cache._make_key(json_system, user_prompt, model or str(TEXT_MODEL_NAME), temperature)
            with cache._lock:
                cache._cache.pop(cache_key, None)

        print(f"JSON parse failed (attempt {attempt + 1}/{retries}), retrying...")

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

        print(f"JSON parse failed (chat attempt {attempt + 1}/{retries}), retrying...")

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

        print(f"JSON parse failed (vision attempt {attempt + 1}/{retries}), retrying...")

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
