"""
quiz_generator.py — Génération de quizz QCM à partir de chunks de texte.
"""

import string
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from llm_service import call_llm_json, count_tokens, MODEL_CONTEXT_WINDOW
from document_processor import TextChunk


@dataclass
class QuizQuestion:
    """Une question de quizz QCM."""
    question: str
    choices: Dict[str, str]  # {"A": "...", "B": "...", ...}
    correct_answers: List[str]  # ["A", "C"]
    explanation: str = ""
    source_pages: List[int] = field(default_factory=list)


@dataclass
class Quiz:
    """Un quizz complet."""
    title: str
    difficulty: str
    questions: List[QuizQuestion] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# Mapping difficulté → instructions pour le LLM
DIFFICULTY_PROMPTS = {
    "facile": (
        "Génère des questions FACILES basées sur des faits explicites du texte. "
        "Les questions doivent porter sur des informations directement mentionnées, "
        "des définitions, des dates, ou des faits simples. "
        "Les mauvaises réponses doivent être clairement fausses."
    ),
    "moyen": (
        "Génère des questions de difficulté MOYENNE qui testent la compréhension du texte. "
        "Les questions peuvent nécessiter de relier plusieurs informations, "
        "comprendre des concepts, ou interpréter des données. "
        "Les mauvaises réponses doivent être plausibles mais incorrectes."
    ),
    "difficile": (
        "Génère des questions DIFFICILES qui testent l'analyse et la synthèse. "
        "Les questions doivent nécessiter une réflexion approfondie, "
        "la capacité à faire des inférences, ou à appliquer des concepts. "
        "Les mauvaises réponses doivent être très plausibles et subtiles. "
        "Inclure des questions qui combinent plusieurs parties du texte."
    ),
}


def _build_quiz_prompt(
    text: str,
    difficulty: str,
    num_questions: int,
    num_choices: int,
    num_correct: int,
    choice_labels: List[str],
    difficulty_prompts: Optional[Dict[str, str]] = None
) -> tuple:
    """Construit le prompt système et utilisateur pour la génération de quizz."""
    
    labels_str = ", ".join(choice_labels[:num_choices])
    prompts = difficulty_prompts or DIFFICULTY_PROMPTS
    diff_instruction = prompts.get(difficulty, DIFFICULTY_PROMPTS.get(difficulty, ""))
    
    system_prompt = f"""Tu es un expert en pédagogie et en création de quizz éducatifs.
Tu dois générer exactement {num_questions} questions QCM (Questions à Choix Multiples).

RÈGLES STRICTES :
1. Chaque question doit avoir exactement {num_choices} choix de réponse ({labels_str})
2. Chaque question doit avoir exactement {num_correct} bonne(s) réponse(s)
3. {diff_instruction}
4. Chaque question doit inclure une explication de la réponse
5. Les questions doivent être variées et couvrir différentes parties du texte
6. Les choix de réponse doivent être du même type et de longueur similaire

FORMAT DE RÉPONSE (JSON strict) :
{{
    "questions": [
        {{
            "question": "La question posée ?",
            "choices": {{{", ".join(f'"{l}": "Choix {l}"' for l in choice_labels[:num_choices])}}},
            "correct_answers": {list(choice_labels[:num_correct])},
            "explanation": "Explication détaillée de la bonne réponse..."
        }}
    ]
}}"""

    user_prompt = f"""Voici le texte source pour générer les questions :

---
{text}
---

Génère exactement {num_questions} questions QCM de niveau {difficulty}."""
    
    return system_prompt, user_prompt


def generate_quiz_from_chunk(
    chunk: TextChunk,
    difficulty: str = "moyen",
    num_questions: int = 5,
    num_choices: int = 4,
    num_correct: int = 1,
    difficulty_prompts: Optional[Dict[str, str]] = None,
    model: Optional[str] = None
) -> List[QuizQuestion]:
    """
    Génère des questions de quizz à partir d'un seul chunk de texte.
    """
    # Générer les labels de choix (A, B, C, ...)
    choice_labels = list(string.ascii_uppercase[:num_choices])
    
    system_prompt, user_prompt = _build_quiz_prompt(
        chunk.text, difficulty, num_questions, num_choices, num_correct, choice_labels, difficulty_prompts
    )
    
    # Appel au LLM
    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.6)
    
    # Parser les questions
    questions = []
    for q_data in result.get("questions", []):
        try:
            question = QuizQuestion(
                question=q_data["question"],
                choices=q_data["choices"],
                correct_answers=q_data["correct_answers"],
                explanation=q_data.get("explanation", ""),
                source_pages=chunk.source_pages
            )
            # Validation : vérifier que les bonnes réponses sont dans les choix
            if all(ans in question.choices for ans in question.correct_answers):
                questions.append(question)
        except (KeyError, TypeError):
            continue  # Skip les questions mal formées
    
    return questions


