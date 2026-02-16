"""
quiz_exporter.py — Export du quizz en HTML interactif standalone.
"""

import os
import io
import csv
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


def export_quiz_csv(quiz: Quiz) -> str:
    """
    Exporte le quizz au format CSV.
    
    Structure : Question, Choix A, Choix B, Choix C, Choix D, ..., Bonnes Réponses, Explication, Pages Source
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Trouver le nombre max de choix pour l'en-tête
    max_choices = 0
    for q in quiz.questions:
        max_choices = max(max_choices, len(q.choices))
    
    # En-tête
    header = ["Question"]
    for i in range(max_choices):
        header.append(f"Choix {chr(65 + i)}")
    header.extend(["Bonnes Réponses", "Explication", "Pages Source"])
    writer.writerow(header)
    
    # Données
    for q in quiz.questions:
        row = [q.question]
        # Ajouter les choix
        labels = sorted(q.choices.keys())
        for i in range(max_choices):
            if i < len(labels):
                row.append(q.choices[labels[i]])
            else:
                row.append("")
        
        row.append(", ".join(q.correct_answers))
        row.append(q.explanation)
        row.append(", ".join(map(str, q.source_pages)))
        writer.writerow(row)
    
    return output.getvalue()


def export_exercises_csv(exercises: list) -> str:
    """
    Exporte les exercices au format CSV.
    
    Structure : Énoncé, Réponse Attendue, Étapes, Correction, Vérifié, Pages Source
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # En-tête
    header = ["Énoncé", "Réponse Attendue", "Étapes de Résolution", "Correction IA", "Vérifié", "Pages Source"]
    writer.writerow(header)
    
    # Données
    for ex in exercises:
        row = [
            ex.statement,
            ex.expected_answer,
            "\n".join(ex.steps),
            ex.correction,
            "Oui" if ex.verified else "Non",
            ", ".join(map(str, ex.source_pages))
        ]
        writer.writerow(row)
    
    return output.getvalue()
