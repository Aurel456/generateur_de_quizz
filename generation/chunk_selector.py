"""
chunk_selector.py — Sélection intelligente des chunks les plus pertinents.

Avant la génération, envoie la liste des notions et le contexte utilisateur au LLM
pour qu'il choisisse quels chunks analyser en priorité.
"""

import logging
from typing import List, Optional

from core.llm_service import call_llm_json

logger = logging.getLogger(__name__)


def select_relevant_chunks(
    chunks,
    notions: Optional[list] = None,
    user_context: str = "",
    model: Optional[str] = None,
    max_chunks: Optional[int] = None,
) -> list:
    """
    Demande au LLM de sélectionner les chunks les plus pertinents selon les notions
    et le contexte utilisateur. Retourne les chunks triés par pertinence.

    Si user_context est vide ou s'il n'y a qu'un seul chunk, retourne tous les chunks.

    Args:
        chunks: Liste de TextChunk.
        notions: Liste de Notion (utilisées pour guider la sélection).
        user_context: Texte libre du formateur décrivant ce qu'il veut couvrir.
        model: Modèle LLM à utiliser.
        max_chunks: Nombre maximum de chunks à retourner (None = tous les sélectionnés).

    Returns:
        Liste de TextChunk triée par pertinence (sous-ensemble ou totalité).
    """
    if not chunks or len(chunks) <= 1 or not user_context.strip():
        return list(chunks)

    # Construire la description de chaque chunk
    chunk_descriptions = []
    for i, chunk in enumerate(chunks):
        pages_str = f"p.{','.join(map(str, chunk.source_pages))}" if chunk.source_pages else f"chunk {i+1}"
        doc_str = f" [{chunk.source_document}]" if chunk.source_document else ""
        preview = chunk.text[:200].replace("\n", " ").strip()
        chunk_descriptions.append(
            f"Chunk {i}: {pages_str}{doc_str} — {preview}…"
        )

    notions_block = ""
    if notions:
        active_notions = [n for n in notions if getattr(n, "enabled", True)]
        if active_notions:
            notion_lines = []
            for n in active_notions[:30]:
                pages = getattr(n, "source_pages", None) or []
                doc = getattr(n, "source_document", "") or ""
                desc = (getattr(n, "description", "") or "").strip()
                src_parts = []
                if doc:
                    src_parts.append(doc)
                if pages:
                    src_parts.append(f"p.{','.join(map(str, pages))}")
                src_str = f" [{' — '.join(src_parts)}]" if src_parts else ""
                desc_str = f" — {desc}" if desc else ""
                notion_lines.append(f"- {n.title}{src_str}{desc_str}")
            notions_block = "\n\nNOTIONS À COUVRIR :\n" + "\n".join(notion_lines)

    system_prompt = (
        "Tu es un assistant pédagogique. On te donne une liste de chunks de documents "
        "et un contexte utilisateur décrivant ce que le formateur souhaite couvrir. "
        "Sélectionne les indices des chunks les plus pertinents pour ce contexte.\n\n"
        "FORMAT DE RÉPONSE (JSON strict) :\n"
        '{"selected_indices": [0, 2, 5], "reasoning": "Explication courte"}'
    )

    chunks_text = "\n".join(chunk_descriptions)
    user_prompt = (
        f"CHUNKS DISPONIBLES ({len(chunks)} au total) :\n{chunks_text}"
        f"{notions_block}\n\n"
        f"CONTEXTE UTILISATEUR : {user_context.strip()}\n\n"
        f"Sélectionne les indices des chunks les plus pertinents pour ce contexte. "
        f"Inclus tous les chunks nécessaires pour couvrir le sujet demandé — "
        f"ne sois pas trop restrictif."
    )

    try:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.2)
        selected_indices = result.get("selected_indices", [])
        reasoning = result.get("reasoning", "")

        if reasoning:
            logger.info("Chunk selection reasoning: %s", reasoning)

        # Valider et filtrer les indices
        valid_indices = [i for i in selected_indices if isinstance(i, int) and 0 <= i < len(chunks)]

        if not valid_indices:
            logger.warning("Aucun chunk valide sélectionné, utilisation de tous les chunks.")
            return list(chunks)

        # Appliquer max_chunks si spécifié
        if max_chunks and len(valid_indices) > max_chunks:
            valid_indices = valid_indices[:max_chunks]

        selected = [chunks[i] for i in valid_indices]
        logger.info("Chunks sélectionnés : %d/%d — indices %s", len(selected), len(chunks), valid_indices)
        return selected

    except Exception as e:
        logger.warning("Erreur sélection chunks, utilisation de tous les chunks : %s", e)
        return list(chunks)
