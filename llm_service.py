"""
llm_service.py — Client OpenAI pour gtp-oss-120b avec gestion des tokens et retry.
"""

import json
import os
import re
import time
from typing import Optional

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configuration depuis .env
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://OPENAI_API_BASE:8080/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gtp-oss-120b")
MODEL_CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_WINDOW", "32000"))
TIKTOKEN_ENCODING = os.getenv("TIKTOKEN_ENCODING", "cl100k_base")

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


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.7,
    retries: int = 3,
    json_mode: bool = False
) -> str:
    """
    Appel au LLM avec gestion d'erreur et retry.
    
    Args:
        system_prompt: Prompt système.
        user_prompt: Prompt utilisateur.
        model: Nom du modèle à utiliser. Si None, utilise MODEL_NAME.
        max_tokens: Nombre max de tokens pour la réponse. 
                    Si None, calculé automatiquement.
        temperature: Température de génération.
        retries: Nombre de tentatives en cas d'erreur.
        json_mode: Si True, tente de demander du JSON au modèle.
    
    Returns:
        Réponse du LLM.
    
    Raises:
        Exception: Si tous les retries échouent.
    """
    client = get_client()
    target_model = model or MODEL_NAME
    
    # Calculer les tokens disponibles
    available = estimate_available_tokens(system_prompt, user_prompt)
    if available < 100:
        raise ValueError(
            f"Le prompt est trop long pour le contexte du modèle "
            f"({MODEL_CONTEXT_WINDOW} tokens). "
            f"Tokens disponibles pour la réponse : {available}"
        )
    
    if max_tokens is None:
        # Utiliser un maximum raisonnable basé sur le contexte disponible
        max_tokens = min(available, int(MODEL_CONTEXT_WINDOW * RESPONSE_TOKEN_RATIO))
    
    max_tokens = min(max_tokens, available)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    last_error = None
    for attempt in range(retries):
        try:
            kwargs = {
                "model": target_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            
            response = client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            return content.strip() if content else ""
        
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = 2 ** attempt  # Backoff exponentiel : 1, 2, 4 sec
                time.sleep(wait_time)
    
    raise RuntimeError(
        f"Échec de l'appel LLM avec le modèle {target_model} après {retries} tentatives. "
        f"Dernière erreur : {last_error}"
    )


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: float = 0.5,
    retries: int = 3
) -> dict:
    """
    Appel au LLM avec parsing JSON automatique.
    
    Tente d'extraire un objet JSON de la réponse. Si le parsing échoue,
    essaie d'extraire le JSON d'un bloc de code markdown.
    
    Returns:
        Dict parsé depuis la réponse JSON du LLM.
    """
    # Ajouter une instruction JSON au system prompt
    json_system = system_prompt + (
        "\n\nIMPORTANT: Tu DOIS répondre UNIQUEMENT avec un objet JSON valide. "
        "Pas de texte avant ou après le JSON. Pas de bloc markdown."
    )
    
    raw = call_llm(json_system, user_prompt, model, max_tokens, temperature, retries)
    
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
    
    raise ValueError(
        f"Impossible de parser la réponse JSON du LLM.\n"
        f"Réponse brute :\n{raw[:500]}"
    )


def get_model_info(model: Optional[str] = None) -> dict:
    """Retourne les informations sur le modèle configuré."""
    return {
        "model_name": model or MODEL_NAME,
        "api_base": OPENAI_API_BASE,
        "context_window": MODEL_CONTEXT_WINDOW,
        "max_response_tokens": int(MODEL_CONTEXT_WINDOW * RESPONSE_TOKEN_RATIO),
    }

