"""
pages/quiz_session.py — Page participant pour passer un quizz partagé.

Accessible via URL : http://host:port/quiz_session?code=ABC123
"""

import json
import streamlit as st

from sessions.session_store import get_session, submit_result, get_next_subset

st.set_page_config(
    page_title="Quizz en ligne",
    page_icon="📝",
    layout="centered",
)

# CSS cohérent avec l'app principale
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .quiz-header { text-align: center; padding: 1.5rem 0; }
    .quiz-header h1 {
        background: linear-gradient(135deg, #6c63ff 0%, #3f51b5 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 2rem; font-weight: 700;
    }
    .difficulty-badge {
        display: inline-block; padding: 0.2rem 0.6rem;
        border-radius: 12px; font-size: 0.75rem; font-weight: 600;
    }
    .difficulty-badge.facile { background: rgba(0,200,83,0.15); color: #00c853; }
    .difficulty-badge.moyen { background: rgba(255,171,0,0.15); color: #ffab00; }
    .difficulty-badge.difficile { background: rgba(255,23,68,0.15); color: #ff1744; }
    .notion-tag {
        display: inline-block; background: rgba(108,99,255,0.15); color: #6c63ff;
        padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem;
        margin-right: 0.3rem; margin-bottom: 0.3rem;
    }
    .score-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px; padding: 2rem; text-align: center;
        border: 1px solid #2a2a40;
    }
    .score-value { font-size: 3rem; font-weight: 700; color: #6c63ff; }
</style>
""", unsafe_allow_html=True)

# ─── Récupérer le code de session ───────────────────────────────────────────

session_code = st.query_params.get("code", "")

if not session_code:
    st.markdown("""
    <div class="quiz-header">
        <h1>📝 Quizz en ligne</h1>
    </div>
    """, unsafe_allow_html=True)
    session_code = st.text_input("Entrez le code de la session", placeholder="Ex: K8S42X")
    if session_code:
        st.query_params["code"] = session_code
        st.rerun()
    else:
        st.info("Entrez le code de session fourni par votre formateur pour accéder au quizz.")
        st.stop()

# ─── Charger la session ──────────────────────────────────────────────────────

session = get_session(session_code)
if not session:
    st.error(f"Session introuvable : **{session_code}**")
    st.stop()

if not session.is_active:
    st.warning("Cette session est fermée. Aucune soumission n'est possible.")
    st.stop()

quiz_data = json.loads(session.quiz_json)
is_pool_session = bool(session.pool_json)

# ─── Session state ───────────────────────────────────────────────────────────

if "participant_name" not in st.session_state:
    st.session_state.participant_name = ""
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "result" not in st.session_state:
    st.session_state.result = None
if "pool_subset" not in st.session_state:
    st.session_state.pool_subset = None  # Questions subset for pool sessions

# ─── Identification du participant ────────────────────────────────────────────

if not st.session_state.submitted:
    participant_name = st.text_input(
        "Votre nom / identifiant",
        value=st.session_state.participant_name,
        placeholder="Entrez votre nom pour commencer",
    )
    st.session_state.participant_name = participant_name

    if not participant_name:
        st.markdown(f"""
        <div class="quiz-header">
            <h1>📝 {session.title}</h1>
        </div>
        """, unsafe_allow_html=True)
        st.info("Entrez votre nom pour accéder au quizz.")
        st.stop()

    # Charger le sous-ensemble pour les sessions pool
    if is_pool_session and st.session_state.pool_subset is None:
        with st.spinner("Préparation de votre quizz personnalisé…"):
            st.session_state.pool_subset = get_next_subset(session_code, participant_name)

    questions = st.session_state.pool_subset if is_pool_session else quiz_data.get("questions", [])

    pool_size = len(json.loads(session.pool_json)) if is_pool_session else None
    pool_label = f" (pool de {pool_size})" if pool_size else ""

    st.markdown(f"""
    <div class="quiz-header">
        <h1>📝 {session.title}</h1>
        <p style="color: #a0a0b8;">{len(questions)} questions{pool_label}</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ─── Affichage des questions ──────────────────────────────────────────────

    answers = {}
    for i, q in enumerate(questions):
        diff_label = q.get("difficulty_level", "moyen")
        diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
        related_notions = q.get("related_notions", [])

        st.markdown(f"### {diff_emoji} Question {i+1}")
        st.markdown(f'<span class="difficulty-badge {diff_label}">{diff_label.capitalize()}</span>', unsafe_allow_html=True)

        if related_notions:
            tags = " ".join(f'<span class="notion-tag">{n}</span>' for n in related_notions)
            st.markdown(f"📚 {tags}", unsafe_allow_html=True)

        st.markdown(q.get("question", ""))

        choices = q.get("choices", {})
        correct_answers = q.get("correct_answers", [])
        num_correct = len(correct_answers)

        if num_correct == 1:
            # Radio pour réponse unique
            options = [f"{label}. {text}" for label, text in choices.items()]
            labels_list = list(choices.keys())
            selected = st.radio(
                "Votre réponse",
                options=options,
                key=f"q_{i}",
                index=None,
                label_visibility="collapsed",
            )
            if selected:
                idx = options.index(selected)
                answers[str(i)] = [labels_list[idx]]
            else:
                answers[str(i)] = []
        else:
            # Checkboxes pour réponses multiples
            st.caption(f"Sélectionnez {num_correct} réponse(s)")
            selected_labels = []
            for label, text in choices.items():
                if st.checkbox(f"{label}. {text}", key=f"q_{i}_{label}"):
                    selected_labels.append(label)
            answers[str(i)] = selected_labels

        st.divider()

    # ─── Bouton de soumission ─────────────────────────────────────────────────

    # Vérifier que toutes les questions ont une réponse
    unanswered = [i + 1 for i in range(len(questions)) if len(answers.get(str(i), [])) == 0]
    all_answered = len(unanswered) == 0

    if not all_answered:
        if len(unanswered) <= 5:
            missing_str = ", ".join(str(n) for n in unanswered)
            st.warning(f"⚠️ Question(s) sans réponse : **{missing_str}**")
        else:
            first_five = ", ".join(str(n) for n in unanswered[:5])
            st.warning(f"⚠️ {len(unanswered)} question(s) sans réponse : **{first_five}**, …")

    if st.button("📤 Soumettre mes réponses", type="primary", width='stretch', disabled=not all_answered):
        with st.spinner("Envoi des résultats..."):
            result = submit_result(
                session_code, participant_name, answers,
                questions_override=questions if is_pool_session else None,
            )
            if result:
                st.session_state.submitted = True
                st.session_state.result = result
                st.rerun()
            else:
                st.error("Erreur lors de la soumission. La session est peut-être fermée.")

    st.caption("💡 Si les résultats ne s'affichent pas après soumission, cliquez sur **Rafraîchir** ci-dessous.")
    if st.button("🔃 Rafraîchir", key="refresh_pre_submit"):
        st.rerun()

else:
    # ─── Affichage des résultats ──────────────────────────────────────────────

    # Pour les résultats, on reconstruit la liste de questions affichées
    if is_pool_session and st.session_state.pool_subset is not None:
        questions = st.session_state.pool_subset
    else:
        questions = quiz_data.get("questions", [])

    result = st.session_state.result
    if result:
        pct = (result.score / result.total * 100) if result.total > 0 else 0

        # Message contextuel
        if pct >= 90:
            emoji, message = "🏆", "Excellent ! Maîtrise parfaite !"
        elif pct >= 70:
            emoji, message = "👏", "Très bien ! Bonne compréhension !"
        elif pct >= 50:
            emoji, message = "👍", "Pas mal ! Continuez à réviser."
        else:
            emoji, message = "📚", "Il faut revoir le sujet. Courage !"

        st.markdown(f"""
        <div class="score-card">
            <div class="score-value">{result.score} / {result.total}</div>
            <p style="font-size: 1.5rem; margin-top: 0.5rem;">{emoji} {message}</p>
            <p style="color: #a0a0b8; margin-top: 0.5rem;">{pct:.0f}% de réussite</p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Détails par question
        per_question = json.loads(result.per_question_json)
        st.markdown("### Détails par question")

        for i, q in enumerate(questions):
            is_correct = per_question.get(str(i), False)
            icon = "✅" if is_correct else "❌"
            diff_label = q.get("difficulty_level", "moyen")

            with st.expander(f"{icon} Question {i+1} — {q.get('question', '')[:80]}..."):
                st.markdown(q.get("question", ""))

                choices = q.get("choices", {})
                correct_answers = q.get("correct_answers", [])
                user_answers_data = json.loads(result.answers_json)
                user_selected = user_answers_data.get(str(i), [])

                for label, text in choices.items():
                    is_correct_choice = label in correct_answers
                    is_selected = label in user_selected

                    if is_correct_choice and is_selected:
                        st.markdown(f"✅ **{label}.** {text}")
                    elif is_correct_choice:
                        st.markdown(f"🟢 **{label}.** {text} *(bonne réponse)*")
                    elif is_selected:
                        st.markdown(f"❌ **{label}.** {text} *(votre réponse)*")
                    else:
                        st.markdown(f"⬜ {label}. {text}")

                explanation = q.get("explanation", "")
                if explanation:
                    st.info(f"💡 {explanation}")

        # Boutons de refaire et rafraîchir
        st.divider()

        # Bouton de relance pour sessions pool si sous le seuil
        if is_pool_session:
            threshold = session.pass_threshold or 0.7
            threshold_pct = threshold * 100
            if pct < threshold_pct:
                st.warning(
                    f"Score insuffisant ({pct:.0f}% < {threshold_pct:.0f}% requis). "
                    "Vous pouvez réessayer avec de nouvelles questions."
                )
                if st.button("🔁 Réessayer avec de nouvelles questions", type="primary", width='stretch'):
                    st.session_state.submitted = False
                    st.session_state.result = None
                    st.session_state.pool_subset = None  # Force refresh of subset
                    st.rerun()
            else:
                st.success(f"✅ Seuil atteint ({pct:.0f}% ≥ {threshold_pct:.0f}%). Félicitations !")

        col_redo, col_refresh = st.columns(2)
        with col_redo:
            redo_label = "🔄 Refaire le quizz" if not is_pool_session else "🔄 Recommencer depuis le début"
            if st.button(redo_label, width='stretch'):
                st.session_state.submitted = False
                st.session_state.result = None
                st.session_state.pool_subset = None
                st.rerun()
        with col_refresh:
            if st.button("🔃 Rafraîchir la page", width='stretch'):
                st.rerun()
