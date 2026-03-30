"""
exercise_generator.py — Génération d'exercices avec vérification agentique via LangChain.

Les exercices ont des réponses numériques vérifiables par exécution de code Python.
"""

import re
import subprocess
import sys
import tempfile
import os
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_experimental.tools import PythonREPLTool
from langgraph.prebuilt import create_react_agent

import logging

from core.llm_service import (
    call_llm_json,
    call_llm_vision_json,
    count_tokens,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    MODEL_NAME,
    VISION_MODEL_NAME,
    VISION_MODEL_NAMES,
    MODEL_CONTEXT_WINDOW,
)
from core.models import validate_exercise
from processing.document_processor import TextChunk

logger = logging.getLogger(__name__)

# Timeout pour l'exécution sandbox (en secondes)
SANDBOX_TIMEOUT = 30

# Bloc JSON fixe (non éditable dans l'UI)
EXERCISE_JSON_FORMAT = """FORMAT DE RÉPONSE (JSON strict) :
{{
    "exercises": [
        {{
            "statement": "Énoncé complet de l'exercice (auto-suffisant, toutes les données incluses)...",
            "expected_answer": "42.5",
            "steps": [
                "Étape 1 : Identifier les données...",
                "Étape 2 : Appliquer la formule...",
                "Étape 3 : Calculer le résultat..."
            ],
            "correction": "Correction détaillée avec explications pédagogiques...",
            "verification_code": "# Code Python COMPLET\\n# Étape 1 : Données\\ndonnee_1 = 100\\ndonnee_2 = 0.425\\n# Étape 2 : Calcul\\nresult = donnee_1 * donnee_2\\nprint(f'Résultat: {{result}}')",
            "citation": "Citation exacte du passage du texte qui inspire l'exercice...",
            "source_page": 1,
            "related_notions": ["Titre notion 1", "Titre notion 2"],
            "sub_parts": [
                {{
                    "question": "Q1. Première question partielle...",
                    "expected_answer": "10.0",
                    "steps": ["Étape 1...", "Étape 2..."],
                    "verification_code": "result = 10.0\\nprint(f'Résultat: {{result}}')"
                }},
                {{
                    "question": "Q2. Deuxième question partielle...",
                    "expected_answer": "32.5",
                    "steps": ["Étape 1...", "Étape 2..."],
                    "verification_code": "result = 32.5\\nprint(f'Résultat: {{result}}')"
                }}
            ]
        }}
    ]
}}

NOTE sur sub_parts : Si l'exercice comporte PLUSIEURS questions numérotées (Q1, Q2, Q3...), utilise le champ "sub_parts" pour structurer chaque sous-question avec sa propre réponse, ses étapes et son code de vérification. Dans ce cas, "expected_answer" et "steps" au niveau principal servent de résumé global (ou peuvent être vides). Si l'exercice n'a qu'UNE seule question, laisse "sub_parts" vide ([])."""

EXERCISE_JSON_FORMAT_TROU = """FORMAT DE RÉPONSE (JSON strict) :
{{
    "exercises": [
        {{
            "statement": "Texte de l'exercice avec des blancs indiqués par _____. Ex: Le délai de _____ est de _____ jours.",
            "blanks": [
                {{"position": 1, "answer": "recours", "context": "Le délai de [BLANC] est de _____ jours."}},
                {{"position": 2, "answer": "30", "context": "Le délai de _____ est de [BLANC] jours."}}
            ],
            "correction": "Correction détaillée expliquant chaque réponse...",
            "citation": "Citation exacte du passage du texte qui inspire l'exercice...",
            "source_page": 1,
            "related_notions": ["Titre notion 1"]
        }}
    ]
}}"""

EXERCISE_JSON_FORMAT_CAS_PRATIQUE = """FORMAT DE RÉPONSE (JSON strict) :
{{
    "exercises": [
        {{
            "statement": "Contexte complet du cas pratique (situation, données, contexte réglementaire si applicable)...",
            "sub_questions": [
                {{"question": "Question 1 ?", "answer": "Réponse développée à la question 1..."}},
                {{"question": "Question 2 ?", "answer": "Réponse développée à la question 2..."}}
            ],
            "correction": "Correction globale et commentaires pédagogiques sur l'ensemble du cas...",
            "verification_code": "# Code Python de vérification des calculs (OPTIONNEL, seulement si des calculs sont demandés)\\n# Étape 1 : Données\\nbase = 50000\\ntaux = 0.2\\n# Étape 2 : Calcul\\nresult = base * taux\\nprint(f'Résultat: {{result}}')",
            "citation": "Citation exacte du passage du texte qui inspire le cas...",
            "source_page": 1,
            "related_notions": ["Titre notion 1", "Titre notion 2"]
        }}
    ]
}}"""

# ── Persona par défaut (éditable par le formateur) ───────────────────────────

EXERCISE_DEFAULT_PERSONA = (
    "Tu es un expert en pédagogie et en création d'exercices éducatifs. "
    "Tu maîtrises le domaine couvert par les documents fournis et tu sais "
    "concevoir des exercices clairs, progressifs et pédagogiquement pertinents."
)

# ── Règles fixes par type (non éditables, affichées en lecture seule) ────────

