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

from llm_service import (
    call_llm_json,
    count_tokens,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    MODEL_NAME,
    MODEL_CONTEXT_WINDOW,
)
from document_processor import TextChunk

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
            "source_page": 1
        }}
    ]
}}"""

_COMMON_RULES = """
CONTEXTE IMPORTANT :
Les étudiants suivent une formation mais ne possèdent PAS le document source au moment de l'exercice.
Chaque exercice doit être AUTONOME, fournir toutes les données nécessaires dans son énoncé,
et être résolvable sans le document.
N'utilise JAMAIS de formulations comme "selon le texte", "d'après le document", etc.

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
{{notions_block}}"""

# Prompts éditables par difficulté (sans le bloc JSON fixe)
DEFAULT_EXERCISE_PROMPTS = {
    "facile": (
        "Tu es un expert pédagogique qui crée des exercices FACILES d'application numérique directe.\n"
        "Tu dois créer exactement {num_exercises} exercice(s) basé(s) sur le texte fourni.\n"
        + _COMMON_RULES.replace("{{notions_block}}", "{notions_block}") + "\n"
        "NIVEAU FACILE — Application numérique directe :\n"
        "- Application DIRECTE d'une formule ou d'un concept en une étape principale\n"
        "- Toutes les données numériques sont explicitement fournies dans l'énoncé\n"
        "- Calcul simple, sans raisonnement multi-étapes complexe\n"
        "- Idéal pour vérifier la maîtrise d'une formule ou d'une définition\n"
    ),
    "moyen": (
        "Tu es un expert pédagogique qui crée des exercices de niveau MOYEN nécessitant plusieurs étapes de raisonnement.\n"
        "Tu dois créer exactement {num_exercises} exercice(s) basé(s) sur le texte fourni.\n"
        + _COMMON_RULES.replace("{{notions_block}}", "{notions_block}") + "\n"
        "NIVEAU MOYEN — Raisonnement multi-étapes :\n"
        "- Nécessite plusieurs étapes de calcul ou de raisonnement enchaînées\n"
        "- Peut combiner plusieurs formules ou concepts\n"
        "- Les données sont fournies mais leur traitement demande de la réflexion\n"
        "- Application de connaissances à une situation concrète\n"
    ),
    "difficile": (
        "Tu es un expert pédagogique qui crée des exercices DIFFICILES de niveau études supérieures.\n"
        "Tu dois créer exactement {num_exercises} exercice(s) basé(s) sur le texte fourni.\n"
        + _COMMON_RULES.replace("{{notions_block}}", "{notions_block}") + "\n"
        "NIVEAU DIFFICILE — Résolution complexe, niveau études supérieures :\n"
        "- Nécessite un raisonnement complexe et multi-niveaux\n"
        "- Combine plusieurs domaines ou concepts avancés\n"
        "- Résolution non triviale avec des subtilités ou pièges\n"
        "- Demande une analyse approfondie et une maîtrise solide des concepts\n"
        "- Peut inclure des modélisations, optimisations ou démonstrations\n"
    ),
}

# Alias pour compatibilité avec l'ancien code
DEFAULT_EXERCISE_PROMPT = DEFAULT_EXERCISE_PROMPTS["moyen"]


@dataclass
class Exercise:
    """Un exercice avec sa correction vérifiée."""
    statement: str  # Énoncé de l'exercice
    expected_answer: str  # Réponse attendue (numérique)
    steps: List[str] = field(default_factory=list)  # Étapes de résolution
    num_steps: int = 0  # Nombre d'étapes
    correction: str = ""  # Correction détaillée par IA
    verification_code: str = ""  # Code Python de vérification
    verified: bool = False  # La réponse a-t-elle été vérifiée ?
    verification_output: str = ""  # Sortie de la vérification
    source_pages: List[int] = field(default_factory=list)
    source_document: str = ""
    citation: str = ""
    difficulty_level: str = "moyen"  # facile / moyen / difficile


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
) -> tuple:
    """Construit le prompt pour la génération d'exercices."""

    notions_block = ""
    if notions_text:
        notions_block = f"\n\n{notions_text}\nLes exercices doivent tester la maîtrise pratique de ces notions fondamentales."

    prompts = custom_exercise_prompts or DEFAULT_EXERCISE_PROMPTS
    instructions = prompts.get(difficulty, prompts.get("moyen", ""))

    # Injecter les variables dynamiques dans la partie éditable
    instructions = instructions.replace("{num_exercises}", str(num_exercises))
    instructions = instructions.replace("{notions_block}", notions_block)

    # Assembler avec le bloc JSON fixe
    system_prompt = instructions.rstrip() + "\n\n" + EXERCISE_JSON_FORMAT

    doc_context = f" (document : {source_document})" if source_document else ""
    user_prompt = (
        f"Voici le texte source{doc_context} :\n\n---\n{text}\n---\n\n"
        f"Crée exactement {num_exercises} exercice(s) de niveau {difficulty} avec des réponses numériques vérifiables.\n"
        f"Rappel : l'énoncé doit être auto-suffisant et le code de vérification doit reproduire INTÉGRALEMENT les calculs."
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


def _verify_exercise_direct(exercise: Exercise) -> Exercise:
    """
    Vérification directe en exécutant le code Python dans un sous-processus isolé
    (fallback si l'agent échoue).
    
    Le code est exécuté dans un processus séparé avec un timeout pour éviter
    l'exécution de code malveillant dans le processus principal.
    """
    if not exercise.verification_code:
        exercise.verified = False
        exercise.verification_output = "Pas de code de vérification fourni."
        return exercise

    try:
        # Construire un script wrapper qui exécute le code et imprime le résultat
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

        # Écrire le code dans un fichier temporaire
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(wrapper_code)
            tmp_path = tmp_file.name

        try:
            # Exécuter dans un sous-processus avec timeout
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=SANDBOX_TIMEOUT,
                cwd=tempfile.gettempdir(),  # Répertoire de travail neutre
            )

            stdout = proc.stdout
            stderr = proc.stderr

            if proc.returncode != 0:
                exercise.verified = False
                exercise.verification_output = (
                    f"❌ Erreur lors de l'exécution (code retour {proc.returncode}) :\n"
                    f"{stderr[:500] if stderr else 'Pas de détails.'}"
                )
                return exercise

            # Chercher le résultat dans la sortie
            result_match = re.search(r'__RESULT__=(.+)', stdout)
            if result_match:
                result_value = result_match.group(1).strip()

                # Comparer avec la réponse attendue
                try:
                    expected = float(exercise.expected_answer.replace(',', '.'))
                    actual = float(result_value)
                    # Tolérance de 0.1% pour les arrondis
                    if abs(expected - actual) < abs(expected) * 0.001 + 0.01:
                        exercise.verified = True
                        exercise.verification_output = (
                            f"✅ Vérifié par exécution sandbox. "
                            f"Résultat obtenu : {actual}, attendu : {expected}"
                        )
                    else:
                        exercise.verified = False
                        exercise.verification_output = (
                            f"❌ Résultat incorrect. "
                            f"Obtenu : {actual}, attendu : {expected}"
                        )
                except ValueError:
                    # Comparaison en string
                    if result_value.strip() == exercise.expected_answer.strip():
                        exercise.verified = True
                        exercise.verification_output = "✅ Vérifié (comparaison texte)."
                    else:
                        exercise.verified = False
                        exercise.verification_output = (
                            f"❌ Résultat différent. "
                            f"Obtenu : {result_value}, attendu : {exercise.expected_answer}"
                        )
            else:
                exercise.verified = False
                exercise.verification_output = (
                    "⚠️ Le code de vérification n'a pas produit de variable résultat "
                    "(result, answer, res, etc.)\n"
                    f"Sortie standard : {stdout[:300] if stdout else '(vide)'}"
                )
        finally:
            # Nettoyage du fichier temporaire
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except subprocess.TimeoutExpired:
        exercise.verified = False
        exercise.verification_output = (
            f"⏱️ Timeout : le code de vérification a dépassé {SANDBOX_TIMEOUT}s."
        )
    except Exception as e:
        exercise.verified = False
        exercise.verification_output = f"❌ Erreur lors de l'exécution sandbox : {str(e)}"

    return exercise


