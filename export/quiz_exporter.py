"""
quiz_exporter.py — Export du quizz et exercices en HTML interactif standalone et CSV.
"""

import os
import io
import csv
from typing import List, Optional

from jinja2 import Template

from generation.quiz_generator import Quiz

# Chemin du template (remonter d'un niveau depuis export/ vers la racine du projet)
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
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


def _sanitize_csv_field(value: str) -> str:
    """Nettoie un champ pour l'export CSV : remplace les retours à la ligne."""
    if not value:
        return ""
    return value.replace("\r\n", " | ").replace("\n", " | ").replace("\r", " | ")


def export_quiz_csv(quiz: Quiz) -> str:
    """
    Exporte le quizz au format CSV (séparateur ;, guillemets systématiques, BOM UTF-8).

    Structure : Question, Choix A, Choix B, Choix C, Choix D, ..., Bonnes Réponses, Explication, Pages Source
    """
    output = io.StringIO()
    # BOM UTF-8 pour qu'Excel détecte automatiquement l'encodage
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)

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
        row = [_sanitize_csv_field(q.question)]
        labels = sorted(q.choices.keys())
        for i in range(max_choices):
            if i < len(labels):
                row.append(_sanitize_csv_field(q.choices[labels[i]]))
            else:
                row.append("")

        row.append(" | ".join(q.correct_answers))
        row.append(_sanitize_csv_field(q.explanation))
        row.append(getattr(q, 'difficulty_level', '') or '')
        row.append(_sanitize_csv_field(getattr(q, 'citation', '') or ''))
        row.append(getattr(q, 'source_document', '') or '')
        row.append(" | ".join(map(str, q.source_pages)))
        row.append(" | ".join(getattr(q, 'related_notions', []) or []))
        writer.writerow(row)

    return output.getvalue()


def export_exercises_csv(exercises: list) -> str:
    """
    Exporte les exercices au format CSV (séparateur ;, guillemets systématiques, BOM UTF-8).

    Structure : Énoncé, Réponse Attendue, Étapes, Correction, Vérifié, Pages Source
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)

    # En-tête
    header = ["Énoncé", "Réponse Attendue", "Étapes de Résolution", "Correction IA", "Vérifié", "Citation", "Document Source", "Pages Source", "Notions"]
    writer.writerow(header)

    # Données
    for ex in exercises:
        row = [
            _sanitize_csv_field(ex.statement),
            ex.expected_answer,
            " | ".join(ex.steps),
            _sanitize_csv_field(ex.correction),
            "Oui" if ex.verified else "Non",
            _sanitize_csv_field(getattr(ex, 'citation', '') or ''),
            getattr(ex, 'source_document', '') or '',
            " | ".join(map(str, ex.source_pages)),
            " | ".join(getattr(ex, 'related_notions', []) or []),
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


def export_combined_html(quiz: Optional[Quiz], exercises: Optional[list]) -> str:
    """
    Génère un fichier HTML combiné avec quiz QCM + exercices dans un seul document.
    Utilise des onglets CSS/JS pour naviguer entre les sections.
    """
    import re as _re

    quiz_section = ""
    exercises_section = ""
    quiz_count = 0
    ex_count = 0

    # Section Quiz
    if quiz and quiz.questions:
        quiz_count = len(quiz.questions)
        quiz_html = export_quiz_html(quiz)
        body_match = _re.search(r'<body[^>]*>(.*?)</body>', quiz_html, _re.DOTALL)
        if body_match:
            quiz_section = body_match.group(1)
        else:
            quiz_section = f"<p>{quiz_count} questions générées</p>"

    # Section Exercices
    if exercises:
        ex_count = len(exercises)
        ex_html = export_exercises_html(exercises)
        body_match = _re.search(r'<body[^>]*>(.*?)</body>', ex_html, _re.DOTALL)
        if body_match:
            exercises_section = body_match.group(1)
        else:
            exercises_section = f"<p>{ex_count} exercices générés</p>"

    title = quiz.title if quiz else "Export combiné"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Quiz + Exercices</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Inter', sans-serif; background: #0f0f1a; color: #e0e0e0; }}
    .tabs {{ display: flex; justify-content: center; gap: 1rem; padding: 1.5rem; background: #16213e; border-bottom: 2px solid #2a2a40; }}
    .tab-btn {{
        padding: 0.7rem 1.5rem; border-radius: 8px; border: 1px solid #2a2a40;
        background: transparent; color: #a0a0b8; font-size: 1rem; font-weight: 600;
        cursor: pointer; transition: all 0.2s;
    }}
    .tab-btn:hover {{ background: rgba(108,99,255,0.1); color: #6c63ff; }}
    .tab-btn.active {{ background: #6c63ff; color: #fff; border-color: #6c63ff; }}
    .tab-content {{ display: none; padding: 2rem; }}
    .tab-content.active {{ display: block; }}
    .combined-header {{
        text-align: center; padding: 2rem; background: linear-gradient(135deg, #16213e, #1a1a2e);
    }}
    .combined-header h1 {{ color: #6c63ff; margin-bottom: 0.5rem; }}
    .combined-header p {{ color: #a0a0b8; }}
    .exercise-card {{
        background: #16213e; border: 1px solid #2a2a40; border-radius: 12px;
        padding: 1.5rem; margin-bottom: 1.5rem;
    }}
    .exercise-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
    .exercise-header h3 {{ color: #6c63ff; }}
    .badge {{ padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
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
    .notion-tag {{
        display: inline-block; background: rgba(108,99,255,0.15); color: #6c63ff;
        padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.8rem;
        margin-right: 0.3rem; margin-bottom: 0.3rem;
    }}
</style>
</head>
<body>
<div class="combined-header">
    <h1>{title}</h1>
    <p>{quiz_count} question(s) QCM — {ex_count} exercice(s)</p>
</div>
<div class="tabs">
    {"<button class='tab-btn active' onclick='switchTab(\"quiz\")'>QCM (" + str(quiz_count) + ")</button>" if quiz_count else ""}
    {"<button class='tab-btn" + (" active" if not quiz_count else "") + "' onclick='switchTab(\"exercises\")'>Exercices (" + str(ex_count) + ")</button>" if ex_count else ""}
</div>
<div id="tab-quiz" class="tab-content {"active" if quiz_count else ""}">{quiz_section}</div>
<div id="tab-exercises" class="tab-content {"active" if not quiz_count and ex_count else ""}">{exercises_section}</div>
<script>
function switchTab(tab) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    event.target.classList.add('active');
}}
</script>
</body>
</html>"""
    return html