EXERCISE_FIXED_RULES_CALCUL = """CONTEXTE IMPORTANT :
Les étudiants ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME, fournir toutes les données nécessaires dans son énoncé.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.

RÈGLES (appliquées automatiquement) :
1. Réponse numérique claire et vérifiable
2. Énoncé clair, complet et auto-suffisant
3. Résolution décomposée en étapes numérotées
4. Code Python reproduisant intégralement les calculs depuis les données de départ
5. Le code NE DOIT PAS se contenter de poser result = <valeur_finale>
6. Variable 'result' pour le résultat final
7. Page exacte et citation du passage source
8. print() pour chaque étape intermédiaire
9. 'related_notions' avec les titres exacts des notions couvertes"""

EXERCISE_FIXED_RULES_TROU = """CONTEXTE IMPORTANT :
Les étudiants ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.

RÈGLES (appliquées automatiquement) :
1. Blancs matérialisés par _____ dans l'énoncé
2. Chaque blanc = un terme, une valeur ou une notion clé
3. Entre 2 et 5 blancs par exercice
4. Blancs sur des informations importantes, pas anecdotiques
5. Champ "context" avec [BLANC] à la place du terme manquant
6. Page exacte et citation du passage source
7. 'related_notions' avec les titres exacts des notions couvertes
8. L'énoncé doit fournir SUFFISAMMENT DE CONTEXTE pour répondre sans le document
9. Au minimum 3 phrases, dont au moins une phrase de contexte SANS blanc"""

EXERCISE_FIXED_RULES_CAS_PRATIQUE = """CONTEXTE IMPORTANT :
Les étudiants ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME — l'énoncé fournit toutes les données nécessaires.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.

RÈGLES (appliquées automatiquement) :
1. Situation concrète réaliste (personne, entreprise, dossier, scénario)
2. Toutes les informations nécessaires dans l'énoncé
3. Entre 2 et 4 sous-questions progressives
4. Analyse, calcul ou argumentation demandée
5. Correction complète et pédagogique par sous-question
6. Page exacte et citation du passage source
7. 'related_notions' avec les titres exacts des notions couvertes
8. Pour les sous-questions avec calculs, fournir un verification_code Python avec les étapes arithmétiques (PAS de code arbitraire)
9. Le code doit stocker le résultat final dans 'result' et afficher chaque étape avec print()"""

# Dict pour accéder aux règles fixes par type
EXERCISE_FIXED_RULES_BY_TYPE = {
    "calcul": EXERCISE_FIXED_RULES_CALCUL,
    "trou": EXERCISE_FIXED_RULES_TROU,
    "cas_pratique": EXERCISE_FIXED_RULES_CAS_PRATIQUE,
}

# ── Règles internes complètes (injectées dans le prompt, non éditables) ─────

_COMMON_RULES_TROU = """
CONTEXTE IMPORTANT :
Les étudiants suivent une formation mais ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.

RÈGLES POUR LES QUESTIONS À TROU :
1. L'énoncé est une ou plusieurs phrases avec des blancs matérialisés par _____
2. Chaque blanc correspond à un terme, une valeur ou une notion clé du cours
3. Il doit y avoir entre 2 et 5 blancs par exercice
4. Les blancs doivent porter sur des informations importantes, pas des détails anecdotiques
5. Le champ "context" de chaque blanc montre la phrase avec [BLANC] à la place du terme manquant
6. Pour chaque exercice, précise la PAGE EXACTE de la source et une CITATION exacte
7. Indique dans 'related_notions' le(s) titre(s) exact(s) des notions couvertes
8. L'énoncé doit fournir SUFFISAMMENT DE CONTEXTE pour que l'étudiant puisse répondre sans le document.
   Chaque phrase à trou doit être entourée de phrases explicatives qui donnent le cadre nécessaire (définitions, exemples, contexte).
9. L'exercice doit comporter au minimum 3 phrases, dont au moins une phrase de contexte SANS blanc avant les phrases à compléter.
{notions_block}"""

_COMMON_RULES_CAS_PRATIQUE = """
CONTEXTE IMPORTANT :
Les étudiants suivent une formation mais ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME — l'énoncé fournit toutes les données nécessaires.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.

RÈGLES POUR LES CAS PRATIQUES :
1. Le cas pratique présente une situation concrète réaliste (personne, entreprise, dossier, scénario)
2. L'énoncé fournit toutes les informations nécessaires pour répondre
3. Il doit y avoir entre 2 et 4 sous-questions progressives
4. Les sous-questions doivent demander une analyse, un calcul ou une prise de position argumentée
5. La correction de chaque sous-question doit être complète et pédagogique
6. Pour chaque exercice, précise la PAGE EXACTE de la source et une CITATION exacte
7. Indique dans 'related_notions' le(s) titre(s) exact(s) des notions couvertes
8. Pour les sous-questions comportant des CALCULS, fournis un champ "verification_code" avec du code Python vérifiant les étapes de calcul.
   NE génère PAS de code Python arbitraire — uniquement les étapes arithmétiques reproduisant le raisonnement.
   Le code doit stocker le résultat final dans une variable 'result' et afficher chaque étape avec print().
{notions_block}"""

