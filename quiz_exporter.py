"""
quiz_exporter.py — Export du quizz en HTML interactif standalone.
"""

import os
from jinja2 import Template

from quiz_generator import Quiz

# Chemin du template
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "quiz_template.html")


def export_quiz_html(quiz: Quiz) -> str:
    """
    Génère un fichier HTML interactif standalone pour le quizz.
    
    Args:
        quiz: Objet Quiz contenant les questions.
    
    Returns:
        Contenu HTML sous forme de string.
    """
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template_str = f.read()
    
    template = Template(template_str)
    
    # Préparer les données pour le template
    questions_data = []
    for i, q in enumerate(quiz.questions):
        questions_data.append({
            "index": i + 1,
            "question": q.question,
            "choices": q.choices,
            "correct_answers": q.correct_answers,
            "explanation": q.explanation,
            "num_correct": len(q.correct_answers),
            "is_multiple": len(q.correct_answers) > 1,
        })
    
    html = template.render(
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=questions_data,
        total_questions=len(questions_data),
        metadata=quiz.metadata,
    )
    
    return html
