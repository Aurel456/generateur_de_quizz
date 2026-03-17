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
            "difficulty_level": q.difficulty_level or "moyen",
            "source_document": q.source_document or "",
            "citation": q.citation or "",
            "source_pages": q.source_pages,
            "related_notions": getattr(q, 'related_notions', []) or [],
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
    header.extend(["Bonnes Réponses", "Explication", "Difficulté", "Citation", "Document Source", "Pages Source", "Notions"])
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
        row.append(getattr(q, 'difficulty_level', '') or '')
        row.append(getattr(q, 'citation', '') or '')
        row.append(getattr(q, 'source_document', '') or '')
        row.append(", ".join(map(str, q.source_pages)))
        row.append(", ".join(getattr(q, 'related_notions', []) or []))
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
    header = ["Énoncé", "Réponse Attendue", "Étapes de Résolution", "Correction IA", "Vérifié", "Citation", "Document Source", "Pages Source", "Notions"]
    writer.writerow(header)
    
    # Données
    for ex in exercises:
        row = [
            ex.statement,
            ex.expected_answer,
            "\n".join(ex.steps),
            ex.correction,
            "Oui" if ex.verified else "Non",
            getattr(ex, 'citation', '') or '',
            getattr(ex, 'source_document', '') or '',
            ", ".join(map(str, ex.source_pages)),
            ", ".join(getattr(ex, 'related_notions', []) or []),
        ]
        writer.writerow(row)

    return output.getvalue()


def export_exercises_html(exercises: list) -> str:
    """
    Génère un fichier HTML interactif standalone pour les exercices.
    
    Args:
        exercises: Liste d'objets Exercise.
    
    Returns:
        Contenu HTML sous forme de string.
    """
    exercises_html_parts = []
    for i, ex in enumerate(exercises, 1):
        verified_badge = (
            '<span class="badge verified">✅ Vérifié</span>'
            if ex.verified else
            '<span class="badge not-verified">⚠️ Non vérifié</span>'
        )
        
        steps_html = ""
        if ex.steps:
            steps_items = "".join(f"<li>{step}</li>" for step in ex.steps)
            steps_html = f'<h4>📊 Résolution ({len(ex.steps)} étapes)</h4><ol>{steps_items}</ol>'
        
        correction_html = ""
        if ex.correction:
            correction_html = f'<h4>🤖 Correction IA</h4><p>{ex.correction}</p>'
        
        code_html = ""
        if ex.verification_code:
            escaped_code = ex.verification_code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            code_html = (
                f'<details><summary>🔍 Code de vérification</summary>'
                f'<pre><code>{escaped_code}</code></pre></details>'
            )
        
        source_html = ""
        source_parts = []
        if ex.source_document:
            source_parts.append(f"📄 {ex.source_document}")
        if ex.source_pages:
            source_parts.append(f"p. {', '.join(map(str, ex.source_pages))}")
        if source_parts:
            source_html = f'<p class="source">Source : {", ".join(source_parts)}</p>'
        
        citation_html = ""
        if ex.citation:
            citation_html = f'<blockquote>📝 {ex.citation}</blockquote>'

        notions_html = ""
        ex_notions = getattr(ex, 'related_notions', []) or []
        if ex_notions:
            notion_tags = " ".join(
                f'<span class="notion-tag">{n}</span>' for n in ex_notions
            )
            notions_html = f'<div class="notion-tags">📚 {notion_tags}</div>'

        exercises_html_parts.append(f"""
        <div class="exercise-card">
            <div class="exercise-header">
                <h3>Exercice {i}</h3>
                {verified_badge}
            </div>
            {notions_html}
            <h4>📝 Énoncé</h4>
            <p>{ex.statement}</p>
            <h4>🎯 Réponse attendue : <code>{ex.expected_answer}</code></h4>
            {steps_html}
            {correction_html}
            {code_html}
            {citation_html}
            {source_html}
        </div>
        """)
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Exercices générés</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Inter', sans-serif; background: #0f0f1a; color: #e0e0e0; padding: 2rem; }}
    h1 {{ text-align: center; color: #6c63ff; margin-bottom: 2rem; }}
    .exercise-card {{
        background: #16213e; border: 1px solid #2a2a40; border-radius: 12px;
        padding: 1.5rem; margin-bottom: 1.5rem;
    }}
    .exercise-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
    .exercise-header h3 {{ color: #6c63ff; }}
    .badge {{
        padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600;
    }}
    .verified {{ background: rgba(0,200,83,0.15); color: #00c853; border: 1px solid rgba(0,200,83,0.3); }}
    .not-verified {{ background: rgba(255,171,0,0.15); color: #ffab00; border: 1px solid rgba(255,171,0,0.3); }}
    h4 {{ color: #a0a0ff; margin: 1rem 0 0.5rem 0; }}
    code {{ background: #1a1a2e; padding: 0.2rem 0.5rem; border-radius: 4px; color: #ff9800; }}
    pre {{ background: #1a1a2e; padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 0.5rem 0; }}
    pre code {{ background: none; padding: 0; }}
    ol {{ padding-left: 1.5rem; }}
    li {{ margin: 0.3rem 0; }}
    blockquote {{ border-left: 3px solid #6c63ff; padding-left: 1rem; margin: 0.5rem 0; font-style: italic; color: #a0a0b8; }}
    .source {{ color: #a0a0b8; font-size: 0.85rem; margin-top: 0.5rem; }}
    details {{ margin: 0.5rem 0; }}
    summary {{ cursor: pointer; color: #6c63ff; font-weight: 500; }}
    .notion-tags {{ margin: 0.5rem 0; }}
    .notion-tag {{
        display: inline-block; background: rgba(108,99,255,0.15); color: #6c63ff;
        padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.8rem;
        margin-right: 0.3rem; margin-bottom: 0.3rem;
    }}
</style>
</head>
<body>
<h1>🧮 Exercices générés</h1>
<p style="text-align: center; color: #a0a0b8; margin-bottom: 2rem;">
    {len(exercises)} exercice(s) — {sum(1 for e in exercises if e.verified)} vérifié(s)
</p>
{"".join(exercises_html_parts)}
</body>
</html>"""
    return html