_COMMON_RULES = """
CONTEXTE IMPORTANT :
Les étudiants suivent une formation mais ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME, fournir toutes les données nécessaires dans son énoncé,
et être résolvable sans le document.
INTERDIT ABSOLU dans l'énoncé : toute référence au document source.
N'utilise JAMAIS : "selon le texte", "d'après le document", "comme indiqué ci-dessus",
"dans le texte fourni", "d'après le passage", "selon l'extrait", ou toute formulation similaire.
L'énoncé doit se lire comme un exercice autonome, sans que l'apprenant n'ait besoin d'aucun document.

RÈGLES :
1. Chaque exercice doit avoir une réponse numérique claire et vérifiable
2. L'énoncé doit être clair, complet et auto-suffisant
3. La résolution doit être décomposée en étapes claires et numérotées
4. Le code Python doit reproduire INTÉGRALEMENT les calculs étape par étape depuis les données de départ
5. Le code NE DOIT PAS se contenter de poser result = <valeur_finale>
   Exemple INTERDIT : result = 42.5
   Exemple CORRECT : donnee_1 = 100 ; donnee_2 = 0.425 ; result = donnee_1 * donnee_2
6. Le code doit stocker le résultat final dans une variable nommée 'result'
7. Pour chaque exercice, précise la PAGE EXACTE de la source
8. Inclus une CITATION exacte du passage du texte qui inspire l'exercice
9. Le code doit afficher chaque étape intermédiaire avec print() pour permettre la vérification pas à pas
   Exemple : print(f'Étape 1 — donnee_1 = {{donnee_1}}') ; print(f'Étape 2 — calcul = {{calcul}}')
10. Pour chaque exercice, indique dans 'related_notions' le(s) titre(s) exact(s) des notions fondamentales couvertes. Utilise les titres tels qu'ils apparaissent dans la liste des notions.
{notions_block}"""

# ── Instructions par difficulté (éditables par le formateur) ─────────────────

DEFAULT_EXERCISE_PROMPTS_TROU = {
    "facile": "NIVEAU FACILE : Les blancs portent sur des définitions simples, des termes clés ou des valeurs directement mentionnées dans le texte.",
    "moyen": "NIVEAU MOYEN : Les blancs portent sur des concepts importants, des conditions ou des articulations logiques du cours.",
    "difficile": "NIVEAU DIFFICILE : Les blancs portent sur des nuances, des exceptions, des conditions précises ou des articulations complexes entre notions.",
}

DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE = {
    "facile": "NIVEAU FACILE : Le cas est simple, les informations nécessaires sont évidentes, les sous-questions portent sur l'application directe d'une règle ou d'un principe.",
    "moyen": "NIVEAU MOYEN : Le cas nécessite d'analyser la situation, d'identifier la règle applicable et de l'appliquer en plusieurs étapes.",
    "difficile": "NIVEAU DIFFICILE : Le cas est complexe, implique plusieurs notions croisées, des situations ambiguës ou des exceptions à identifier. Les sous-questions demandent argumentation et synthèse.",
}

DEFAULT_EXERCISE_PROMPTS = {
    "facile": (
        "NIVEAU FACILE — Application numérique directe :\n"
        "- Application DIRECTE d'une formule ou d'un concept en une étape principale\n"
        "- Toutes les données numériques sont explicitement fournies dans l'énoncé\n"
        "- Calcul simple, sans raisonnement multi-étapes complexe\n"
        "- Idéal pour vérifier la maîtrise d'une formule ou d'une définition"
    ),
    "moyen": (
        "NIVEAU MOYEN — Raisonnement multi-étapes :\n"
        "- Nécessite plusieurs étapes de calcul ou de raisonnement enchaînées\n"
        "- Peut combiner plusieurs formules ou concepts\n"
        "- Les données sont fournies mais leur traitement demande de la réflexion\n"
        "- Application de connaissances à une situation concrète"
    ),
    "difficile": (
        "NIVEAU DIFFICILE — Résolution complexe, niveau études supérieures :\n"
        "- Nécessite un raisonnement complexe et multi-niveaux\n"
        "- Combine plusieurs domaines ou concepts avancés\n"
        "- Résolution non triviale avec des subtilités ou pièges\n"
        "- Demande une analyse approfondie et une maîtrise solide des concepts\n"
        "- Peut inclure des modélisations, optimisations ou démonstrations"
    ),
}

# Alias pour compatibilité avec l'ancien code
DEFAULT_EXERCISE_PROMPT = DEFAULT_EXERCISE_PROMPTS["moyen"]


@dataclass
class Exercise:
    """Un exercice avec sa correction vérifiée."""
    statement: str  # Énoncé de l'exercice
    expected_answer: str  # Réponse attendue (numérique, pour type "calcul")
    steps: List[str] = field(default_factory=list)  # Étapes de résolution
    num_steps: int = 0  # Nombre d'étapes
    correction: str = ""  # Correction détaillée par IA
    verification_code: str = ""  # Code Python de vérification (type "calcul" uniquement)
    verified: bool = False  # La réponse a-t-elle été vérifiée ?
    verification_output: str = ""  # Sortie de la vérification
    source_pages: List[int] = field(default_factory=list)
    source_document: str = ""
    citation: str = ""
    difficulty_level: str = "moyen"  # facile / moyen / difficile
    related_notions: List[str] = field(default_factory=list)  # Titres des notions couvertes
    exercise_type: str = "calcul"  # "calcul" | "trou" | "cas_pratique"
    blanks: List[dict] = field(default_factory=list)  # Pour type "trou"
    sub_questions: List[dict] = field(default_factory=list)  # Pour type "cas_pratique"
    sub_parts: List[dict] = field(default_factory=list)  # Multi-questions (Q1, Q2...) pour calcul


