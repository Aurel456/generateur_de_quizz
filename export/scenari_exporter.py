"""
scenari_exporter.py — Export des quiz et exercices au format SCENARI (.quiz XML).

SCENARI (modèle ENT/Opale) attend un item XML par question. Ce module convertit
les dataclasses du projet (`QuizQuestion`, `Exercise`) vers les 5 primitives quiz
SCENARI rencontrées à l'import :

| Source projet                              | Primitive SCENARI   | Racine             |
|--------------------------------------------|---------------------|--------------------|
| QCM 1 bonne réponse (incl. Vrai/Faux)      | QCU                 | `ent:mcqSur`       |
| QCM plusieurs bonnes réponses              | QCM cases à cocher  | `ent:mcqMurBool`   |
| Exercice type "trou"                       | Texte à trou        | `ent:cloze`        |
| Exercice type "cas_pratique" / "calcul"    | Quiz rédactionnel   | `ent:practQuiz`    |

Chaque item est un fichier `.quiz` autonome ; `export_scenari_zip()` les regroupe
dans une archive ZIP importable dans un atelier SCENARI.
"""

import io
import re
import zipfile
from typing import List, Optional, Tuple

from generation.quiz_generator import Quiz

# Namespaces SCENARI (identiques aux exemples d'import fournis)
_XML_HEADER = '<?xml version="1.0"?>'
_ITEM_OPEN = (
    '<sc:item xmlns:ent="scenari:ENT" '
    'xmlns:sc="http://www.utc.fr/ics/scenari/v3/core" '
    'xmlns:sp="http://www.utc.fr/ics/scenari/v3/primitive">'
)
_ITEM_CLOSE = "</sc:item>"


# ─────────────────────────── Helpers XML ────────────────────────────

def _esc(text) -> str:
    """Échappe le texte pour insertion dans un nœud XML."""
    if text is None:
        return ""
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _para(text: str, em: bool = False) -> str:
    """Construit un unique `<sc:para>` (optionnellement en emphase)."""
    inner = _esc(text)
    if em:
        inner = f'<sc:inlineStyle role="em">{inner}</sc:inlineStyle>'
    return f'<sc:para xml:space="preserve">{inner}</sc:para>'


def _paras(text: str, em: bool = False) -> str:
    """Découpe un texte multi-lignes en plusieurs `<sc:para>`."""
    if not text:
        return _para("", em)
    lines = [ln for ln in str(text).split("\n")]
    # Conserver les lignes non vides ; au moins un para
    paras = [_para(ln, em) for ln in lines if ln.strip()]
    return "".join(paras) if paras else _para("", em)


def _txt(text: str, em: bool = False) -> str:
    """Bloc `<ent:txt>` contenant un ou plusieurs paragraphes."""
    return f"<ent:txt>{_paras(text, em)}</ent:txt>"


def _flow(text: str, em: bool = False) -> str:
    """Bloc riche `<ent:flow><sp:txt><ent:txt>…` utilisé pour question/explication."""
    return f"<ent:flow><sp:txt>{_txt(text, em)}</sp:txt></ent:flow>"


def _quizm(title: str) -> str:
    return f"<ent:quizM><sp:title>{_esc(title)}</sp:title></ent:quizM>"


def _slugify(text: str, fallback: str = "item") -> str:
    s = re.sub(r"[^\w\s-]", "", str(text or ""), flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s_-]+", "_", s)
    return s[:50] or fallback


