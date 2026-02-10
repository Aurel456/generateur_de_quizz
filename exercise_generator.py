"""
exercise_generator.py — Génération d'exercices avec vérification agentique via LangChain.

Les exercices ont des réponses numériques vérifiables par exécution de code Python.
"""

import re
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
from pdf_processor import TextChunk


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


def _get_langchain_llm():
    """Crée une instance ChatOpenAI pour LangChain."""
    return ChatOpenAI(
        model=MODEL_NAME,
        openai_api_base=OPENAI_API_BASE,
        openai_api_key=OPENAI_API_KEY,
        temperature=0.3,
        max_tokens=4000,
    )


def _build_exercise_prompt(text: str, num_exercises: int) -> tuple:
    """Construit le prompt pour la génération d'exercices."""
    
    system_prompt = f"""Tu es un expert pédagogique qui crée des exercices de niveau moyen à difficile.
Tu dois créer exactement {num_exercises} exercice(s) basé(s) sur le texte fourni.

RÈGLES STRICTES :
1. Chaque exercice doit avoir une réponse numérique claire et vérifiable
2. L'énoncé doit être clair et complet, sans ambiguïté
3. La résolution doit être décomposée en étapes claires et numérotées
4. Tu dois fournir un code Python qui calcule et vérifie la réponse
5. Le code Python doit afficher (print) le résultat final
6. Les exercices doivent être de niveau moyen à difficile (analyse, calcul, application)

TYPES D'EXERCICES ACCEPTÉS :
- Calculs basés sur des données du texte (pourcentages, proportions, statistiques)
- Problèmes d'application de formules mentionnées dans le texte
- Exercices de conversion ou de transformation de données
- Questions quantitatives nécessitant plusieurs étapes de raisonnement

FORMAT DE RÉPONSE (JSON strict) :
{{
    "exercises": [
        {{
            "statement": "Énoncé complet de l'exercice...",
            "expected_answer": "42.5",
            "steps": [
                "Étape 1 : Identifier les données...",
                "Étape 2 : Appliquer la formule...",
                "Étape 3 : Calculer le résultat..."
            ],
            "correction": "Correction détaillée avec explications pédagogiques...",
            "verification_code": "# Code Python\\nresult = 42.5\\nprint(f'Résultat: {{result}}')"
        }}
    ]
}}"""

    user_prompt = f"""Voici le texte source :

---
{text}
---

Crée exactement {num_exercises} exercice(s) de niveau moyen à difficile avec des réponses numériques vérifiables."""
    
    return system_prompt, user_prompt


def _verify_exercise_with_agent(exercise: Exercise) -> Exercise:
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
        llm = _get_langchain_llm()
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
    Vérification directe en exécutant le code Python (fallback si l'agent échoue).
    """
    try:
        # Exécuter le code dans un namespace isolé
        namespace = {}
        exec(exercise.verification_code, namespace)
        
        # Chercher les variables de résultat dans le namespace
        result_value = None
        for var_name in ['result', 'resultat', 'answer', 'reponse', 'res']:
            if var_name in namespace:
                result_value = namespace[var_name]
                break
        
        if result_value is not None:
            # Comparer avec la réponse attendue
            try:
                expected = float(exercise.expected_answer.replace(',', '.'))
                actual = float(result_value)
                # Tolérance de 0.1% pour les arrondis
                if abs(expected - actual) < abs(expected) * 0.001 + 0.01:
                    exercise.verified = True
                    exercise.verification_output = (
                        f"✅ Vérifié par exécution directe. "
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
                if str(result_value).strip() == exercise.expected_answer.strip():
                    exercise.verified = True
                    exercise.verification_output = f"✅ Vérifié (comparaison texte)."
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
                "(result, answer, res, etc.)"
            )
    except Exception as e:
        exercise.verified = False
        exercise.verification_output = f"❌ Erreur lors de l'exécution : {str(e)}"
    
    return exercise


def generate_exercises_from_chunk(
    chunk: TextChunk,
    num_exercises: int = 2,
    max_retries: int = 3
) -> List[Exercise]:
    """
    Génère des exercices à partir d'un chunk de texte avec vérification.
    
    Si la vérification échoue, re-génère l'exercice (max max_retries tentatives).
    """
    system_prompt, user_prompt = _build_exercise_prompt(chunk.text, num_exercises)
    
    exercises = []
    
    for attempt in range(max_retries):
        try:
            result = call_llm_json(system_prompt, user_prompt, temperature=0.5)
            
            for ex_data in result.get("exercises", []):
                try:
                    exercise = Exercise(
                        statement=ex_data["statement"],
                        expected_answer=str(ex_data["expected_answer"]),
                        steps=ex_data.get("steps", []),
                        num_steps=len(ex_data.get("steps", [])),
                        correction=ex_data.get("correction", ""),
                        verification_code=ex_data.get("verification_code", ""),
                        source_pages=chunk.source_pages,
                    )
                    
                    # Vérifier l'exercice via l'agent
                    exercise = _verify_exercise_with_agent(exercise)
                    exercises.append(exercise)
                    
                except (KeyError, TypeError) as e:
                    continue
            
            # Si on a assez d'exercices vérifiés, on arrête
            verified_count = sum(1 for ex in exercises if ex.verified)
            if verified_count >= num_exercises:
                break
                
        except Exception as e:
            print(f"Tentative {attempt + 1}/{max_retries} échouée : {e}")
            continue
    
    return exercises[:num_exercises]


def generate_exercises(
    chunks: List[TextChunk],
    num_exercises: int = 5,
    progress_callback=None
) -> List[Exercise]:
    """
    Génère des exercices à partir de plusieurs chunks.
    
    Args:
        chunks: Liste de TextChunk.
        num_exercises: Nombre total d'exercices souhaités.
        progress_callback: Fonction callback(current, total) pour la progression.
    
    Returns:
        Liste d'Exercise.
    """
    if not chunks:
        return []
    
    # Distribuer les exercices entre les chunks
    exercises_per_chunk = max(1, num_exercises // len(chunks))
    remaining = num_exercises
    
    all_exercises = []
    total_chunks = min(len(chunks), num_exercises)  # pas plus de chunks que d'exercices
    
    for i, chunk in enumerate(chunks[:total_chunks]):
        if remaining <= 0:
            break
        
        if progress_callback:
            progress_callback(i, total_chunks)
        
        n = min(exercises_per_chunk, remaining)
        if i == total_chunks - 1:
            n = remaining  # Dernier chunk prend le reste
        
        try:
            exercises = generate_exercises_from_chunk(chunk, n)
            all_exercises.extend(exercises)
            remaining -= len(exercises)
        except Exception as e:
            print(f"Erreur sur le chunk {i}: {e}")
            continue
    
    if progress_callback:
        progress_callback(total_chunks, total_chunks)
    
    return all_exercises[:num_exercises]