def export_combined_csv(quiz: Optional[Quiz], exercises: Optional[list]) -> str:
    """
    Exporte quiz + exercices dans un seul CSV avec séparateurs de sections.
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_ALL)

    if quiz and quiz.questions:
        writer.writerow(["=== QUIZ QCM ==="])
        writer.writerow([])
        max_choices = max(len(q.choices) for q in quiz.questions)
        header = ["Question"]
        for i in range(max_choices):
            header.append(f"Choix {chr(65 + i)}")
        header.extend(["Bonnes Réponses", "Explication", "Difficulté", "Citation", "Document Source", "Pages Source", "Notions"])
        writer.writerow(header)
        for q in quiz.questions:
            row = [_sanitize_csv_field(q.question)]
            labels = sorted(q.choices.keys())
            for i in range(max_choices):
                row.append(_sanitize_csv_field(q.choices[labels[i]]) if i < len(labels) else "")
            row.append(" | ".join(q.correct_answers))
            row.append(_sanitize_csv_field(q.explanation))
            row.append(getattr(q, 'difficulty_level', '') or '')
            row.append(_sanitize_csv_field(getattr(q, 'citation', '') or ''))
            row.append(getattr(q, 'source_document', '') or '')
            row.append(" | ".join(map(str, q.source_pages)))
            row.append(" | ".join(getattr(q, 'related_notions', []) or []))
            writer.writerow(row)
        writer.writerow([])

    if exercises:
        writer.writerow(["=== EXERCICES ==="])
        writer.writerow([])
        header = ["Type", "Énoncé", "Réponse Attendue", "Étapes", "Correction IA", "Vérifié", "Citation", "Document Source", "Pages Source", "Notions"]
        writer.writerow(header)
        for ex in exercises:
            row = [
                getattr(ex, 'exercise_type', 'calcul'),
                _sanitize_csv_field(ex.statement),
                ex.expected_answer,
                " | ".join(ex.steps) if ex.steps else "",
                _sanitize_csv_field(ex.correction),
                "Oui" if ex.verified else "Non",
                _sanitize_csv_field(getattr(ex, 'citation', '') or ''),
                getattr(ex, 'source_document', '') or '',
                " | ".join(map(str, ex.source_pages)),
                " | ".join(getattr(ex, 'related_notions', []) or []),
            ]
            writer.writerow(row)

    return output.getvalue()