def _get_langchain_llm(model: Optional[str] = None):
    """Crée une instance ChatOpenAI pour LangChain."""
    return ChatOpenAI(
        model=model or MODEL_NAME,
        openai_api_base=OPENAI_API_BASE,
        openai_api_key=OPENAI_API_KEY,
        temperature=0.3,
    )


def _build_exercise_prompt(
    text: str,
    num_exercises: int,
    notions_text: str = "",
    source_document: str = "",
    difficulty: str = "moyen",
    custom_exercise_prompts: Optional[dict] = None,
    exercise_type: str = "calcul",
    persona: str = "",
) -> tuple:
    """
    Construit le prompt pour la génération d'exercices.

    Assemblage : persona + "Crée N exercice(s)..." + règles fixes par type + instructions
    de difficulté (éditables) + format JSON.
    """

    notions_block = ""
    if notions_text:
        notions_block = f"\n\n{notions_text}\nLes exercices doivent tester la maîtrise pratique de ces notions fondamentales."

    # Persona active
    active_persona = persona.strip() if persona and persona.strip() else EXERCISE_DEFAULT_PERSONA

    # Sélection des ressources selon le type
    if exercise_type == "trou":
        prompts = custom_exercise_prompts or DEFAULT_EXERCISE_PROMPTS_TROU
        common_rules = _COMMON_RULES_TROU
        json_format = EXERCISE_JSON_FORMAT_TROU
        type_label = "questions à trou (compléter les blancs)"
    elif exercise_type == "cas_pratique":
        prompts = custom_exercise_prompts or DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE
        common_rules = _COMMON_RULES_CAS_PRATIQUE
        json_format = EXERCISE_JSON_FORMAT_CAS_PRATIQUE
        type_label = "cas pratiques"
    else:
        prompts = custom_exercise_prompts or DEFAULT_EXERCISE_PROMPTS
        common_rules = _COMMON_RULES
        json_format = EXERCISE_JSON_FORMAT
        type_label = "exercices numériques"

    difficulty_instructions = prompts.get(difficulty, prompts.get("moyen", ""))

    # Injecter notions dans les règles communes
    rules_block = common_rules.replace("{notions_block}", notions_block)

    # Assembler le system prompt : persona + task + rules + difficulty + JSON
    system_prompt = (
        f"{active_persona}\n\n"
        f"Tu dois créer exactement {num_exercises} {type_label} de niveau {difficulty} "
        f"basé(s) sur le texte fourni.\n"
        f"{rules_block}\n\n"
        f"{difficulty_instructions}\n\n"
        f"{json_format}"
    )

    doc_context = f" (document : {source_document})" if source_document else ""
    user_prompt = (
        f"Voici le texte source{doc_context} :\n\n---\n{text}\n---\n\n"
        f"Crée exactement {num_exercises} {type_label} de niveau {difficulty}.\n"
        f"IMPORTANT : l'énoncé NE DOIT PAS faire référence au texte source. "
        f"L'exercice doit être auto-suffisant."
    )

    return system_prompt, user_prompt


def _verify_exercise_with_agent(exercise: Exercise, model: Optional[str] = None) -> Exercise:
    """
    Vérifie un exercice en exécutant le code Python via un agent LangGraph.
    
    L'agent :
    1. Exécute le code de vérification
    2. Compare le résultat avec la réponse attendue
    3. Valide ou invalide l'exercice
    """
    if not exercise.verification_code:
        exercise.verified = False
        exercise.verification_output = "Pas de code de vérification fourni."
        return exercise
    
    try:
        llm = _get_langchain_llm(model=model)
        python_tool = PythonREPLTool()
        tools = [python_tool]

        # Créer l'agent LangGraph ReAct (retourne un CompiledGraph)
        system_prompt = (
            "Tu es un agent vérificateur d'exercices. "
            "Tu dois exécuter du code Python pour vérifier que la réponse attendue est correcte. "
            "Exécute le code, compare le résultat avec la réponse attendue, "
            "puis conclus par VÉRIFIÉ si le résultat correspond, ou ERREUR sinon."
        )

        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_prompt,
        )

        user_message = (
            f"Vérifie cet exercice en exécutant le code Python fourni.\n\n"
            f"EXERCICE : {exercise.statement}\n\n"
            f"RÉPONSE ATTENDUE : {exercise.expected_answer}\n\n"
            f"CODE DE VÉRIFICATION :\n```python\n{exercise.verification_code}\n```\n\n"
            f"Exécute le code et indique si le résultat correspond à la réponse attendue "
            f"({exercise.expected_answer}). Conclus par VÉRIFIÉ ou ERREUR."
        )

        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_message}]}
        )

        # Extraire la réponse finale de l'agent
        messages = result.get("messages", [])
        output = ""
        if messages:
            last_msg = messages[-1]
            output = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

        exercise.verification_output = output
        exercise.verified = "VÉRIFIÉ" in output.upper() or "VERIFIE" in output.upper()
        
    except Exception as e:
        # Fallback : exécution directe du code
        exercise = _verify_exercise_direct(exercise)

    return exercise


