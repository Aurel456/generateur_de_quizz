"""
pages/work_session.py — Atelier de travail collaboratif pour formateurs.

Accessible via la barre latérale ou en ajoutant ?code=XXXXXX à l'URL.
Permet à plusieurs formateurs de co-éditer un brouillon de quizz.
"""

import json
import time

import streamlit as st

from sessions.session_store import (
    create_work_session, get_work_session, update_work_session_draft,
    publish_work_session, list_work_sessions,
)

st.set_page_config(
    page_title="Atelier Formateurs",
    page_icon="🛠️",
    layout="wide",
)

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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="ws-header"><h1>🛠️ Atelier Formateurs</h1></div>', unsafe_allow_html=True)
st.caption("Éditez un brouillon de quizz en équipe et publiez-le comme session étudiante.")

# ─── Session state ────────────────────────────────────────────────────────────

if "ws_code" not in st.session_state:
    st.session_state.ws_code = st.query_params.get("code", "")
if "ws_editor_name" not in st.session_state:
    st.session_state.ws_editor_name = ""
if "ws_editing_idx" not in st.session_state:
    st.session_state.ws_editing_idx = None
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

# ─── En-tête de l'atelier ────────────────────────────────────────────────────

col_h1, col_h2 = st.columns([5, 2])
with col_h1:
    st.markdown(f"## 📝 {ws.title}")
    st.caption(
        f"Code : `{ws.work_code}` · {len(questions)} question(s) · "
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
    # Recharge silencieuse (les modifications des collègues apparaîtront)

st.divider()

# ─── Liste des questions ──────────────────────────────────────────────────────

st.markdown(f"### 📋 Questions ({len(questions)})")

if not questions:
    st.info("Aucune question dans ce brouillon. Ajoutez des questions ci-dessous.")

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

            col_s, col_c, col_d = st.columns([2, 2, 1])
            with col_s:
                if st.button("💾 Sauvegarder", key=f"ws_save_{i}", type="primary"):
                    questions[i] = {
                        **q,
                        "question": edit_q,
                        "choices": edit_choices,
                        "correct_answers": edit_correct,
                        "explanation": edit_exp,
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
            st.markdown(q.get("question", ""))
            for label, text in q.get("choices", {}).items():
                icon = "✅" if label in q.get("correct_answers", []) else "⬜"
                st.markdown(f"**{icon} {label}.** {text}")
            if q.get("explanation"):
                st.info(f"💡 {q['explanation']}")

            col_edit, col_up, col_down = st.columns([3, 1, 1])
            with col_edit:
                if st.button("✏️ Éditer", key=f"ws_edit_{i}"):
                    st.session_state.ws_editing_idx = i
                    st.rerun()
            with col_up:
                if i > 0 and st.button("⬆️", key=f"ws_up_{i}", help="Monter"):
                    questions[i], questions[i - 1] = questions[i - 1], questions[i]
                    quiz_data["questions"] = questions
                    update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                    st.rerun()
            with col_down:
                if i < len(questions) - 1 and st.button("⬇️", key=f"ws_down_{i}", help="Descendre"):
                    questions[i], questions[i + 1] = questions[i + 1], questions[i]
                    quiz_data["questions"] = questions
                    update_work_session_draft(ws.work_code, quiz_data, editor_name or "?")
                    st.rerun()

st.divider()

# ─── Ajout d'une nouvelle question ───────────────────────────────────────────

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

st.divider()

# ─── Publication ─────────────────────────────────────────────────────────────

st.markdown("### 📡 Publier comme session étudiante")
st.caption("La session publiée sera accessible aux participants avec un code d'accès. L'atelier reste éditable.")

pub_title = st.text_input("Titre de la session", value=ws.title, key="ws_pub_title")
if st.button("📤 Publier", type="primary", disabled=not questions or ws.status == "published"):
    with st.spinner("Création de la session…"):
        session_obj = publish_work_session(ws.work_code, session_title=pub_title)
    if session_obj:
        st.success(f"Session publiée ! Code participant : **{session_obj.session_code}**")
        st.code(f"Code de session : {session_obj.session_code}", language=None)
    else:
        st.error("Erreur lors de la publication.")

st.markdown("---")
if st.button("← Retour à la liste des ateliers"):
    st.session_state.ws_code = ""
    st.query_params.clear()
    st.rerun()