def _short_title(text: str, max_len: int = 60) -> str:
    """Titre court pour `sp:title` (workspace SCENARI)."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s or "Question"


def _wrap_item(body: str) -> str:
    return f"{_XML_HEADER}\n{_ITEM_OPEN}{body}{_ITEM_CLOSE}"


# ─────────────────────────── QCM → SCENARI ──────────────────────────

def question_to_scenari(q, title: Optional[str] = None) -> str:
    """Convertit une `QuizQuestion` en item SCENARI (mcqSur ou mcqMurBool)."""
    labels = sorted(q.choices.keys())
    correct = set(q.correct_answers or [])
    item_title = title or _short_title(q.question)

    question_block = (
        f"<sc:question>{_flow(q.question, em=True)}</sc:question>"
    )

    if len(correct) <= 1:
        return _wrap_item(_build_mcq_sur(q, labels, item_title, question_block))
    return _wrap_item(_build_mcq_mur_bool(q, labels, correct, item_title, question_block))


def _build_mcq_sur(q, labels, item_title, question_block) -> str:
    """QCU : une seule bonne réponse, `<sc:solution choice="N"/>` (1-based)."""
    correct_label = (q.correct_answers or [None])[0]
    choices_xml = []
    solution_index = 1
    for i, label in enumerate(labels, start=1):
        is_correct = label == correct_label
        if is_correct:
            solution_index = i
        choice = f"<sc:choiceLabel>{_txt(q.choices[label])}</sc:choiceLabel>"
        if is_correct and q.explanation:
            choice += f"<sc:choiceExplanation>{_txt(q.explanation)}</sc:choiceExplanation>"
        choices_xml.append(f"<sc:choice>{choice}</sc:choice>")

    return (
        "<ent:mcqSur>"
        f"{_quizm(item_title)}"
        f"{question_block}"
        f"<sc:choices>{''.join(choices_xml)}</sc:choices>"
        f'<sc:solution choice="{solution_index}"/>'
        "</ent:mcqSur>"
    )


def _build_mcq_mur_bool(q, labels, correct, item_title, question_block) -> str:
    """QCM cases à cocher : `solution="checked"` sur les bonnes réponses."""
    choices_xml = []
    for label in labels:
        attr = ' solution="checked"' if label in correct else ""
        choices_xml.append(
            f"<sc:choice{attr}>"
            f"<sc:choiceLabel>{_txt(q.choices[label])}</sc:choiceLabel>"
            "</sc:choice>"
        )
    explanation_xml = ""
    if q.explanation:
        explanation_xml = f"<sc:globalExplanation>{_flow(q.explanation)}</sc:globalExplanation>"

    return (
        "<ent:mcqMurBool>"
        f"{_quizm(item_title)}"
        f"{question_block}"
        f"<sc:choices>{''.join(choices_xml)}</sc:choices>"
        f"{explanation_xml}"
        "</ent:mcqMurBool>"
    )


# ─────────────────────────── Exercice → SCENARI ─────────────────────

def exercise_to_scenari(ex, title: Optional[str] = None) -> str:
    """Convertit un `Exercise` en item SCENARI (cloze pour trou, practQuiz sinon)."""
    ex_type = getattr(ex, "exercise_type", "calcul")
    item_title = title or _short_title(ex.statement)
    if ex_type == "trou":
        return _wrap_item(_build_cloze(ex, item_title))
    return _wrap_item(_build_pract_quiz(ex, item_title))


def _build_cloze(ex, item_title) -> str:
    """Texte à trou : remplace les `___` par des `textLeaf role="gap"`.

    Chaque trou devient un menu déroulant (`sp:options`) si des variantes existent,
    sinon une simple saisie dont la bonne réponse est le texte du `textLeaf`.
    """
    blanks = getattr(ex, "blanks", []) or []
    statement = ex.statement or ""
    parts = statement.split("___")

    segments = [_esc(parts[0])] if parts else [""]
    for i in range(1, len(parts)):
        blank = blanks[i - 1] if i - 1 < len(blanks) else {}
        answer = blank.get("answer", "") if isinstance(blank, dict) else ""
        accepted = blank.get("accepted_answers", []) if isinstance(blank, dict) else []
        # Options du menu déroulant : la réponse + variantes acceptées (dédupliquées)
        options, seen = [], set()
        for opt in [answer, *accepted]:
            key = (opt or "").strip().lower()
            if opt and key not in seen:
                seen.add(key)
                options.append(opt)
        if len(options) >= 2:
            opts_xml = "".join(f"<sp:option>{_esc(o)}</sp:option>" for o in options)
            gap_m = f'<ent:gapM xml:space="default"><sp:options>{opts_xml}</sp:options></ent:gapM>'
        else:
            gap_m = '<ent:gapM xml:space="default"/>'
        segments.append(
            f'<sc:textLeaf role="gap">{gap_m}{_esc(answer)}</sc:textLeaf>'
        )
        segments.append(_esc(parts[i]))

    para = f'<sc:para xml:space="preserve">{"".join(segments)}</sc:para>'
    return (
        "<ent:cloze>"
        f"{_quizm(item_title)}"
        f"<sc:gapText><ent:clozeTxt>{para}</ent:clozeTxt></sc:gapText>"
        "</ent:cloze>"
    )


def _build_pract_quiz(ex, item_title) -> str:
    """Quiz rédactionnel : énoncé dans `sp:desc`, corrigé dans `sp:sol`."""
    # ── Énoncé (desc) ──
    desc_parts = [_paras(ex.statement)]
    sub_qs = getattr(ex, "sub_questions", []) or []
    if sub_qs:
        items = "".join(
            f'<sc:listItem>{_para(sq.get("question", ""))}</sc:listItem>'
            for sq in sub_qs if isinstance(sq, dict)
        )
        if items:
            desc_parts.append(f"<sc:orderedList>{items}</sc:orderedList>")
    desc_inner = "".join(desc_parts)
    desc = (
        f"<sp:desc><ent:flow><sp:txt><ent:txt>{desc_inner}</ent:txt></sp:txt></ent:flow></sp:desc>"
    )

    # ── Corrigé (sol) ──
    sol_parts = []
    expected = getattr(ex, "expected_answer", "") or ""
    if expected:
        sol_parts.append(_para(f"Réponse attendue : {expected}"))
    if sub_qs:
        items = "".join(
            f'<sc:listItem>{_para(sq.get("answer", ""))}</sc:listItem>'
            for sq in sub_qs if isinstance(sq, dict) and sq.get("answer")
        )
        if items:
            sol_parts.append(f"<sc:orderedList>{items}</sc:orderedList>")
    if getattr(ex, "steps", None):
        items = "".join(f"<sc:listItem>{_para(s)}</sc:listItem>" for s in ex.steps)
        sol_parts.append(f"<sc:orderedList>{items}</sc:orderedList>")
    if getattr(ex, "correction", ""):
        sol_parts.append(_paras(ex.correction))
    if getattr(ex, "pedagogical_comment", ""):
        sol_parts.append(_paras(ex.pedagogical_comment))
    if not sol_parts:
        sol_parts.append(_para(""))
    sol_inner = "".join(sol_parts)
    sol = (
        f"<sp:sol><ent:flow><sp:txt><ent:txt>{sol_inner}</ent:txt></sp:txt></ent:flow></sp:sol>"
    )

    return (
        "<ent:practQuiz>"
        f"{_quizm(item_title)}"
        f"<sp:quest><ent:practQuizQ>{desc}{sol}</ent:practQuizQ></sp:quest>"
        "</ent:practQuiz>"
    )


# ─────────────────────────── Assemblage ─────────────────────────────

def build_scenari_items(
    quiz: Optional[Quiz] = None,
    exercises: Optional[list] = None,
) -> List[Tuple[str, str]]:
    """Retourne la liste `(nom_fichier.quiz, contenu_xml)` pour tous les items."""
    items: List[Tuple[str, str]] = []
    used_names = set()

    def _unique_name(base: str) -> str:
        name = f"{base}.quiz"
        n = 2
        while name in used_names:
            name = f"{base}_{n}.quiz"
            n += 1
        used_names.add(name)
        return name

    if quiz and getattr(quiz, "questions", None):
        for i, q in enumerate(quiz.questions, start=1):
            xml = question_to_scenari(q)
            base = f"q{i:02d}_{_slugify(q.question, f'question_{i}')}"
            items.append((_unique_name(base), xml))

    if exercises:
        for i, ex in enumerate(exercises, start=1):
            xml = exercise_to_scenari(ex)
            ex_type = getattr(ex, "exercise_type", "calcul")
            base = f"ex{i:02d}_{ex_type}_{_slugify(ex.statement, f'exercice_{i}')}"
            items.append((_unique_name(base), xml))

    return items


def export_scenari_zip(
    quiz: Optional[Quiz] = None,
    exercises: Optional[list] = None,
) -> bytes:
    """Regroupe tous les items SCENARI dans une archive ZIP (bytes)."""
    items = build_scenari_items(quiz, exercises)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, xml in items:
            zf.writestr(filename, xml)
    return buffer.getvalue()