def _parse_numeric(value: str) -> float:
    """
    Parse une valeur numérique de manière robuste.
    Gère : espaces, virgules décimales, séparateurs de milliers,
    suffixes d'unités, pourcentages, notation scientifique.
    Exemples : "10" → 10.0, "10.0" → 10.0, "10,5" → 10.5,
               "1 000" → 1000.0, "42.5%" → 42.5, "3.14 m" → 3.14
    """
    s = str(value).strip()
    # Retirer les unités/texte en fin de chaîne (%, €, m, kg, etc.)
    s = re.sub(r'[%€$£°]$', '', s).strip()
    s = re.sub(r'\s*[a-zA-Zµ°/²³]+[\s/a-zA-Z²³]*$', '', s).strip()
    # Retirer les espaces (séparateur de milliers français : "1 000")
    s = s.replace('\u202f', '').replace('\xa0', '').replace(' ', '')
    # Gérer virgule vs point décimal
    # Si on a à la fois des points et des virgules, le dernier est le séparateur décimal
    has_comma = ',' in s
    has_dot = '.' in s
    if has_comma and has_dot:
        # "1,000.5" ou "1.000,5"
        if s.rfind(',') > s.rfind('.'):
            # Virgule est le séparateur décimal : "1.000,5"
            s = s.replace('.', '').replace(',', '.')
        else:
            # Point est le séparateur décimal : "1,000.5"
            s = s.replace(',', '')
    elif has_comma:
        # Virgule seule : séparateur décimal ("10,5") ou milliers ("1,000")
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            # Probablement séparateur de milliers : "1,000"
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
    return float(s)


def _verify_sub_part(sub_part: dict) -> dict:
    """Vérifie une sous-partie d'exercice multi-questions par exécution de code Python."""
    code = sub_part.get("verification_code", "")
    expected = str(sub_part.get("expected_answer", ""))
    if not code:
        return {**sub_part, "verified": False, "verification_output": "Pas de code de vérification."}

    wrapper_code = code + "\n\n"
    wrapper_code += (
        "import json as _json\n"
        "_result_vars = ['result', 'resultat', 'answer', 'reponse', 'res']\n"
        "for _var in _result_vars:\n"
        "    if _var in dir() or _var in globals():\n"
        "        _val = globals().get(_var) or locals().get(_var)\n"
        "        if _val is not None:\n"
        "            print(f'__RESULT__={_val}')\n"
        "            break\n"
    )

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(wrapper_code)
            tmp_path = tmp_file.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True, timeout=SANDBOX_TIMEOUT,
                cwd=tempfile.gettempdir(),
            )
            if proc.returncode != 0:
                return {**sub_part, "verified": False, "verification_output": f"Erreur d'exécution: {proc.stderr[:300]}"}

            result_match = re.search(r'__RESULT__=(.+)', proc.stdout)
            if result_match:
                result_value = result_match.group(1).strip()
                try:
                    exp = _parse_numeric(expected)
                    act = _parse_numeric(result_value)
                    verified = abs(exp - act) < abs(exp) * 0.001 + 0.01
                except (ValueError, TypeError):
                    verified = result_value.strip() == expected.strip()
                return {**sub_part, "verified": verified, "verification_output": f"Résultat: {result_value} (attendu: {expected})"}
            else:
                return {**sub_part, "verified": False, "verification_output": "Pas de variable résultat produite."}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except subprocess.TimeoutExpired:
        return {**sub_part, "verified": False, "verification_output": f"Timeout ({SANDBOX_TIMEOUT}s)"}
    except Exception as e:
        return {**sub_part, "verified": False, "verification_output": f"Erreur: {e}"}


