"""
pages/work_session.py — Atelier de travail collaboratif pour formateurs.

Accessible via la barre latérale ou en ajoutant ?code=XXXXXX à l'URL.
Permet à plusieurs formateurs de co-éditer un brouillon de quizz et d'exercices.
"""

import json
import time

import streamlit as st

from sessions.session_store import (
    create_work_session, get_work_session, update_work_session_draft,
    publish_work_session, list_work_sessions,
)
from ui.ui_components import render_difficulty_badge, render_source_info

st.set_page_config(
    page_title="Atelier Formateurs",
    page_icon="🛠️",
    layout="wide",
)

# Auth gate — désactivé temporairement
# _ws_user = st.session_state.get("user")
# if _ws_user is None:
#     st.warning("Veuillez vous connecter depuis la page principale.")
#     st.stop()
# if _ws_user.role not in ("admin", "formateur"):
#     st.error("Accès réservé aux formateurs et administrateurs.")
#     st.stop()

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .ws-header { text-align: center; padding: 1rem 0 0.5rem; }
    .ws-header h1 {
        background: linear-gradient(135deg, #6c63ff 0%, #3f51b5 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 1.8rem; font-weight: 700;
    }
    .notion-tag {
        display: inline-block; background: rgba(108,99,255,0.15); color: #6c63ff;
        padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem;
        margin-right: 0.3rem; margin-bottom: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="ws-header"><h1>🛠️ Atelier Formateurs</h1></div>', unsafe_allow_html=True)
st.caption("Éditez un brouillon de quizz et d'exercices en équipe et publiez-le comme session étudiante.")

# ─── Session state ────────────────────────────────────────────────────────────

if "ws_code" not in st.session_state:
    st.session_state.ws_code = st.query_params.get("code", "")
if "ws_editor_name" not in st.session_state:
    st.session_state.ws_editor_name = ""
if "ws_editing_idx" not in st.session_state:
    st.session_state.ws_editing_idx = None
if "ws_editing_ex_idx" not in st.session_state:
    st.session_state.ws_editing_ex_idx = None
if "ws_last_refresh" not in st.session_state:
    st.session_state.ws_last_refresh = 0.0

# ─── Entrée / création d'un atelier ──────────────────────────────────────────

col_code, col_name = st.columns([3, 2])
with col_code:
    ws_code_input = st.text_input(
        "Code de l'atelier",
        value=st.session_state.ws_code,
        placeholder="Ex: K8S42X — laissez vide pour créer un nouvel atelier",
    )
with col_name:
    editor_name = st.text_input(
        "Votre nom",
        value=st.session_state.ws_editor_name,
        placeholder="Identifiant du formateur",
    )

if editor_name:
    st.session_state.ws_editor_name = editor_name

if ws_code_input and ws_code_input != st.session_state.ws_code:
    st.session_state.ws_code = ws_code_input.strip().upper()
    st.query_params["code"] = st.session_state.ws_code
    st.rerun()

if not st.session_state.ws_code:
    st.divider()
    st.markdown("### Créer un nouvel atelier")
    new_title = st.text_input("Titre du quizz", placeholder="Ex: QCM Réseaux — Chapitre 3")
    if st.button("➕ Créer l'atelier", type="primary", disabled=not new_title or not editor_name):
        ws = create_work_session({}, [], new_title, owner_name=editor_name)
        st.session_state.ws_code = ws.work_code
        st.query_params["code"] = ws.work_code
        st.success(f"Atelier créé ! Code : **{ws.work_code}**")
        st.rerun()

    st.divider()
    st.markdown("### Ateliers existants")
    ws_list = list_work_sessions()
    if not ws_list:
        st.info("Aucun atelier créé pour l'instant.")
    else:
        for ws in ws_list[:10]:
            status_icon = "✅" if ws.status == "published" else "📝"
            last_mod = ws.last_modified[:16].replace("T", " ")
            col_ws1, col_ws2 = st.columns([4, 1])
            with col_ws1:
                st.markdown(f"{status_icon} **{ws.title}** — `{ws.work_code}` — {last_mod} — par {ws.owner_name or '?'}")
            with col_ws2:
                if st.button("Ouvrir", key=f"open_ws_{ws.work_code}"):
                    st.session_state.ws_code = ws.work_code
                    st.query_params["code"] = ws.work_code
                    st.rerun()
    st.stop()

# ─── Charger l'atelier ────────────────────────────────────────────────────────

ws = get_work_session(st.session_state.ws_code)
if not ws:
    st.error(f"Atelier introuvable : **{st.session_state.ws_code}**")
    if st.button("← Retour"):
        st.session_state.ws_code = ""
        st.query_params.clear()
        st.rerun()
    st.stop()

quiz_data = json.loads(ws.draft_quiz_json)
questions = quiz_data.get("questions", [])
exercises = json.loads(ws.draft_exercises_json or "[]")

# ─── En-tête de l'atelier ────────────────────────────────────────────────────

col_h1, col_h2 = st.columns([5, 2])
with col_h1:
    st.markdown(f"## 📝 {ws.title}")
    st.caption(
        f"Code : `{ws.work_code}` · {len(questions)} question(s) · {len(exercises)} exercice(s) · "
        f"Dernière modification : {ws.last_modified[:16].replace('T', ' ')} par **{ws.owner_name or '?'}**"
    )
with col_h2:
    if st.button("🔃 Rafraîchir", help="Récupérer les modifications des collègues"):
        st.session_state.ws_last_refresh = time.time()
        st.rerun()

if ws.status == "published":
    st.info("Cet atelier a été publié comme session étudiante.")

# ─── Auto-rafraîchissement toutes les 30 s ────────────────────────────────────

if time.time() - st.session_state.ws_last_refresh > 30:
    st.session_state.ws_last_refresh = time.time()

# ─── Helper function pour affichage exercice ─────────────────────────────────

def _render_ws_exercise(idx, ex, exercises_list, ws, quiz_data, editor_name):
    """Affiche un exercice dans l'atelier avec mode lecture/édition."""
    diff_label = ex.get("difficulty_level", "moyen")
    diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
    ex_type = ex.get("exercise_type", "calcul")
    type_icon = {"calcul": "🔢", "trou": "✏️", "cas_pratique": "📋"}.get(ex_type, "📝")
    verified = ex.get("verified", False)
    verified_label = "✅ Vérifié" if verified else "⚠️ Non vérifié"
    is_editing = (st.session_state.ws_editing_ex_idx == idx)

    with st.expander(
        f"{diff_emoji} {type_icon} Exercice {idx+1} — {verified_label}",
        expanded=is_editing,
    ):
        if is_editing:
            # ── Mode édition exercice ────────────────────────────────────
            edit_statement = st.text_area("Énoncé", value=ex.get("statement", ""), key=f"ws_ex_stmt_{idx}", height=120)
            edit_ex_diff = st.selectbox(
                "Difficulté", ["facile", "moyen", "difficile"],
                index=["facile", "moyen", "difficile"].index(diff_label) if diff_label in ["facile", "moyen", "difficile"] else 1,
                key=f"ws_ex_diff_{idx}",
            )

            if ex_type == "trou":
                st.markdown("**Réponses des blancs** (JSON)")
                edit_blanks_str = st.text_area(
                    "blanks (JSON)", value=json.dumps(ex.get("blanks", []), ensure_ascii=False, indent=2),
                    key=f"ws_ex_blanks_{idx}", height=120,
                )
            elif ex_type == "cas_pratique":
                st.markdown("**Sous-questions** (JSON)")
                edit_subq_str = st.text_area(
                    "sub_questions (JSON)", value=json.dumps(ex.get("sub_questions", []), ensure_ascii=False, indent=2),
                    key=f"ws_ex_subq_{idx}", height=120,
                )
            else:
                edit_answer = st.text_input("Réponse attendue", value=ex.get("expected_answer", ""), key=f"ws_ex_ans_{idx}")

            edit_correction = st.text_area("Correction", value=ex.get("correction", ""), key=f"ws_ex_corr_{idx}", height=80)

            col_s, col_c, col_d = st.columns([2, 2, 1])
            with col_s:
                if st.button("💾 Sauvegarder", key=f"ws_ex_save_{idx}", type="primary"):
                    exercises_list[idx] = {
                        **ex,
                        "statement": edit_statement,
                        "difficulty_level": edit_ex_diff,
                        "correction": edit_correction,
                    }
                    if ex_type == "trou":
                        try:
                            exercises_list[idx]["blanks"] = json.loads(edit_blanks_str)
                        except json.JSONDecodeError:
                            st.error("JSON invalide pour les blancs.")
                            return
                    elif ex_type == "cas_pratique":
                        try:
                            exercises_list[idx]["sub_questions"] = json.loads(edit_subq_str)
                        except json.JSONDecodeError:
                            st.error("JSON invalide pour les sous-questions.")
                            return
                    else:
                        exercises_list[idx]["expected_answer"] = edit_answer
                    update_work_session_draft(
                        ws.work_code, quiz_data, editor_name or "?",
                        exercises_data=exercises_list,
                    )
                    st.session_state.ws_editing_ex_idx = None
                    st.rerun()
            with col_c:
                if st.button("✖️ Annuler", key=f"ws_ex_cancel_{idx}"):
                    st.session_state.ws_editing_ex_idx = None
                    st.rerun()
            with col_d:
                if st.button("🗑️", key=f"ws_ex_del_{idx}", help="Supprimer"):
                    exercises_list.pop(idx)
                    update_work_session_draft(
                        ws.work_code, quiz_data, editor_name or "?",
                        exercises_data=exercises_list,
                    )
                    st.session_state.ws_editing_ex_idx = None
                    st.rerun()
        else:
            # ── Mode lecture exercice ────────────────────────────────────
            render_difficulty_badge(diff_label)

            related_notions = ex.get("related_notions", [])
            if related_notions:
                tags_html = " ".join(f'<span class="notion-tag">{n}</span>' for n in related_notions)
                st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

            st.markdown("#### 📝 Énoncé")
            st.markdown(ex.get("statement", ""))

            if ex_type == "trou":
                blanks = ex.get("blanks", [])
                if blanks:
                    st.markdown("#### ✏️ Réponses attendues")
                    for b in blanks:
                        b_pos = b.get("position", "?")
                        st.markdown(f"**Blanc {b_pos} :** `{b.get('answer', '')}` — *{b.get('context', '')}*")
            elif ex_type == "cas_pratique":
                sub_qs = ex.get("sub_questions", [])
                if sub_qs:
                    st.markdown("#### ❓ Sous-questions & Réponses")
                    for j, sq in enumerate(sub_qs):
                        st.markdown(f"**Q{j+1} :** {sq.get('question', '')}")
                        st.markdown(f"> {sq.get('answer', '')}")
                if ex.get("verification_code"):
                    with st.expander("🔍 Code de vérification"):
                        st.code(ex["verification_code"], language="python")
            else:
                sub_parts = ex.get("sub_parts", [])
                if sub_parts:
                    st.markdown("#### 🔢 Questions")
                    for sp_idx, sp in enumerate(sub_parts):
                        sp_verified = sp.get("verified", False)
                        sp_icon = "✅" if sp_verified else "⚠️"
                        st.markdown(f"**{sp_icon} Q{sp_idx+1}.** {sp.get('question', '')}")
                        st.markdown(f"🎯 Réponse attendue : `{sp.get('expected_answer', '')}`")
                        sp_steps = sp.get("steps", [])
                        if sp_steps:
                            for sj, sstep in enumerate(sp_steps):
                                st.markdown(f"   {sj+1}. {sstep}")
                        st.markdown("---")
                else:
                    if ex.get("expected_answer"):
                        st.markdown(f"#### 🎯 Réponse attendue : `{ex['expected_answer']}`")
                    steps = ex.get("steps", [])
                    if steps:
                        st.markdown(f"#### 📊 Résolution ({len(steps)} étapes)")
                        for j, step in enumerate(steps):
                            st.markdown(f"**{j+1}.** {step}")

                if ex.get("verification_code"):
                    with st.expander("🔍 Code de vérification"):
                        st.code(ex["verification_code"], language="python")

            if ex.get("correction"):
                st.markdown("#### 🤖 Correction")
                st.markdown(ex["correction"])

            render_source_info(ex.get("source_document"), ex.get("source_pages"))

            if ex.get("citation"):
                st.caption(f"📝 *\"{ex['citation']}\"*")

            if st.button("✏️ Éditer", key=f"ws_ex_edit_{idx}"):
                st.session_state.ws_editing_ex_idx = idx
                st.rerun()


# ─── Onglets Questions / Exercices ───────────────────────────────────────────

tab_quiz, tab_exercises, tab_tools = st.tabs([
    f"📋 Questions ({len(questions)})",
    f"🧮 Exercices ({len(exercises)})",
    "🔧 Outils",
])


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET QUESTIONS
# ══════════════════════════════════════════════════════════════════════════════

with tab_quiz:
    if not questions:
        st.info("Aucune question dans ce brouillon. Ajoutez des questions ci-dessous ou exportez depuis l'app principale.")

    for i, q in enumerate(questions):
        diff_label = q.get("difficulty_level", "moyen")
        diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
        is_editing = (st.session_state.ws_editing_idx == i)

        with st.expander(f"{diff_emoji} Q{i+1}. {q.get('question', '')[:90]}…", expanded=is_editing):
            if is_editing:
                # ── Mode édition ────────────────────────────────────────────────
                edit_q = st.text_area("Énoncé", value=q.get("question", ""), key=f"ws_q_{i}", height=80)
                st.markdown("**Choix de réponse**")
                edit_choices = {}
                for label, text in q.get("choices", {}).items():
                    edit_choices[label] = st.text_input(f"Choix {label}", value=text, key=f"ws_c_{i}_{label}")
                edit_correct = st.multiselect(
                    "Bonne(s) réponse(s)",
                    options=list(q.get("choices", {}).keys()),
                    default=q.get("correct_answers", []),
                    key=f"ws_corr_{i}",
                )
                edit_exp = st.text_area("Explication", value=q.get("explanation", ""), key=f"ws_e_{i}", height=60)
                edit_diff = st.selectbox(
                    "Difficulté", ["facile", "moyen", "difficile"],
                    index=["facile", "moyen", "difficile"].index(diff_label) if diff_label in ["facile", "moyen", "difficile"] else 1,
                    key=f"ws_diff_{i}",
                )

                col_s, col_c, col_d = st.columns([2, 2, 1])
                with col_s:
                    if st.button("💾 Sauvegarder", key=f"ws_save_{i}", type="primary"):
                        questions[i] = {
                            **q,
                            "question": edit_q,
                            "choices": edit_choices,
                            "correct_answers": edit_correct,
                            "explanation": edit_exp,
                            "difficulty_level": edit_diff,
                        }
                        quiz_data["questions"] = questions
                        update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                        st.session_state.ws_editing_idx = None
                        st.rerun()
                with col_c:
                    if st.button("✖️ Annuler", key=f"ws_cancel_{i}"):
                        st.session_state.ws_editing_idx = None
                        st.rerun()
                with col_d:
                    if st.button("🗑️", key=f"ws_del_{i}", help="Supprimer"):
                        questions.pop(i)
                        quiz_data["questions"] = questions
                        update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                        st.session_state.ws_editing_idx = None
                        st.rerun()
            else:
                # ── Mode lecture ─────────────────────────────────────────────────
                render_difficulty_badge(diff_label)

                related_notions = q.get("related_notions", [])
                if related_notions:
                    tags_html = " ".join(f'<span class="notion-tag">{n}</span>' for n in related_notions)
                    st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

                st.markdown(q.get("question", ""))
                for label, text in q.get("choices", {}).items():
                    icon = "✅" if label in q.get("correct_answers", []) else "⬜"
                    st.markdown(f"**{icon} {label}.** {text}")
                if q.get("explanation"):
                    st.info(f"💡 {q['explanation']}")

                render_source_info(q.get("source_document"), q.get("source_pages"))

                if q.get("citation"):
                    st.caption(f"📝 *\"{q['citation']}\"*")

                col_edit, col_up, col_down = st.columns([2, 1, 1])
                with col_edit:
                    if st.button("✏️ Éditer", key=f"ws_edit_{i}"):
                        st.session_state.ws_editing_idx = i
                        st.rerun()
                with col_up:
                    if i > 0 and st.button("⬆️", key=f"ws_up_{i}", help="Monter"):
                        questions[i], questions[i-1] = questions[i-1], questions[i]
                        quiz_data["questions"] = questions
                        update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                        st.rerun()
                with col_down:
                    if i < len(questions) - 1 and st.button("⬇️", key=f"ws_down_{i}", help="Descendre"):
                        questions[i], questions[i+1] = questions[i+1], questions[i]
                        quiz_data["questions"] = questions
                        update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                        st.rerun()

    # ─── Ajout d'une nouvelle question ───────────────────────────────────────
    st.divider()
    with st.expander("➕ Ajouter une question manuellement"):
        new_q_text = st.text_area("Énoncé", key="ws_new_q", height=70)
        new_choices = {}
        for lbl in ["A", "B", "C", "D"]:
            new_choices[lbl] = st.text_input(f"Choix {lbl}", key=f"ws_new_c_{lbl}")
        new_correct = st.multiselect(
            "Bonne(s) réponse(s)", options=["A", "B", "C", "D"], key="ws_new_corr"
        )
        new_diff = st.selectbox("Difficulté", ["facile", "moyen", "difficile"], index=1, key="ws_new_diff")
        new_exp = st.text_area("Explication", key="ws_new_exp", height=60)

        if st.button("Ajouter la question", disabled=not new_q_text or not new_correct):
            questions.append({
                "question": new_q_text,
                "choices": {k: v for k, v in new_choices.items() if v},
                "correct_answers": new_correct,
                "difficulty_level": new_diff,
                "explanation": new_exp,
                "related_notions": [],
                "source_pages": [],
                "source_document": "",
                "citation": "",
            })
            quiz_data["questions"] = questions
            update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET EXERCICES
# ══════════════════════════════════════════════════════════════════════════════

with tab_exercises:
    if not exercises:
        st.info("Aucun exercice dans ce brouillon. Exportez des exercices depuis l'app principale.")

    # Grouper par type
    type_labels = {"calcul": "🔢 Calcul", "trou": "✏️ Questions à trou", "cas_pratique": "📋 Cas pratique"}
    type_groups = {}
    for idx, ex in enumerate(exercises):
        t = ex.get("exercise_type", "calcul")
        type_groups.setdefault(t, []).append((idx, ex))

    if len(type_groups) > 1:
        tab_names = [f"{type_labels.get(t, t)} ({len(exs)})" for t, exs in type_groups.items()]
        ex_tabs = st.tabs(tab_names)
        for ex_tab, (t, exs) in zip(ex_tabs, type_groups.items()):
            with ex_tab:
                for orig_idx, ex in exs:
                    _render_ws_exercise(orig_idx, ex, exercises, ws, quiz_data, editor_name)
    else:
        for idx, ex in enumerate(exercises):
            _render_ws_exercise(idx, ex, exercises, ws, quiz_data, editor_name)

    # ─── Ajout manuel d'exercice ─────────────────────────────────────────────
    st.divider()
    with st.expander("➕ Ajouter un exercice manuellement"):
        new_ex_type = st.selectbox(
            "Type", ["calcul", "trou", "cas_pratique"],
            format_func=lambda x: type_labels.get(x, x),
            key="ws_new_ex_type",
        )
        new_ex_statement = st.text_area("Énoncé", key="ws_new_ex_statement", height=100)
        new_ex_diff = st.selectbox("Difficulté", ["facile", "moyen", "difficile"], index=1, key="ws_new_ex_diff")
        new_ex_answer = st.text_input("Réponse attendue", key="ws_new_ex_answer")
        new_ex_correction = st.text_area("Correction / Explication", key="ws_new_ex_correction", height=80)

        if st.button("Ajouter l'exercice", disabled=not new_ex_statement, key="ws_add_ex_btn"):
            exercises.append({
                "statement": new_ex_statement,
                "expected_answer": new_ex_answer,
                "steps": [],
                "correction": new_ex_correction,
                "verification_code": "",
                "verified": False,
                "source_pages": [],
                "source_document": "",
                "citation": "",
                "difficulty_level": new_ex_diff,
                "related_notions": [],
                "exercise_type": new_ex_type,
                "blanks": [],
                "sub_questions": [],
            })
            update_work_session_draft(
                ws.work_code, quiz_data, editor_name or "?",
                exercises_data=exercises,
            )
            st.rerun()

    if exercises:
        st.divider()
        if st.button("🗑️ Effacer tous les exercices", key="ws_clear_all_ex"):
            update_work_session_draft(
                ws.work_code, quiz_data, editor_name or "?",
                exercises_data=[],
            )
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ONGLET OUTILS
# ══════════════════════════════════════════════════════════════════════════════

with tab_tools:
    # ─── Vue diff (original vs brouillon actuel) ────────────────────────────
    original_questions = json.loads(ws.original_quiz_json) if ws.original_quiz_json else []
    if isinstance(original_questions, dict):
        original_questions = original_questions.get("questions", [])

    if original_questions:
        with st.expander("📊 Voir les modifications par rapport à l'original"):
            orig_texts = {q.get("question", "").strip(): q for q in original_questions}
            curr_texts = {q.get("question", "").strip(): q for q in questions}

            added = [q for txt, q in curr_texts.items() if txt not in orig_texts]
            removed = [q for txt, q in orig_texts.items() if txt not in curr_texts]
            modified = []
            for txt, q in curr_texts.items():
                if txt in orig_texts:
                    oq = orig_texts[txt]
                    if (q.get("choices") != oq.get("choices")
                            or q.get("correct_answers") != oq.get("correct_answers")
                            or q.get("explanation") != oq.get("explanation")):
                        modified.append((oq, q))

            if not added and not removed and not modified:
                st.success("Aucune modification par rapport à l'original.")
            else:
                st.markdown(f"**{len(added)}** ajoutée(s) · **{len(removed)}** supprimée(s) · **{len(modified)}** modifiée(s)")

                for q in added:
                    st.markdown(
                        f'<div style="border-left:4px solid #4caf50;padding:4px 12px;margin:6px 0;background:#e8f5e9;">'
                        f'<b>+ Ajoutée :</b> {q.get("question","")[:120]}</div>',
                        unsafe_allow_html=True,
                    )
                for q in removed:
                    st.markdown(
                        f'<div style="border-left:4px solid #f44336;padding:4px 12px;margin:6px 0;background:#ffebee;">'
                        f'<b>− Supprimée :</b> {q.get("question","")[:120]}</div>',
                        unsafe_allow_html=True,
                    )
                for oq, nq in modified:
                    details = []
                    if oq.get("choices") != nq.get("choices"):
                        details.append("choix")
                    if oq.get("correct_answers") != nq.get("correct_answers"):
                        details.append("réponses")
                    if oq.get("explanation") != nq.get("explanation"):
                        details.append("explication")
                    st.markdown(
                        f'<div style="border-left:4px solid #ff9800;padding:4px 12px;margin:6px 0;background:#fff3e0;">'
                        f'<b>~ Modifiée ({", ".join(details)}) :</b> {nq.get("question","")[:120]}</div>',
                        unsafe_allow_html=True,
                    )

    # ─── Importer / fusionner ────────────────────────────────────────────────
    st.divider()
    with st.expander("🔗 Importer des questions depuis une session existante"):
        from sessions.session_store import get_session as _get_session
        import_code = st.text_input("Code de la session à importer", key="ws_import_code", placeholder="Ex: K8S42X")
        if st.button("📥 Importer", disabled=not import_code, key="ws_import_btn"):
            source_session = _get_session(import_code.strip().upper())
            if source_session is None:
                st.error(f"Session introuvable : {import_code}")
            else:
                import_data = json.loads(source_session.quiz_json)
                imported_qs = import_data.get("questions", [])
                if source_session.pool_json:
                    imported_qs = json.loads(source_session.pool_json)
                imported_exs = json.loads(source_session.exercises_json or "[]")
                if not imported_qs and not imported_exs:
                    st.warning("Cette session ne contient aucune question ni exercice.")
                else:
                    if imported_qs:
                        questions.extend(imported_qs)
                        quiz_data["questions"] = questions
                    if imported_exs:
                        exercises.extend(imported_exs)
                    update_work_session_draft(
                        ws.work_code, quiz_data, editor_name or "?",
                        exercises_data=exercises if imported_exs else None,
                    )
                    parts = []
                    if imported_qs:
                        parts.append(f"{len(imported_qs)} question(s)")
                    if imported_exs:
                        parts.append(f"{len(imported_exs)} exercice(s)")
                    st.success(f"✅ {' et '.join(parts)} importés.")
                    st.rerun()

    with st.expander("🔀 Fusionner depuis un autre atelier"):
        merge_code = st.text_input("Code de l'atelier à fusionner", key="ws_merge_code", placeholder="Ex: AB1234")
        if st.button("🔀 Fusionner", disabled=not merge_code, key="ws_merge_btn"):
            merge_ws = get_work_session(merge_code.strip().upper())
            if merge_ws is None:
                st.error(f"Atelier introuvable : {merge_code}")
            else:
                merge_data = json.loads(merge_ws.draft_quiz_json)
                merge_qs = merge_data.get("questions", [])
                merge_exs = json.loads(merge_ws.draft_exercises_json or "[]")
                if not merge_qs and not merge_exs:
                    st.warning("Cet atelier ne contient aucune question ni exercice.")
                else:
                    if merge_qs:
                        questions.extend(merge_qs)
                        quiz_data["questions"] = questions
                    if merge_exs:
                        exercises.extend(merge_exs)
                    update_work_session_draft(
                        ws.work_code, quiz_data, editor_name or "?",
                        exercises_data=exercises if merge_exs else None,
                    )
                    parts = []
                    if merge_qs:
                        parts.append(f"{len(merge_qs)} question(s)")
                    if merge_exs:
                        parts.append(f"{len(merge_exs)} exercice(s)")
                    st.success(f"✅ {' et '.join(parts)} fusionnés depuis l'atelier {merge_code.strip().upper()}.")
                    st.rerun()

    # ─── Publication ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📡 Publier comme session étudiante")
    st.caption("La session publiée sera accessible aux participants avec un code d'accès. L'atelier reste éditable.")

    pub_title = st.text_input("Titre de la session", value=ws.title, key="ws_pub_title")

    pool_mode = st.toggle("🎲 Mode pool (sous-ensemble aléatoire par participant)", value=False, key="ws_pool_mode")
    if pool_mode and len(questions) >= 2:
        col_pool1, col_pool2 = st.columns(2)
        with col_pool1:
            subset_size = st.slider(
                "Questions par participant",
                min_value=1, max_value=len(questions), value=min(10, len(questions)),
                key="ws_pool_subset",
            )
        with col_pool2:
            pass_threshold = st.slider(
                "Seuil de validation (%)",
                min_value=0, max_value=100, value=70, step=5,
                key="ws_pool_threshold",
            ) / 100.0
    elif pool_mode:
        st.warning("Il faut au moins 2 questions pour activer le mode pool.")
        subset_size = len(questions)
        pass_threshold = 0.7

    has_content = bool(questions) or bool(exercises)
    if st.button("📤 Publier", type="primary", disabled=not has_content or ws.status == "published"):
        with st.spinner("Création de la session…"):
            if pool_mode and len(questions) >= 2:
                session_obj = publish_work_session(
                    ws.work_code, session_title=pub_title,
                    pool_mode=True, subset_size=subset_size, pass_threshold=pass_threshold,
                )
            else:
                session_obj = publish_work_session(ws.work_code, session_title=pub_title)
        if session_obj:
            mode_label = " (mode pool)" if pool_mode and len(questions) >= 2 else ""
            st.success(f"Session publiée{mode_label} ! Code participant : **{session_obj.session_code}**")
            st.code(f"Code de session : {session_obj.session_code}", language=None)
        else:
            st.error("Erreur lors de la publication.")

st.markdown("---")
if st.button("← Retour à la liste des ateliers"):
    st.session_state.ws_code = ""
    st.query_params.clear()
    st.rerun()
