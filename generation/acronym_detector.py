"""
acronym_detector.py — Détection et gestion des acronymes à partir de documents et d'un fichier de référence.

Les acronymes sont détectés par scan regex contre un dictionnaire de référence (acronyms.json),
puis optionnellement enrichis par le LLM pour les acronymes inconnus.
Ils sont injectés comme glossaire dans les prompts de génération quiz/exercices.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.llm_service import call_llm_json
from processing.document_processor import TextChunk


@dataclass
class Acronym:
    """Un acronyme identifié dans les documents."""
    acronym: str              # ex: "TVA"
    definition: str           # Définition principale sélectionnée
    all_definitions: List[str] = field(default_factory=list)  # Toutes les définitions du fichier référence
    source_document: str = ""
    source_pages: List[int] = field(default_factory=list)
    enabled: bool = True
    from_reference: bool = True  # False si ajouté manuellement ou détecté par LLM


def load_acronym_reference(path: str) -> Dict[str, List[str]]:
    """
    Charge le fichier de référence des acronymes.

    Args:
        path: Chemin vers le fichier acronyms.json

    Returns:
        Dict {acronyme: [définitions]}
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    reference = {}
    for entry in data.get("acronyms", []):
        acronym = entry.get("acronym", "").strip()
        definitions = entry.get("definitions", [])
        if acronym and definitions:
            reference[acronym] = definitions
    return reference


def detect_acronyms_from_text(
    chunks: List[TextChunk],
    reference: Dict[str, List[str]],
    progress_callback=None,
) -> List[Acronym]:
    """
    Détecte les acronymes présents dans les chunks par scan regex contre le dictionnaire de référence.

    Args:
        chunks: Liste de TextChunk à analyser.
        reference: Dict {acronyme: [définitions]} chargé depuis acronyms.json.
        progress_callback: Fonction callback(current, total) pour la progression.

    Returns:
        Liste d'Acronym détectés dans les documents, dédupliqués.
    """
    if not chunks or not reference:
        return []

    # Compiler un pattern unique pour tous les acronymes de référence
    # Trier par longueur décroissante pour matcher les plus longs d'abord
    sorted_acronyms = sorted(reference.keys(), key=len, reverse=True)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in sorted_acronyms) + r")\b"
    )

    # Scanner chaque chunk et collecter les occurrences
    found: Dict[str, Dict] = {}  # acronym -> {source_documents, source_pages}

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i, len(chunks))

        matches = set(pattern.findall(chunk.text))
        for acronym in matches:
            if acronym not in found:
                found[acronym] = {"source_documents": set(), "source_pages": set()}
            if chunk.source_document:
                found[acronym]["source_documents"].add(chunk.source_document)
            found[acronym]["source_pages"].update(chunk.source_pages)

    if progress_callback:
        progress_callback(len(chunks), len(chunks))

    # Construire les objets Acronym
    acronyms = []
    for acronym in sorted(found.keys()):
        definitions = reference[acronym]
        docs = found[acronym]["source_documents"]
        pages = sorted(found[acronym]["source_pages"])
        acronyms.append(Acronym(
            acronym=acronym,
            definition=definitions[0],
            all_definitions=definitions,
            source_document=", ".join(sorted(docs)) if docs else "",
            source_pages=pages,
            enabled=True,
            from_reference=True,
        ))

    return acronyms