def _verify_exercise_direct(exercise: Exercise) -> Exercise:
    """
    Vérification directe en exécutant le code Python dans un sous-processus isolé.
    Capture tous les résultats intermédiaires (print) et le résultat final.
    """
    # Vérifier les sub_parts individuellement si présentes
    if exercise.sub_parts:
        all_verified = True
        details = ["═══ VÉRIFICATION MULTI-QUESTIONS ═══\n"]
        verified_parts = []
        for idx, sp in enumerate(exercise.sub_parts):
            if sp.get("verification_code"):
                result_sp = _verify_sub_part(sp)
                sp_ok = result_sp.get("verified", False)
                icon = "✅" if sp_ok else "❌"
                details.append(f"{icon} Q{idx+1}: {result_sp.get('verification_output', '')}")
                if not sp_ok:
                    all_verified = False
                verified_parts.append(result_sp)
            else:
                verified_parts.append({**sp, "verified": False, "verification_output": "Pas de code."})
                details.append(f"⚠️ Q{idx+1}: Pas de code de vérification")
                all_verified = False

        exercise.sub_parts = verified_parts
        exercise.verified = all_verified
        exercise.verification_output = "\n".join(details)
        return exercise

    if not exercise.verification_code:
        exercise.verified = False
        exercise.verification_output = "Pas de code de vérification fourni."
        return exercise

    try:
        wrapper_code = exercise.verification_code + "\n\n"
        wrapper_code += (
            "# --- Extraction du résultat ---\n"
            "import json as _json\n"
            "_result_vars = ['result', 'resultat', 'answer', 'reponse', 'res']\n"
            "for _var in _result_vars:\n"
            "    if _var in dir() or _var in globals():\n"
            "        _val = globals().get(_var) or locals().get(_var)\n"
            "        if _val is not None:\n"
            "            print(f'__RESULT__={_val}')\n"
            "            break\n"
        )

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(wrapper_code)
            tmp_path = tmp_file.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=SANDBOX_TIMEOUT,
                cwd=tempfile.gettempdir(),
            )

            stdout = proc.stdout
            stderr = proc.stderr

            # --- Construire l'output détaillé ---
            detail = []
            detail.append("═══ VÉRIFICATION AUTOMATIQUE ═══\n")

            if proc.returncode != 0:
                detail.append("❌ ERREUR D'EXÉCUTION DU CODE")
                detail.append(f"Code retour : {proc.returncode}")
                if stderr:
                    detail.append(f"\nErreur :\n{stderr[:500]}")
                exercise.verified = False
                exercise.verification_output = "\n".join(detail)
                return exercise

            # Extraire les lignes de calcul (tout sauf __RESULT__)
            calc_lines = [
                line for line in stdout.splitlines()
                if not line.startswith("__RESULT__")
            ]
            if calc_lines:
                detail.append("📊 Résultats des calculs :")
                for line in calc_lines:
                    detail.append(f"   {line}")
                detail.append("")

            # Extraire le résultat final
            result_match = re.search(r'__RESULT__=(.+)', stdout)
            if result_match:
                result_value = result_match.group(1).strip()
                detail.append(f"🎯 Résultat du code : {result_value}")
                detail.append(f"📝 Réponse attendue : {exercise.expected_answer}")
                detail.append("")

                try:
                    expected = _parse_numeric(exercise.expected_answer)
                    actual = _parse_numeric(result_value)
                    if abs(expected - actual) < abs(expected) * 0.001 + 0.01:
                        exercise.verified = True
                        detail.append("✅ VÉRIFIÉ — Tous les calculs sont corrects")
                    else:
                        exercise.verified = False
                        detail.append(f"❌ ERREUR — Résultat ({actual}) ≠ attendu ({expected})")
                except (ValueError, TypeError):
                    if result_value.strip() == exercise.expected_answer.strip():
                        exercise.verified = True
                        detail.append("✅ VÉRIFIÉ — Comparaison texte correcte")
                    else:
                        exercise.verified = False
                        detail.append(f"❌ ERREUR — Obtenu \"{result_value}\" ≠ attendu \"{exercise.expected_answer}\"")
            else:
                exercise.verified = False
                detail.append("⚠️ Le code n'a pas produit de variable résultat (result, answer, res...)")
                if stdout.strip():
                    detail.append(f"Sortie brute : {stdout[:300]}")

            exercise.verification_output = "\n".join(detail)

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except subprocess.TimeoutExpired:
        exercise.verified = False
        exercise.verification_output = f"⏱️ Timeout : le code a dépassé {SANDBOX_TIMEOUT}s."
    except Exception as e:
        exercise.verified = False
        exercise.verification_output = f"❌ Erreur sandbox : {str(e)}"

    return exercise


def _correct_exercise_with_llm(exercise: Exercise, model: Optional[str] = None, enable_thinking: bool = True) -> Exercise:
    """
    Demande au LLM de corriger un exercice dont la vérification a échoué.
    Envoie le résultat du code Python au LLM pour qu'il corrige sa résolution.
    """
    system_prompt = """Tu es un expert en correction d'exercices. L'exercice suivant a échoué la vérification automatique : le code Python de vérification donne un résultat différent de la réponse attendue.

Analyse l'erreur et corrige :
- La réponse attendue (expected_answer) pour qu'elle corresponde au résultat CORRECT
- Les étapes de résolution si elles contiennent une erreur
- Le code de vérification si nécessaire
- La correction détaillée

Le code Python fait foi : si le code calcule correctement, c'est la réponse attendue qui est fausse.

FORMAT DE RÉPONSE (JSON strict) :
{
    "expected_answer": "valeur_corrigée",
    "steps": ["Étape 1 corrigée...", "Étape 2 corrigée..."],
    "correction": "Correction détaillée expliquant le raisonnement correct...",
    "verification_code": "# Code Python corrigé si nécessaire..."
}"""

    user_prompt = (
        f"EXERCICE :\n{exercise.statement}\n\n"
        f"RÉPONSE ATTENDUE (initiale, probablement fausse) : {exercise.expected_answer}\n\n"
        f"CODE DE VÉRIFICATION :\n```python\n{exercise.verification_code}\n```\n\n"
        f"RÉSULTAT DE LA VÉRIFICATION :\n{exercise.verification_output}\n\n"
        "Corrige cet exercice. Le résultat du code Python est la référence."
    )

    try:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, enable_thinking=enable_thinking)

        if "expected_answer" in result:
            exercise.expected_answer = str(result["expected_answer"])
        if "steps" in result:
            exercise.steps = result["steps"]
            exercise.num_steps = len(result["steps"])
        if "correction" in result:
            exercise.correction = result["correction"]
        if "verification_code" in result:
            exercise.verification_code = result["verification_code"]
    except Exception as e:
        print(f"Correction LLM échouée : {e}")

    return exercise


