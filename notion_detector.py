"""
notion_detector.py — Détection et édition des notions fondamentales via LLM.

Les notions fondamentales sont les concepts, définitions, théorèmes et principes
clés identifiés dans les documents. Elles guident la génération de quizz et exercices.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict

from llm_service import call_llm_json, call_llm
from document_processor import TextChunk


@dataclass
class Notion:
    """Une notion fondamentale identifiée dans les documents."""
    title: str
    description: str
    source_document: str = ""
    source_pages: List[int] = field(default_factory=list)
    enabled: bool = True


def _build_detection_prompt(chunks: List[TextChunk]) -> tuple:
    """Construit le prompt pour détecter les notions fondamentales."""

    # Construire le contexte avec les chunks (limiter pour ne pas dépasser le contexte)
    context_parts = []
    for chunk in chunks:
        doc_label = f"[Document: {chunk.source_document}]" if chunk.source_document else ""
        pages_label = f"[Pages: {', '.join(map(str, chunk.source_pages))}]"
        context_parts.append(f"{doc_label} {pages_label}\n{chunk.text}")

    context = "\n\n---\n\n".join(context_parts)

    system_prompt = """Tu es un expert pédagogique. Tu dois identifier les NOTIONS FONDAMENTALES présentes dans les documents fournis.

Les notions fondamentales sont :
- Les concepts clés et définitions essentielles
- Les théorèmes, lois, principes importants
- Les formules et méthodes fondamentales
- Les idées directrices et concepts structurants du document

RÈGLES :
1. Identifie entre 5 et 20 notions selon la richesse du contenu
2. Chaque notion doit avoir un titre concis et une description claire
3. Cite le document source et les pages où la notion apparaît
4. Ordonne les notions par importance pédagogique

FORMAT DE RÉPONSE (JSON strict) :
{
    "notions": [
        {
            "title": "Titre concis de la notion",
            "description": "Description claire de la notion en 1-3 phrases",
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2, 3]
        }
    ]
}"""

    user_prompt = f"""Voici le contenu des documents :

---
{context}
---

Identifie les notions fondamentales de ces documents."""

    return system_prompt, user_prompt


def detect_notions(
    chunks: List[TextChunk],
    model: Optional[str] = None
) -> List[Notion]:
    """
    Détecte les notions fondamentales à partir des chunks de texte.

    Args:
        chunks: Liste de TextChunk à analyser.
        model: Modèle LLM à utiliser.

    Returns:
        Liste de Notion détectées.
    """
    if not chunks:
        return []

    system_prompt, user_prompt = _build_detection_prompt(chunks)

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3)

    notions = []
    for n_data in result.get("notions", []):
        try:
            notion = Notion(
                title=n_data["title"],
                description=n_data.get("description", ""),
                source_document=n_data.get("source_document", ""),
                source_pages=n_data.get("source_pages", []),
                enabled=True,
            )
            notions.append(notion)
        except (KeyError, TypeError):
            continue

    return notions


def edit_notions_with_llm(
    current_notions: List[Notion],
    user_instruction: str,
    model: Optional[str] = None
) -> List[Notion]:
    """
    Permet à l'utilisateur de modifier les notions via une instruction en langage naturel.

    Args:
        current_notions: Liste des notions actuelles.
        user_instruction: Instruction de l'utilisateur (ex: "Ajoute une notion sur X").
        model: Modèle LLM à utiliser.

    Returns:
        Liste de Notion mise à jour.
    """
    # Sérialiser les notions actuelles
    notions_text = ""
    for i, n in enumerate(current_notions, 1):
        status = "✅ activée" if n.enabled else "❌ désactivée"
        notions_text += (
            f"{i}. [{status}] **{n.title}**\n"
            f"   Description : {n.description}\n"
            f"   Source : {n.source_document}, pages {n.source_pages}\n\n"
        )

    system_prompt = """Tu es un assistant pédagogique. L'utilisateur te donne une liste de notions fondamentales et une instruction pour les modifier.

Tu dois retourner la liste COMPLÈTE des notions après modification.

FORMAT DE RÉPONSE (JSON strict) :
{
    "notions": [
        {
            "title": "Titre de la notion",
            "description": "Description de la notion",
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2],
            "enabled": true
        }
    ],
    "explanation": "Explication de ce qui a été modifié"
}"""

    user_prompt = f"""Voici les notions actuelles :

{notions_text}

INSTRUCTION DE L'UTILISATEUR : {user_instruction}

Applique cette instruction et retourne la liste complète mise à jour."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3)

    notions = []
    for n_data in result.get("notions", []):
        try:
            notion = Notion(
                title=n_data["title"],
                description=n_data.get("description", ""),
                source_document=n_data.get("source_document", ""),
                source_pages=n_data.get("source_pages", []),
                enabled=n_data.get("enabled", True),
            )
            notions.append(notion)
        except (KeyError, TypeError):
            continue

    explanation = result.get("explanation", "")
    return notions, explanation


def notions_to_prompt_text(notions: List[Notion]) -> str:
    """
    Convertit les notions activées en texte à injecter dans les prompts de génération.

    Args:
        notions: Liste de Notion.

    Returns:
        Texte formaté pour inclusion dans un prompt LLM.
    """
    active = [n for n in notions if n.enabled]
    if not active:
        return ""

    lines = ["NOTIONS FONDAMENTALES À COUVRIR :"]
    for i, n in enumerate(active, 1):
        lines.append(f"{i}. {n.title} : {n.description}")

    return "\n".join(lines)
