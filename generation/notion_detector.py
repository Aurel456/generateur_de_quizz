"""
notion_detector.py — Détection et édition des notions fondamentales via LLM.

Les notions fondamentales sont les concepts, définitions, théorèmes et principes
clés identifiés dans les documents. Elles guident la génération de quizz et exercices.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict

from core.llm_service import call_llm_json, call_llm_vision_json, call_llm
from processing.document_processor import TextChunk


@dataclass
class Notion:
    """Une notion fondamentale identifiée dans les documents."""
    title: str
    description: str
    source_document: str = ""
    source_pages: List[int] = field(default_factory=list)
    enabled: bool = True
    category: str = ""
    question_count: int = 0  # Nombre de questions générées couvrant cette notion


def _build_detection_prompt_incremental(
    chunk: TextChunk,
    existing_notions: List[Notion]
) -> tuple:
    """Construit le prompt pour détecter les notions d'un chunk, en tenant compte des notions déjà trouvées."""

    doc_label = f"[Document: {chunk.source_document}]" if chunk.source_document else ""
    pages_label = f"[Pages: {', '.join(map(str, chunk.source_pages))}]"
    chunk_context = f"{doc_label} {pages_label}\n{chunk.text}"

    # Sérialiser les notions existantes
    existing_text = ""
    if existing_notions:
        existing_text = "\n\nNOTIONS FONDAMENTALES DÉJÀ IDENTIFIÉES :\n"
        for i, n in enumerate(existing_notions, 1):
            src = ""
            if n.source_document:
                src += f" (Source: {n.source_document}"
                if n.source_pages:
                    src += f", p. {', '.join(map(str, n.source_pages))}"
                src += ")"
            existing_text += f"{i}. {n.title} : {n.description}{src}\n"

    system_prompt = f"""Tu es un expert pédagogique. Tu dois analyser un nouveau passage de texte et mettre à jour la liste des NOTIONS FONDAMENTALES.

Les notions fondamentales sont :
- Les concepts clés et définitions essentielles
- Les théorèmes, lois, principes importants
- Les formules et méthodes fondamentales
- Les idées directrices et concepts structurants du document

RÈGLES :
1. CONSERVE toutes les notions existantes (tu peux enrichir leur description si le nouveau texte apporte des précisions)
2. AJOUTE les nouvelles notions identifiées dans ce passage
3. FUSIONNE les notions redondantes ou similaires
4. Chaque notion doit avoir un titre concis et une description claire
5. Cite le document source et les pages où la notion apparaît
6. Ordonne les notions par importance pédagogique
7. Pour chaque notion, attribue une catégorie thématique (ex: "Fondements", "Procédures", "Calculs", "Cas particuliers", "Définitions") qui regroupe logiquement les notions selon la structure du document.

FORMAT DE RÉPONSE (JSON strict) :
{{
    "notions": [
        {{
            "title": "Titre concis de la notion",
            "description": "Description claire de la notion en 1-3 phrases",
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2, 3],
            "category": "Fondements"
        }}
    ]
}}"""

    user_prompt = f"""Voici le nouveau passage à analyser :

---
{chunk_context}
---
{existing_text}
Retourne la liste COMPLÈTE et mise à jour des notions fondamentales (existantes + nouvelles de ce passage)."""

    return system_prompt, user_prompt


def _parse_notions_response(result: dict) -> List[Notion]:
    """Parse la réponse JSON du LLM en liste de Notion."""
    notions = []
    for n_data in result.get("notions", []):
        try:
            notion = Notion(
                title=n_data["title"],
                description=n_data.get("description", ""),
                source_document=n_data.get("source_document", ""),
                source_pages=n_data.get("source_pages", []),
                enabled=True,
                category=n_data.get("category", ""),
            )
            notions.append(notion)
        except (KeyError, TypeError):
            continue
    return notions


def detect_notions(
    chunks: List[TextChunk],
    model: Optional[str] = None,
    progress_callback=None,
    vision_mode: bool = False,
    enable_thinking: bool = True,
) -> List[Notion]:
    """
    Détecte les notions fondamentales de manière itérative, chunk par chunk.

    À chaque chunk, le LLM reçoit les notions déjà trouvées et le nouveau texte,
    puis retourne la liste mise à jour (notions existantes enrichies + nouvelles notions).

    Note: pas de batch possible ici (chaque chunk dépend des notions précédentes).

    Args:
        chunks: Liste de TextChunk à analyser.
        model: Modèle LLM à utiliser.
        progress_callback: Fonction callback(current, total) pour la progression.
        vision_mode: Si True, envoie les images des chunks au modèle vision.

    Returns:
        Liste de Notion détectées et consolidées.
    """
    if not chunks:
        return []

    notions: List[Notion] = []

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i, len(chunks))

        system_prompt, user_prompt = _build_detection_prompt_incremental(chunk, notions)

        try:
            if vision_mode and chunk.page_images:
                result = call_llm_vision_json(system_prompt, user_prompt, chunk.page_images, model=model, temperature=0.3, enable_thinking=enable_thinking)
            else:
                result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)
            notions = _parse_notions_response(result)
        except Exception as e:
            print(f"Erreur détection notions chunk {i}: {e}")
            continue

    if progress_callback:
        progress_callback(len(chunks), len(chunks))

    return notions


def edit_notions_with_llm(
    current_notions: List[Notion],
    user_instruction: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
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

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)

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


def merge_similar_notions(
    notions: List[Notion],
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> tuple:
    """
    Fusionne les notions similaires ou redondantes entre elles via le LLM.

    Returns:
        (liste_fusionnée, résumé_des_fusions)
    """
    if not notions or len(notions) <= 1:
        return notions, "Aucune fusion nécessaire."

    notions_text = "\n".join(
        f"{i}. [{n.title}] : {n.description}"
        + (f" (Source: {n.source_document}, p. {', '.join(map(str, n.source_pages))})" if n.source_document else "")
        for i, n in enumerate(notions)
    )

    system_prompt = """Tu es un expert pédagogique. Tu dois regrouper et fusionner les notions fondamentales qui sont similaires, redondantes ou étroitement liées.

RÈGLES :
1. Fusionne les notions qui traitent du même concept sous des angles différents
2. Combine les descriptions pour ne rien perdre d'important
3. Conserve toutes les pages sources des notions fusionnées
4. Garde les notions véritablement distinctes séparées
5. Le résultat doit être une liste PLUS COURTE et plus claire

FORMAT DE RÉPONSE (JSON strict) :
{
    "merged_notions": [
        {
            "title": "Titre de la notion fusionnée ou conservée",
            "description": "Description complète combinant les infos pertinentes",
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2, 3]
        }
    ],
    "merge_summary": "Résumé court des fusions effectuées (ex: 'Fusionné 3 notions sur les dérivées en 1')"
}"""

    user_prompt = (
        f"Voici les {len(notions)} notions à analyser et regrouper :\n\n"
        f"{notions_text}\n\n"
        "Fusionne les notions similaires ou redondantes. Retourne une liste consolidée."
    )

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)

    merged = []
    for n_data in result.get("merged_notions", []):
        try:
            merged.append(Notion(
                title=n_data["title"],
                description=n_data.get("description", ""),
                source_document=n_data.get("source_document", ""),
                source_pages=n_data.get("source_pages", []),
                enabled=True,
            ))
        except (KeyError, TypeError):
            continue

    summary = result.get("merge_summary", f"{len(notions)} → {len(merged)} notions")
    return merged, summary


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