def generate_quiz(
    chunks: List[TextChunk],
    difficulty: Optional[str] = None,
    num_questions: Optional[int] = None,
    difficulty_counts: Optional[Dict[str, int]] = None,
    num_choices: int = 4,
    num_correct: int = 1,
    difficulty_prompts: Optional[Dict[str, str]] = None,
    model: Optional[str] = None,
    progress_callback=None
) -> Quiz:
    """
    Génère un quizz complet à partir de plusieurs chunks.
    
    Args:
        chunks: Liste de TextChunk.
        difficulty: "facile", "moyen", ou "difficile" (si difficulty_counts est None).
        num_questions: Nombre total (si difficulty_counts est None).
        difficulty_counts: Dict {difficulté: nombre}. Ex: {"facile": 5, "moyen": 10}.
        num_choices: Nombre de choix par question (4-7).
        num_correct: Nombre de bonnes réponses par question.
        difficulty_prompts: Prompts personnalisés.
        model: Modèle LLM à utiliser.
        progress_callback: Fonction callback(current, total) pour la progression.
    
    Returns:
        Quiz complet.
    """
    if not chunks:
        return Quiz(title="Quizz vide", difficulty="mixte")

    # Déterminer les comptes par difficulté
    if difficulty_counts is None:
        if difficulty is None or num_questions is None:
            difficulty_counts = {"moyen": 10}
        else:
            difficulty_counts = {difficulty: num_questions}
    
    total_requested = sum(difficulty_counts.values())
    all_questions = []
    
    # Pour chaque difficulté demandée, on répartit sur les chunks
    diff_keys = [k for k, v in difficulty_counts.items() if v > 0]
    total_steps = len(diff_keys) * len(chunks)
    current_step = 0

    for diff_name, diff_count in difficulty_counts.items():
        if diff_count <= 0:
            continue
            
        # Distribuer les questions de cette difficulté entre les chunks
        total_tokens = sum(c.token_count for c in chunks)
        questions_per_chunk = []
        remaining = diff_count
        
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                n = max(remaining, 0)
            else:
                ratio = chunk.token_count / total_tokens if total_tokens > 0 else 1 / len(chunks)
                n = round(diff_count * ratio)
                n = min(n, remaining)
            questions_per_chunk.append(n)
            remaining -= n
            if remaining <= 0:
                # Combler le reste avec des 0 pour avoir la même longueur que chunks
                questions_per_chunk.extend([0] * (len(chunks) - len(questions_per_chunk)))
                break
        
        # Générer
        for i, (chunk, n_questions) in enumerate(zip(chunks, questions_per_chunk)):
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps)
            
            if n_questions <= 0:
                continue
                
            try:
                questions = generate_quiz_from_chunk(
                    chunk=chunk,
                    difficulty=diff_name,
                    num_questions=n_questions,
                    num_choices=num_choices,
                    num_correct=num_correct,
                    difficulty_prompts=difficulty_prompts,
                    model=model
                )
                all_questions.extend(questions)
            except Exception as e:
                print(f"Erreur sur le chunk {i} ({diff_name}): {e}")
                continue

    if progress_callback:
        progress_callback(total_steps, total_steps)
    
    quiz = Quiz(
        title="Quizz généré depuis PDF",
        difficulty=", ".join(diff_keys) if len(diff_keys) > 1 else (diff_keys[0] if diff_keys else "inconnue"),
        questions=all_questions,
        metadata={
            "difficulty_counts": difficulty_counts,
            "num_choices": num_choices,
            "num_correct_per_question": num_correct,
            "total_questions_generated": len(all_questions),
            "model": model
        }
    )
    
    return quiz