def _parse_exercises(
    result: dict,
    chunk: TextChunk,
    difficulty: str,
    exercise_type: str = "calcul",
) -> List[Exercise]:
    """Parse le JSON retourné par le LLM en liste d'Exercise avec validation Pydantic."""
    exercises = []
    for ex_data in result.get("exercises", []):
        try:
            # Validation Pydantic (normalise source_page → source_pages)
            validated = validate_exercise(ex_data)

            source_pages = validated["source_pages"] if validated["source_pages"] else chunk.source_pages

            if exercise_type == "trou":
                exercise = Exercise(
                    statement=validated["statement"],
                    expected_answer="",
                    blanks=validated.get("blanks", []),
                    correction=validated.get("correction", ""),
                    source_pages=source_pages,
                    source_document=chunk.source_document,
                    citation=validated.get("citation", ""),
                    difficulty_level=difficulty,
                    related_notions=validated.get("related_notions", []),
                    exercise_type="trou",
                    verified=True,
                    verification_output="Vérification manuelle recommandée.",
                )
            elif exercise_type == "cas_pratique":
                exercise = Exercise(
                    statement=validated["statement"],
                    expected_answer="",
                    sub_questions=validated.get("sub_questions", []),
                    correction=validated.get("correction", ""),
                    verification_code=validated.get("verification_code", ""),
                    source_pages=source_pages,
                    source_document=chunk.source_document,
                    citation=validated.get("citation", ""),
                    difficulty_level=difficulty,
                    related_notions=validated.get("related_notions", []),
                    exercise_type="cas_pratique",
                    verified=True,
                    verification_output="Vérification manuelle recommandée.",
                )
            else:
                exercise = Exercise(
                    statement=validated["statement"],
                    expected_answer=str(validated.get("expected_answer", "")),
                    steps=validated.get("steps", []),
                    num_steps=len(validated.get("steps", [])),
                    correction=validated.get("correction", ""),
                    verification_code=validated.get("verification_code", ""),
                    source_pages=source_pages,
                    source_document=chunk.source_document,
                    citation=validated.get("citation", ""),
                    difficulty_level=difficulty,
                    related_notions=validated.get("related_notions", []),
                    exercise_type="calcul",
                    sub_parts=validated.get("sub_parts", []),
                )
            exercises.append(exercise)
        except Exception as e:
            logger.warning("Exercice ignoré (validation échouée) : %s", e)
            continue
    return exercises


def _verify_and_correct_exercise(exercise: Exercise, model: Optional[str] = None, enable_thinking: bool = True) -> Exercise:
    """Vérifie un exercice par exécution directe, corrige via LLM si échec.
    Pour les types 'trou' et 'cas_pratique', la vérification automatique est ignorée."""
    if exercise.exercise_type != "calcul":
        # Pas de vérification Python pour ces types
        return exercise

    exercise = _verify_exercise_direct(exercise)
    if not exercise.verified and exercise.verification_code:
        initial_output = exercise.verification_output
        exercise = _correct_exercise_with_llm(exercise, model=model, enable_thinking=enable_thinking)
        exercise = _verify_exercise_direct(exercise)
        exercise.verification_output = (
            initial_output
            + "\n\n🔄 CORRECTION AUTOMATIQUE PAR L'IA\n"
            + exercise.verification_output
        )
    return exercise


def generate_exercises_from_chunk(
    chunk: TextChunk,
    num_exercises: int = 1,
    max_retries: int = 3,
    model: Optional[str] = None,
    notions_text: str = "",
    custom_exercise_prompts: Optional[dict] = None,
    difficulty: str = "moyen",
    vision_mode: bool = False,
    exercise_type: str = "calcul",
    persona: str = "",
    enable_thinking: bool = True,
) -> List[Exercise]:
    """
    Génère des exercices à partir d'un chunk de texte avec vérification.
    Si la vérification échoue, demande au LLM de corriger puis re-vérifie.
    """
    system_prompt, user_prompt = _build_exercise_prompt(
        chunk.text, num_exercises, notions_text=notions_text,
        source_document=chunk.source_document,
        difficulty=difficulty,
        custom_exercise_prompts=custom_exercise_prompts,
        exercise_type=exercise_type,
        persona=persona,
    )

    exercises = []

    for attempt in range(max_retries):
        try:
            if vision_mode and chunk.page_images:
                result = call_llm_vision_json(system_prompt, user_prompt, chunk.page_images, model=model, temperature=0.5, enable_thinking=enable_thinking)
            else:
                result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.5, enable_thinking=enable_thinking)

            parsed = _parse_exercises(result, chunk, difficulty, exercise_type=exercise_type)

            for exercise in parsed:
                exercise = _verify_and_correct_exercise(exercise, model=model, enable_thinking=enable_thinking)
                exercises.append(exercise)

            verified_count = sum(1 for ex in exercises if ex.verified)
            if verified_count >= num_exercises:
                break

        except Exception as e:
            print(f"Tentative {attempt + 1}/{max_retries} échouée : {e}")
            continue

    return exercises[:num_exercises]


