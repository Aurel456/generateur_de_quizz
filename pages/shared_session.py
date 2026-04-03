"""
shared_session.py — Page Streamlit pour la gestion des sessions partagées.

Consultez les sessions de quizz partagées, les questions et les analytics.
"""

import json
import streamlit as st

from sessions.session_store import list_sessions, get_session, deactivate_session
from sessions.analytics import render_analytics_dashboard
from ui.ui_components import render_difficulty_badge

st.set_page_config(
    page_title="📡 Sessions Partagées",
    page_icon="📡",
    layout="wide",
)

st.markdown("### 📡 Sessions Partagées")
st.caption("Consultez les sessions de quizz partagées, les questions et les analytics.")

all_sessions = list_sessions()
if not all_sessions:
    st.info("Aucune session partagée n'a été créée. Générez un quizz puis partagez-le.")
else:
    # Filtre par nom ou code
    filter_text = st.text_input("🔍 Filtrer par nom ou code", key="shared_session_filter", placeholder="Rechercher...")
    if filter_text.strip():
        _ft = filter_text.strip().lower()
        all_sessions = [s for s in all_sessions if _ft in s.title.lower() or _ft in s.session_code.lower()]

    if not all_sessions:
        st.warning("Aucune session ne correspond au filtre.")
    else:
        # Sélecteur de session
        session_labels = {
            f"{'🟢' if s.is_active else '🔴'} {s.title} ({s.session_code}) — {s.created_at[:10]}": s.session_code
            for s in all_sessions
        }
        selected_label = st.selectbox("Sélectionnez une session", list(session_labels.keys()))
        selected_code = session_labels.get(selected_label, "")

        if selected_code:
            sess = get_session(selected_code)
            if sess:
                # Infos session
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("Code", sess.session_code)
                with col_info2:
                    st.metric("Statut", "Active" if sess.is_active else "Fermée")
                with col_info3:
                    st.metric("Créée le", sess.created_at[:10])

                # Actions
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if sess.is_active:
                        if st.button("🔒 Fermer cette session", width='stretch'):
                            deactivate_session(selected_code)
                            st.success("Session fermée.")
                            st.rerun()
                with col_act2:
                    if st.button("🔃 Rafraîchir", width='stretch', key="refresh_sessions"):
                        st.rerun()

                st.divider()

                # Onglets Questions / Analytics
                tab_questions, tab_analytics = st.tabs(["📋 Questions", "📊 Quizz Session Analytics"])

                with tab_questions:
                    quiz_data = json.loads(sess.quiz_json)
                    questions = quiz_data.get("questions", [])
                    st.markdown(f"**{len(questions)} question(s)** dans cette session")

                    for i, q in enumerate(questions):
                        diff_label = q.get("difficulty_level", "moyen")
                        diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                        related_notions = q.get("related_notions", [])

                        with st.expander(f"{diff_emoji} **Q{i+1}.** {q.get('question', '')}", expanded=(i < 3)):
                            render_difficulty_badge(diff_label)

                            if related_notions:
                                tags_html = " ".join(
                                    f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                                    f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                                    f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                                    for n in related_notions
                                )
                                st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

                            st.markdown(q.get("question", ""))

                            choices = q.get("choices", {})
                            correct_answers = q.get("correct_answers", [])
                            for label, text in choices.items():
                                is_correct = label in correct_answers
                                icon = "✅" if is_correct else "⬜"
                                st.markdown(f"**{icon} {label}.** {text}")

                            explanation = q.get("explanation", "")
                            if explanation:
                                st.info(f"💡 {explanation}")

                with tab_analytics:
                    render_analytics_dashboard(selected_code)
