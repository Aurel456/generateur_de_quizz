"""
question_editor.py — Amélioration d'une question QCM par instruction LLM.

Permet au formateur de demander une modification en langage naturel
(reformulation, correction, ajout de distracteurs, etc.) sur une question existante.
"""

from typing import Optional

from core.llm_service import call_llm_json
from generation.quiz_generator import QuizQuestion


def improve_question_with_llm(
    question: QuizQuestion,
    instruction: str,
    source_text: str = "",
    model: Optional[str] = None,
) -> QuizQuestion:
    """
    Améliore une question QCM selon une instruction en langage naturel.

    Préserve les labels des bonnes réponses, source_pages, difficulty_level,
    source_document et related_notions sauf instruction explicite contraire.

    Args:
        question: Question actuelle à modifier.
        instruction: Instruction du formateur (ex: "Rends l'explication plus claire").
        source_text: Extrait du document source (optionnel, améliore la qualité).
        model: Modèle LLM à utiliser.

    Returns:
        QuizQuestion mise à jour.
    """
    choices_text = "\n".join(
        f"  {label}. {text}" for label, text in question.choices.items()
    )
    correct_labels = ", ".join(question.correct_answers)

    source_block = ""
    if source_text:
        source_block = f"""
DOCUMENT SOURCE (pour référence) :
---
{source_text[:3000]}
---
"""

    system_prompt = """Tu es un expert en création de QCM pédagogiques. Tu reçois une question existante et une instruction du formateur pour l'améliorer.

RÈGLES ABSOLUES :
1. Applique uniquement ce que demande l'instruction — ne modifie pas ce qui n'est pas demandé.
2. Conserve les labels des bonnes réponses (si A est correct, A reste correct) sauf instruction explicite.
3. La question doit rester auto-suffisante (ne pas référencer "le texte" ou "le document").
4. L'explication doit justifier clairement pourquoi la/les bonne(s) réponse(s) est/sont correcte(s).
5. Conserve le même niveau de difficulté sauf instruction contraire.

FORMAT DE RÉPONSE (JSON strict) :
{
    "question": "Énoncé de la question",
    "choices": {"A": "Choix A", "B": "Choix B", "C": "Choix C", "D": "Choix D"},
    "correct_answers": ["A"],
    "explanation": "Explication de la bonne réponse",
    "citation": "Citation exacte du document justifiant la réponse (si disponible)"
}"""

    user_prompt = f"""QUESTION ACTUELLE :
{question.question}

CHOIX :
{choices_text}

BONNES RÉPONSES : {correct_labels}

EXPLICATION ACTUELLE : {question.explanation}

CITATION ACTUELLE : {question.citation}
{source_block}
INSTRUCTION DU FORMATEUR : {instruction}

Applique l'instruction et retourne la question mise à jour."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.4)

    return QuizQuestion(
        question=result.get("question", question.question),
        choices=result.get("choices", question.choices),
        correct_answers=result.get("correct_answers", question.correct_answers),
        explanation=result.get("explanation", question.explanation),
        citation=result.get("citation", question.citation),
        source_pages=question.source_pages,
        difficulty_level=question.difficulty_level,
        source_document=question.source_document,
        related_notions=question.related_notions,
    )