def generate_exercises(
    chunks: List[TextChunk],
    num_exercises: Optional[int] = None,
    difficulty_counts: Optional[dict] = None,
    model: Optional[str] = None,
    progress_callback=None,
    notions: Optional[list] = None,
    custom_exercise_prompts: Optional[dict] = None,
    batch_mode: bool = False,
    vision_mode: bool = False,
    exercise_type: str = "calcul",
    persona: str = "",
    enable_thinking: bool = True,
) -> List[Exercise]:
    """
    Génère des exercices à partir de plusieurs chunks, avec support des niveaux de difficulté.

    Args:
        chunks: Liste de TextChunk.
        num_exercises: Nombre total (backward compat, traité comme {"moyen": n}).
        difficulty_counts: Dict {difficulté: nombre}. Ex: {"facile": 2, "moyen": 3}.
        model: Modèle LLM à utiliser.
        progress_callback: Fonction callback(current, total) pour la progression.
        notions: Liste de Notion fondamentales pour guider la génération.
        custom_exercise_prompts: Dict {difficulté: prompt_editable}.
        batch_mode: Si True, utilise l'API Batch pour la génération initiale.
        vision_mode: Si True, envoie les images des chunks au modèle vision.
        enable_thinking: Si True, active le mode thinking du LLM.

    Returns:
        Liste d'Exercise.
    """
    if not chunks:
        return []

    # Backward compat
    if difficulty_counts is None:
        difficulty_counts = {"moyen": num_exercises or 3}

    diff_keys = [k for k, v in difficulty_counts.items() if v > 0]

    # Préparer le texte des notions
    notions_text = ""
    if notions:
        from generation.notion_detector import notions_to_prompt_text
        notions_text = notions_to_prompt_text(notions)

    # Pré-calculer toutes les tâches (difficulté, chunk, n_exercices)
    all_tasks = []
    for diff_name in diff_keys:
        diff_count = difficulty_counts[diff_name]
        if len(chunks) <= diff_count:
            selected = list(chunks)
            per_chunk = [1] * len(chunks)
            remaining = diff_count - len(chunks)
            for i in range(remaining):
                per_chunk[i % len(chunks)] += 1
        else:
            step = len(chunks) / diff_count
            indices = [int(i * step) for i in range(diff_count)]
            selected = [chunks[i] for i in indices]
            per_chunk = [1] * len(selected)
        for chunk, n_ex in zip(selected, per_chunk):
            all_tasks.append((diff_name, chunk, n_ex))

    total_steps = len(all_tasks)
    all_exercises = []

    # ─── MODE BATCH ────────────────────────────────────────────────────────
    if batch_mode and total_steps > 1:
        from generation.batch_service import BatchRequest, run_batch_json, run_batch_multi_model

        batch_requests = []
        task_map = {}  # custom_id → (chunk, diff_name, n_ex)

        for idx, (diff_name, chunk, n_ex) in enumerate(all_tasks):
            system_prompt, user_prompt = _build_exercise_prompt(
                chunk.text, n_ex, notions_text=notions_text,
                source_document=chunk.source_document,
                difficulty=diff_name,
                custom_exercise_prompts=custom_exercise_prompts,
                exercise_type=exercise_type,
                persona=persona,
            )
            custom_id = f"exercise_{diff_name}_{idx}"
            images = chunk.page_images if (vision_mode and chunk.page_images) else None
            target_model = (VISION_MODEL_NAME or model or MODEL_NAME) if (vision_mode and images) else (model or MODEL_NAME)

            batch_requests.append(BatchRequest(
                custom_id=custom_id,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=target_model,
                temperature=0.5,
                images=images,
            ))
            task_map[custom_id] = (chunk, diff_name, n_ex)

        if progress_callback:
            progress_callback(0, total_steps)

        # Multi-model dispatch si vision avec plusieurs modèles
        has_vision_requests = any(r.images for r in batch_requests)
        if has_vision_requests and len(VISION_MODEL_NAMES) > 1:
            batch_result = run_batch_multi_model(
                batch_requests,
                models=VISION_MODEL_NAMES,
                progress_callback=lambda done, total: progress_callback(done, total) if progress_callback else None,
            )
            results = batch_result.results
        else:
            results = run_batch_json(
                batch_requests,
                progress_callback=lambda done, total: progress_callback(done, total) if progress_callback else None,
            )

        # Parse + vérification séquentielle
        for custom_id, parsed_json in results.items():
            chunk, diff_name, n_ex = task_map.get(custom_id, (None, None, None))
            if chunk is None:
                continue
            parsed = _parse_exercises(parsed_json, chunk, diff_name, exercise_type=exercise_type)
            for exercise in parsed[:n_ex]:
                exercise = _verify_and_correct_exercise(exercise, model=model, enable_thinking=enable_thinking)
                all_exercises.append(exercise)

    # ─── MODE SÉQUENTIEL ───────────────────────────────────────────────────
    else:
        for i, (diff_name, chunk, n_ex) in enumerate(all_tasks):
            if progress_callback:
                progress_callback(i, total_steps)
            try:
                exercises = generate_exercises_from_chunk(
                    chunk, n_ex, model=model, notions_text=notions_text,
                    custom_exercise_prompts=custom_exercise_prompts,
                    difficulty=diff_name,
                    vision_mode=vision_mode,
                    exercise_type=exercise_type,
                    persona=persona,
                    enable_thinking=enable_thinking,
                )
                all_exercises.extend(exercises)
            except Exception as e:
                print(f"Erreur sur le chunk {chunk.source_pages} ({diff_name}): {e}")
                continue

    if progress_callback:
        progress_callback(total_steps, total_steps)

    return all_exercises

