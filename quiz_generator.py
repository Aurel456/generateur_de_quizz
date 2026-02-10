"""
quiz_generator.py — Génération de quizz QCM à partir de chunks de texte.
"""

import string
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from llm_service import call_llm_json, count_tokens, MODEL_CONTEXT_WINDOW
from pdf_processor import TextChunk


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
    choice_labels: List[str]
) -> tuple:
    """Construit le prompt système et utilisateur pour la génération de quizz."""
    
    labels_str = ", ".join(choice_labels[:num_choices])
    
    system_prompt = f"""Tu es un expert en pédagogie et en création de quizz éducatifs.
Tu dois générer exactement {num_questions} questions QCM (Questions à Choix Multiples).

RÈGLES STRICTES :
1. Chaque question doit avoir exactement {num_choices} choix de réponse ({labels_str})
2. Chaque question doit avoir exactement {num_correct} bonne(s) réponse(s)
3. {DIFFICULTY_PROMPTS[difficulty]}
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
    num_correct: int = 1
) -> List[QuizQuestion]:
    """
    Génère des questions de quizz à partir d'un seul chunk de texte.
    """
    # Générer les labels de choix (A, B, C, ...)
    choice_labels = list(string.ascii_uppercase[:num_choices])
    
    system_prompt, user_prompt = _build_quiz_prompt(
        chunk.text, difficulty, num_questions, num_choices, num_correct, choice_labels
    )
    
    # Appel au LLM
    result = call_llm_json(system_prompt, user_prompt, temperature=0.6)
    
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
    difficulty: str = "moyen",
    num_questions: int = 10,
    num_choices: int = 4,
    num_correct: int = 1,
    progress_callback=None
) -> Quiz:
    """
    Génère un quizz complet à partir de plusieurs chunks.
    
    Distribue les questions entre les chunks proportionnellement à leur taille,
    puis combine les résultats.
    
    Args:
        chunks: Liste de TextChunk.
        difficulty: "facile", "moyen", ou "difficile".
        num_questions: Nombre total de questions souhaitées.
        num_choices: Nombre de choix par question (4-7).
        num_correct: Nombre de bonnes réponses par question.
        progress_callback: Fonction callback(current, total) pour la progression.
    
    Returns:
        Quiz complet.
    """
    if not chunks:
        return Quiz(title="Quizz vide", difficulty=difficulty)
    
    # Distribuer les questions entre les chunks
    total_tokens = sum(c.token_count for c in chunks)
    questions_per_chunk = []
    remaining = num_questions
    
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            # Dernier chunk : prend les questions restantes
            n = max(remaining, 1)
        else:
            # Proportionnel à la taille du chunk
            ratio = chunk.token_count / total_tokens if total_tokens > 0 else 1 / len(chunks)
            n = max(1, round(num_questions * ratio))
            n = min(n, remaining)
        questions_per_chunk.append(n)
        remaining -= n
        if remaining <= 0:
            break
    
    # Générer les questions par chunk
    all_questions = []
    total_chunks = len(questions_per_chunk)
    
    for i, (chunk, n_questions) in enumerate(zip(chunks, questions_per_chunk)):
        if n_questions <= 0:
            continue
        
        if progress_callback:
            progress_callback(i, total_chunks)
        
        try:
            questions = generate_quiz_from_chunk(
                chunk, difficulty, n_questions, num_choices, num_correct
            )
            all_questions.extend(questions)
        except Exception as e:
            # Log l'erreur mais continue avec les autres chunks
            print(f"Erreur sur le chunk {i}: {e}")
            continue
    
    if progress_callback:
        progress_callback(total_chunks, total_chunks)
    
    # Limiter au nombre demandé
    all_questions = all_questions[:num_questions]
    
    quiz = Quiz(
        title="Quizz généré depuis PDF",
        difficulty=difficulty,
        questions=all_questions,
        metadata={
            "num_chunks_used": total_chunks,
            "num_choices": num_choices,
            "num_correct_per_question": num_correct,
            "total_questions_generated": len(all_questions),
        }
    )
    
    return quiz