def generate_exercises_from_chunk(
    chunk: TextChunk,
    num_exercises: int = 1,
    max_retries: int = 3,
    model: Optional[str] = None,
    notions_text: str = "",
    custom_exercise_prompts: Optional[dict] = None,
    difficulty: str = "moyen",
) -> List[Exercise]:
    """
    Génère des exercices à partir d'un chunk de texte avec vérification.
    Si la vérification échoue, re-génère l'exercice (max max_retries tentatives).
    """
    system_prompt, user_prompt = _build_exercise_prompt(
        chunk.text, num_exercises, notions_text=notions_text,
        source_document=chunk.source_document,
        difficulty=difficulty,
        custom_exercise_prompts=custom_exercise_prompts,
    )

    exercises = []

    for attempt in range(max_retries):
        try:
            result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.5)

            for ex_data in result.get("exercises", []):
                try:
                    source_page = ex_data.get("source_page")
                    if source_page:
                        source_pages = [source_page] if isinstance(source_page, int) else chunk.source_pages
                    else:
                        source_pages = chunk.source_pages

                    exercise = Exercise(
                        statement=ex_data["statement"],
                        expected_answer=str(ex_data["expected_answer"]),
                        steps=ex_data.get("steps", []),
                        num_steps=len(ex_data.get("steps", [])),
                        correction=ex_data.get("correction", ""),
                        verification_code=ex_data.get("verification_code", ""),
                        source_pages=source_pages,
                        source_document=chunk.source_document,
                        citation=ex_data.get("citation", ""),
                        difficulty_level=difficulty,
                    )

                    exercise = _verify_exercise_with_agent(exercise, model=model)
                    exercises.append(exercise)

                except (KeyError, TypeError):
                    continue

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
        from notion_detector import notions_to_prompt_text
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

    for i, (diff_name, chunk, n_ex) in enumerate(all_tasks):
        if progress_callback:
            progress_callback(i, total_steps)
        try:
            exercises = generate_exercises_from_chunk(
                chunk, n_ex, model=model, notions_text=notions_text,
                custom_exercise_prompts=custom_exercise_prompts,
                difficulty=diff_name,
            )
            all_exercises.extend(exercises)
        except Exception as e:
            print(f"Erreur sur le chunk {chunk.source_pages} ({diff_name}): {e}")
            continue

    if progress_callback:
        progress_callback(total_steps, total_steps)

    return all_exercises

