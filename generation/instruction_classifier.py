"""
instruction_classifier.py — Classe le texte libre de l'utilisateur en deux catégories.

Le formateur saisit une consigne unique. Le LLM la découpe en :
- generation_instructions : consignes de style/formulation injectées dans le prompt de génération.
- chunk_filter_instructions : périmètre documentaire utilisé pour filtrer les chunks.

Un même texte peut contenir les deux aspects ; chacun est extrait indépendamment.
"""

import logging
from typing import Optional, Tuple

from core.llm_service import call_llm_json

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "Tu es un assistant qui classe la consigne d'un formateur en deux catégories "
    "pour un système de génération de quiz/exercices à partir de documents.\n\n"
    "CATÉGORIES :\n"
    "1. generation_instructions — Consignes qui influencent COMMENT les questions/exercices "
    "sont formulés (style, focus thématique au sein du contenu retenu, choix de pièges, ton, "
    "types de questions à privilégier ou éviter, contraintes de formulation). Ces consignes "
    "sont injectées dans le prompt de génération de chaque question.\n"
    "2. chunk_filter_instructions — Consignes qui définissent QUELLE PARTIE du document "
    "doit être utilisée (sujets/chapitres/sections à inclure ou exclure, périmètre documentaire, "
    "pages ou thèmes précis à couvrir). Utilisées en amont pour filtrer les chunks pertinents.\n\n"
    "RÈGLES :\n"
    "- Un même texte peut alimenter les deux catégories. Extraire chaque aspect dans la bonne "
    "catégorie, sans dupliquer bêtement.\n"
    "- Si une consigne est purement stylistique ou de formulation → generation_instructions uniquement.\n"
    "- Si une consigne désigne explicitement un sujet/chapitre/partie à couvrir → chunk_filter_instructions.\n"
    "- Si une consigne mélange les deux (ex : « focalise sur les procédures de contrôle et "
    "évite les questions sur les dates »), splitte : le périmètre dans chunk_filter_instructions, "
    "le reste dans generation_instructions.\n"
    "- Conserver la langue d'origine de l'utilisateur.\n"
    "- Si une catégorie est absente du texte, retourne une chaîne vide pour cette catégorie.\n\n"
    "FORMAT DE RÉPONSE (JSON strict) :\n"
    '{"generation_instructions": "...", "chunk_filter_instructions": "...", "reasoning": "Explication courte"}'
)


def classify_user_input(
    text: str,
    model: Optional[str] = None,
    enable_thinking: bool = False,
) -> Tuple[str, str]:
    """
    Classe le texte libre du formateur en deux catégories.

    Args:
        text: Consigne libre du formateur.
        model: Modèle LLM à utiliser.
        enable_thinking: Mode thinking (désactivé par défaut pour cette tâche simple).

    Returns:
        Tuple (generation_instructions, chunk_filter_instructions). Chaînes vides si
        le texte est vide ou si la classification échoue.
    """
    if not text or not text.strip():
        return "", ""

    user_prompt = f"TEXTE À CLASSER :\n{text.strip()}"

    try:
        result = call_llm_json(
            _SYSTEM_PROMPT,
            user_prompt,
            model=model,
            temperature=0.1,
            enable_thinking=enable_thinking,
        )
    except Exception as e:
        logger.warning("Classification échouée, fallback texte brut dans les deux : %s", e)
        return text.strip(), text.strip()

    generation = (result.get("generation_instructions") or "").strip()
    chunk_filter = (result.get("chunk_filter_instructions") or "").strip()
    reasoning = (result.get("reasoning") or "").strip()

    if reasoning:
        logger.info("Classification reasoning: %s", reasoning)

    if not generation and not chunk_filter:
        logger.warning("Classification vide, fallback texte brut dans les deux catégories")
        return text.strip(), text.strip()

    return generation, chunk_filter
