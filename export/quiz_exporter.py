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
        ex_type = getattr(ex, "exercise_type", "calcul")
        if ex.verified:
            verif_method = "code" if ex_type == "calcul" else "LLM"
            verified_badge = f'<span class="badge verified">✅ Vérifié ({verif_method})</span>'
        else:
            verified_badge = '<span class="badge not-verified">⚠️ Non vérifié</span>'

        diff_label = getattr(ex, "difficulty_level", "moyen") or "moyen"
        diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
        type_label = {"calcul": "🔢 Calcul", "trou": "✏️ Trou", "cas_pratique": "📋 Cas pratique"}.get(ex_type, ex_type)

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

        # Contenu spécifique au type (visible = énoncé, caché = correction)
        type_content_html = ""
        answer_html = ""

        if ex_type == "trou":
            blanks = getattr(ex, "blanks", []) or []
            if blanks:
                answer_items = "".join(
                    f'<li><strong>Blanc {b.get("position", "?")} :</strong> <code>{b.get("answer", "")}</code> — <em>{b.get("context", "")}</em></li>'
                    for b in blanks
                )
                answer_html = f'<h4>✏️ Réponses attendues</h4><ol>{answer_items}</ol>'
        elif ex_type == "cas_pratique":
            sub_qs = getattr(ex, "sub_questions", []) or []
            if sub_qs:
                # Questions visibles, réponses cachées
                q_items = "".join(
                    f'<li><strong>Q{j+1} :</strong> {sq.get("question", "")}</li>'
                    for j, sq in enumerate(sub_qs)
                )
                type_content_html = f'<h4>❓ Questions</h4><ol>{q_items}</ol>'
                a_items = "".join(
                    f'<li><strong>Q{j+1} :</strong> {sq.get("answer", "")}</li>'
                    for j, sq in enumerate(sub_qs)
                )
                answer_html = f'<h4>❓ Réponses</h4><ol>{a_items}</ol>'
        else:
            # Calcul
            sub_parts = getattr(ex, "sub_parts", []) or []
            if sub_parts:
                # Multi-questions: show questions visible, answers hidden
                q_items = "".join(
                    f'<li><strong>Q{sp_idx+1} :</strong> {sp.get("question", "")}</li>'
                    for sp_idx, sp in enumerate(sub_parts)
                )
                type_content_html = f'<h4>🔢 Questions</h4><ol>{q_items}</ol>'
                sp_answers = ""
                for sp_idx, sp in enumerate(sub_parts):
                    sp_icon = "✅" if sp.get("verified") else "⚠️"
                    sp_answers += f'<li>{sp_icon} <strong>Q{sp_idx+1} :</strong> <code>{sp.get("expected_answer", "")}</code>'
                    sp_steps = sp.get("steps", [])
                    if sp_steps:
                        sp_answers += "<ol>" + "".join(f"<li>{s}</li>" for s in sp_steps) + "</ol>"
                    sp_answers += "</li>"
                answer_html = f'<h4>🎯 Réponses</h4><ol>{sp_answers}</ol>'
            else:
                answer_html = f'<h4>🎯 Réponse attendue : <code>{ex.expected_answer}</code></h4>'
                if ex.steps:
                    steps_items = "".join(f"<li>{step}</li>" for step in ex.steps)
                    answer_html += f'<h4>📊 Résolution ({len(ex.steps)} étapes)</h4><ol>{steps_items}</ol>'

        # Correction IA + code de vérification (toujours cachés)
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

        exercises_html_parts.append(f"""
        <div class="exercise-card" id="exercise-{i}">
            <div class="exercise-header">
                <h3>{diff_emoji} Exercice {i} <span class="type-badge">{type_label}</span></h3>
                {verified_badge}
            </div>
            {notions_html}
            <h4>📝 Énoncé</h4>
            <p>{ex.statement}</p>
            {type_content_html}
            <button class="reveal-btn" onclick="toggleAnswer({i})">👁️ Voir la correction</button>
            <div class="answer-section" id="answer-{i}" style="display:none;">
                {answer_html}
                {correction_html}
                {code_html}
                {citation_html}
            </div>
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
    .type-badge {{
        font-size: 0.75rem; font-weight: 500; color: #a0a0b8;
        margin-left: 0.5rem;
    }}
    .reveal-btn {{
        display: inline-block; margin-top: 1rem; padding: 0.5rem 1.2rem;
        border-radius: 8px; border: 1px solid #6c63ff; background: rgba(108,99,255,0.1);
        color: #6c63ff; font-size: 0.9rem; font-weight: 600; cursor: pointer;
        transition: all 0.2s;
    }}
    .reveal-btn:hover {{ background: rgba(108,99,255,0.25); }}
    .answer-section {{
        margin-top: 1rem; padding-top: 1rem;
        border-top: 1px dashed #2a2a40;
    }}
</style>
</head>
<body>
<h1>🧮 Exercices générés</h1>
<p style="text-align: center; color: #a0a0b8; margin-bottom: 2rem;">
    {len(exercises)} exercice(s) — {sum(1 for e in exercises if e.verified)} vérifié(s)
</p>
{"".join(exercises_html_parts)}
<script>
function toggleAnswer(exId) {{
    var section = document.getElementById('answer-' + exId);
    var btn = section.previousElementSibling;
    if (section.style.display === 'none') {{
        section.style.display = 'block';
        btn.textContent = '🙈 Masquer la correction';
    }} else {{
        section.style.display = 'none';
        btn.textContent = '👁️ Voir la correction';
    }}
}}
</script>
</body>
</html>"""
    return html


def _extract_html_parts(html: str) -> dict:
    """Extrait les blocs <style>, <body> et <script> d'un HTML complet."""
    import re as _re
    css = ""
    js = ""
    body = ""
    # CSS : tout le contenu entre <style> et </style>
    for m in _re.finditer(r'<style[^>]*>(.*?)</style>', html, _re.DOTALL):
        css += m.group(1) + "\n"
    # JS : tout le contenu entre <script> et </script>
    for m in _re.finditer(r'<script[^>]*>(.*?)</script>', html, _re.DOTALL):
        js += m.group(1) + "\n"
    # Body content
    body_match = _re.search(r'<body[^>]*>(.*)</body>', html, _re.DOTALL)
    if body_match:
        # Retirer les balises <script> du body (déjà extraites)
        body = _re.sub(r'<script[^>]*>.*?</script>', '', body_match.group(1), flags=_re.DOTALL).strip()
    return {"css": css, "js": js, "body": body}


def export_combined_html(quiz: Optional[Quiz], exercises: Optional[list]) -> str:
    """
    Génère un fichier HTML combiné avec quiz QCM + exercices dans un seul document.
    Extrait proprement CSS, JS et body de chaque export pour les assembler.
    """
    quiz_parts = {"css": "", "js": "", "body": ""}
    ex_parts = {"css": "", "js": "", "body": ""}
    quiz_count = 0
    ex_count = 0

    if quiz and quiz.questions:
        quiz_count = len(quiz.questions)
        quiz_html = export_quiz_html(quiz)
        quiz_parts = _extract_html_parts(quiz_html)

    if exercises:
        ex_count = len(exercises)
        ex_html = export_exercises_html(exercises)
        ex_parts = _extract_html_parts(ex_html)

    title = quiz.title if quiz else "Export combiné"

    # Assembler le CSS combiné (tabs + quiz + exercices)
    combined_css = f"""
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    /* --- Onglets combinés --- */
    .combined-tabs {{ display: flex; justify-content: center; gap: 1rem; padding: 1.5rem; background: #16213e; border-bottom: 2px solid #2a2a40; position: sticky; top: 0; z-index: 200; }}
    .combined-tab-btn {{
        padding: 0.7rem 1.5rem; border-radius: 8px; border: 1px solid #2a2a40;
        background: transparent; color: #a0a0b8; font-size: 1rem; font-weight: 600;
        cursor: pointer; transition: all 0.2s;
    }}
    .combined-tab-btn:hover {{ background: rgba(108,99,255,0.1); color: #6c63ff; }}
    .combined-tab-btn.active {{ background: #6c63ff; color: #fff; border-color: #6c63ff; }}
    .combined-tab-content {{ display: none; }}
    .combined-tab-content.active {{ display: block; }}
    .combined-header {{
        text-align: center; padding: 2rem; background: linear-gradient(135deg, #16213e, #1a1a2e);
    }}
    .combined-header h1 {{ color: #6c63ff; margin-bottom: 0.5rem; }}
    .combined-header p {{ color: #a0a0b8; }}
    /* --- CSS Quiz --- */
    {quiz_parts["css"]}
    /* --- CSS Exercices --- */
    {ex_parts["css"]}
    """

    # Assembler le JS combiné (tabs + quiz + exercices)
    combined_js = f"""
    /* --- Onglets --- */
    function switchCombinedTab(tab) {{
        document.querySelectorAll('.combined-tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.combined-tab-btn').forEach(el => el.classList.remove('active'));
        document.getElementById('combined-tab-' + tab).classList.add('active');
        event.target.classList.add('active');
    }}
    /* --- JS Quiz --- */
    {quiz_parts["js"]}
    /* --- JS Exercices --- */
    {ex_parts["js"]}
    """

    quiz_tab_btn = f'<button class="combined-tab-btn active" onclick="switchCombinedTab(\'quiz\')">QCM ({quiz_count})</button>' if quiz_count else ""
    ex_tab_btn = f'<button class="combined-tab-btn{" active" if not quiz_count else ""}" onclick="switchCombinedTab(\'exercises\')">Exercices ({ex_count})</button>' if ex_count else ""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Quiz + Exercices</title>
<style>{combined_css}</style>
</head>
<body>
<div class="combined-header">
    <h1>{title}</h1>
    <p>{quiz_count} question(s) QCM — {ex_count} exercice(s)</p>
</div>
<div class="combined-tabs">
    {quiz_tab_btn}
    {ex_tab_btn}
</div>
<div id="combined-tab-quiz" class="combined-tab-content {"active" if quiz_count else ""}">{quiz_parts["body"]}</div>
<div id="combined-tab-exercises" class="combined-tab-content {"active" if not quiz_count and ex_count else ""}">{ex_parts["body"]}</div>
<script>{combined_js}</script>
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