def detect_unknown_acronyms_with_llm(
    chunks: List[TextChunk],
    known_acronyms: List[str],
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> List[Acronym]:
    """
    Utilise le LLM pour détecter des acronymes NON présents dans le dictionnaire de référence.

    Args:
        chunks: Liste de TextChunk à analyser.
        known_acronyms: Liste des acronymes déjà connus (référence + détectés).
        model: Modèle LLM à utiliser.
        enable_thinking: Activer le mode raisonnement.

    Returns:
        Liste d'Acronym inconnus détectés par le LLM.
    """
    if not chunks:
        return []

    # Concaténer le texte des chunks (limiter pour ne pas dépasser le contexte)
    full_text = "\n\n".join(
        f"[Document: {c.source_document}] [Pages: {', '.join(map(str, c.source_pages))}]\n{c.text}"
        for c in chunks
    )
    # Limiter à ~15000 caractères pour rester dans le budget tokens
    if len(full_text) > 15000:
        full_text = full_text[:15000] + "\n[... texte tronqué ...]"

    known_list = ", ".join(known_acronyms) if known_acronyms else "(aucun)"

    system_prompt = """Tu es un expert linguistique. Tu dois identifier les ACRONYMES et SIGLES présents dans le texte qui NE SONT PAS dans la liste des acronymes déjà connus.

Cherche les patterns :
- Mots en majuscules de 2 à 8 lettres (ex: DGFIP, IRPP, SCI)
- Acronymes suivis de leur expansion entre parenthèses (ex: "TVA (Taxe sur la Valeur Ajoutée)")
- Sigles courants du domaine

RÈGLES :
1. N'inclus PAS les acronymes déjà dans la liste des connus
2. Pour chaque acronyme trouvé, donne sa définition/expansion si tu la connais, sinon indique "Définition inconnue"
3. Cite le document source et les pages

FORMAT DE RÉPONSE (JSON strict) :
{
    "acronyms": [
        {
            "acronym": "SIGLE",
            "definition": "Expansion ou définition du sigle",
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2]
        }
    ]
}"""

    user_prompt = f"""Acronymes déjà connus (à NE PAS inclure) : {known_list}

Texte à analyser :
---
{full_text}
---

Retourne les acronymes/sigles trouvés qui ne sont PAS dans la liste des connus."""

    try:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)
    except Exception:
        return []

    acronyms = []
    for a_data in result.get("acronyms", []):
        try:
            acr = a_data.get("acronym", "").strip()
            defn = a_data.get("definition", "").strip()
            if acr and len(acr) >= 2:
                acronyms.append(Acronym(
                    acronym=acr,
                    definition=defn or "Définition inconnue",
                    all_definitions=[defn] if defn else [],
                    source_document=a_data.get("source_document", ""),
                    source_pages=a_data.get("source_pages", []),
                    enabled=True,
                    from_reference=False,
                ))
        except (KeyError, TypeError):
            continue

    return acronyms


def edit_acronyms_with_llm(
    current_acronyms: List[Acronym],
    user_instruction: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Tuple[List[Acronym], str]:
    """
    Modifie la liste des acronymes via une instruction en langage naturel.

    Args:
        current_acronyms: Liste des acronymes actuels.
        user_instruction: Instruction de l'utilisateur.
        model: Modèle LLM à utiliser.
        enable_thinking: Activer le mode raisonnement.

    Returns:
        (liste_mise_à_jour, explication)
    """
    acronyms_text = ""
    for i, a in enumerate(current_acronyms, 1):
        status = "✅ activé" if a.enabled else "❌ désactivé"
        acronyms_text += (
            f"{i}. [{status}] **{a.acronym}** : {a.definition}\n"
            f"   Toutes les définitions : {', '.join(a.all_definitions) if a.all_definitions else a.definition}\n"
            f"   Source : {a.source_document}, pages {a.source_pages}\n\n"
        )

    system_prompt = """Tu es un assistant pédagogique. L'utilisateur te donne une liste d'acronymes et une instruction pour les modifier.

Tu dois retourner la liste COMPLÈTE des acronymes après modification.

FORMAT DE RÉPONSE (JSON strict) :
{
    "acronyms": [
        {
            "acronym": "SIGLE",
            "definition": "Définition principale",
            "all_definitions": ["Déf 1", "Déf 2"],
            "source_document": "nom_du_fichier.pdf",
            "source_pages": [1, 2],
            "enabled": true
        }
    ],
    "explanation": "Explication de ce qui a été modifié"
}"""

    user_prompt = f"""Voici les acronymes actuels :

{acronyms_text}

INSTRUCTION DE L'UTILISATEUR : {user_instruction}

Applique cette instruction et retourne la liste complète mise à jour."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)

    acronyms = []
    for a_data in result.get("acronyms", []):
        try:
            acr = a_data.get("acronym", "").strip()
            if acr:
                acronyms.append(Acronym(
                    acronym=acr,
                    definition=a_data.get("definition", ""),
                    all_definitions=a_data.get("all_definitions", [a_data.get("definition", "")]),
                    source_document=a_data.get("source_document", ""),
                    source_pages=a_data.get("source_pages", []),
                    enabled=a_data.get("enabled", True),
                    from_reference=False,
                ))
        except (KeyError, TypeError):
            continue

    explanation = result.get("explanation", "")
    return acronyms, explanation


def acronyms_to_prompt_text(acronyms: List[Acronym]) -> str:
    """
    Convertit les acronymes activés en texte à injecter dans les prompts de génération.

    Args:
        acronyms: Liste d'Acronym.

    Returns:
        Texte formaté pour inclusion dans un prompt LLM.
    """
    active = [a for a in acronyms if a.enabled]
    if not active:
        return ""

    lines = ["ACRONYMES DU DOMAINE :"]
    for a in active:
        lines.append(f"- {a.acronym} : {a.definition}")

    return "\n".join(lines)
