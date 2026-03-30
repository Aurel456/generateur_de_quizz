"""
analytics.py — Dashboard analytics pour les sessions de quizz partagées.

Graphiques interactifs (plotly), métriques et recommandations IA pour analyser les résultats.
"""

import json
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from sessions.session_store import get_session_analytics, list_sessions, deactivate_session


def render_analytics_dashboard(session_code: str):
    """Affiche le dashboard analytics complet pour une session."""
    analytics = get_session_analytics(session_code)
    if not analytics:
        st.warning("Session introuvable.")
        return

    session_info = analytics["session"]
    global_stats = analytics["global_stats"]

    # Header
    st.markdown(f"### 📊 Analytics — {session_info['title']}")
    st.caption(f"Code : **{session_info['code']}** — Créée le {session_info['created_at'][:10]}")

    if not session_info["is_active"]:
        st.warning("Cette session est fermée.")

    # Métriques globales
    render_global_metrics(analytics)

    if global_stats["num_participants"] == 0:
        st.info("Aucun participant n'a encore soumis ses réponses.")
        return

    st.divider()

    # Graphiques côte à côte
    col_left, col_right = st.columns(2)
    with col_left:
        render_per_question_chart(analytics)
    with col_right:
        render_per_notion_chart(analytics)

    st.divider()

    # Tableau des participants
    render_participant_table(analytics)

    st.divider()

    # Recommandations IA
    render_ai_recommendations(analytics)


def render_global_metrics(analytics: dict):
    """Affiche les métriques globales."""
    stats = analytics["global_stats"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Participants", stats["num_participants"])
    with col2:
        st.metric("Score moyen", f"{stats['avg_score']:.1f}%")
    with col3:
        st.metric("Score médian", f"{stats['median_score']:.1f}%")
    with col4:
        st.metric("Questions", stats["total_questions"])


def render_per_question_chart(analytics: dict):
    """Bar chart : taux de réussite par question."""
    per_question = analytics["per_question"]
    if not per_question:
        st.info("Pas de données par question.")
        return

    st.markdown("#### Taux de réussite par question")

    # Préparer les données
    labels = []
    rates = []
    colors = []
    for q_idx in sorted(per_question.keys(), key=lambda x: int(x)):
        q = per_question[q_idx]
        labels.append(f"Q{int(q_idx)+1}")
        rate = q["success_rate"] * 100
        rates.append(rate)
        if rate >= 70:
            colors.append("#00c853")
        elif rate >= 40:
            colors.append("#ffab00")
        else:
            colors.append("#ff1744")

    fig = go.Figure(data=[
        go.Bar(
            x=labels,
            y=rates,
            marker_color=colors,
            text=[f"{r:.0f}%" for r in rates],
            textposition="auto",
            hovertext=[
                f"{per_question[str(i)]['question_text'][:60]}...<br>"
                f"Réussite : {per_question[str(i)]['success_rate']*100:.0f}%<br>"
                f"Réponses correctes : {per_question[str(i)]['correct_count']}/{per_question[str(i)]['total_attempts']}"
                for i in range(len(labels))
            ],
            hoverinfo="text",
        )
    ])

    fig.update_layout(
        yaxis_title="Taux de réussite (%)",
        yaxis_range=[0, 105],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e8e8f0"),
        height=350,
        margin=dict(t=10, b=40, l=40, r=10),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.1)")

    st.plotly_chart(fig, width='stretch')


def render_per_notion_chart(analytics: dict):
    """Radar chart : taux de réussite par notion."""
    per_notion = analytics["per_notion"]
    if not per_notion:
        st.info("Pas de données par notion (les questions n'ont pas de notions associées).")
        return

    st.markdown("#### Taux de réussite par notion")

    notion_names = list(per_notion.keys())
    rates = [per_notion[n]["avg_success_rate"] * 100 for n in notion_names]

    if len(notion_names) >= 3:
        # Radar chart
        fig = go.Figure(data=go.Scatterpolar(
            r=rates + [rates[0]],  # Fermer le polygone
            theta=notion_names + [notion_names[0]],
            fill="toself",
            fillcolor="rgba(108,99,255,0.2)",
            line=dict(color="#6c63ff", width=2),
            marker=dict(size=6, color="#6c63ff"),
            text=[f"{r:.0f}%" for r in rates] + [f"{rates[0]:.0f}%"],
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    tickfont=dict(color="#a0a0b8"),
                    gridcolor="rgba(255,255,255,0.1)",
                ),
                angularaxis=dict(
                    tickfont=dict(color="#e8e8f0", size=10),
                    gridcolor="rgba(255,255,255,0.1)",
                ),
                bgcolor="rgba(0,0,0,0)",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e8e8f0"),
            height=350,
            margin=dict(t=30, b=30, l=60, r=60),
            showlegend=False,
        )

        st.plotly_chart(fig, width='stretch')
    else:
        # Fallback : bar chart horizontal si moins de 3 notions
        fig = go.Figure(data=[
            go.Bar(
                y=notion_names,
                x=rates,
                orientation="h",
                marker_color="#6c63ff",
                text=[f"{r:.0f}%" for r in rates],
                textposition="auto",
            )
        ])

        fig.update_layout(
            xaxis_title="Taux de réussite (%)",
            xaxis_range=[0, 105],
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e8e8f0"),
            height=350,
            margin=dict(t=10, b=40, l=10, r=10),
        )
        st.plotly_chart(fig, width='stretch')


def render_participant_table(analytics: dict):
    """Tableau classement des participants."""
    participants = analytics["participants"]
    if not participants:
        return

    st.markdown("#### Classement des participants")

    # Préparer les données pour le dataframe
    table_data = []
    for i, p in enumerate(participants, 1):
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"#{i}"

        table_data.append({
            "Rang": medal,
            "Participant": p["name"],
            "Score": f"{p['score']}/{p['total']}",
            "Pourcentage": f"{p['percentage']}%",
            "Soumis le": p["submitted_at"][:16].replace("T", " "),
        })

    st.dataframe(
        table_data,
        width='stretch',
        hide_index=True,
    )


def render_session_selector() -> str:
    """
    Affiche un sélecteur de session et retourne le code sélectionné.

    Returns:
        Code de la session sélectionnée, ou "" si aucune.
    """
    sessions = list_sessions()
    if not sessions:
        st.info("Aucune session partagée n'a été créée.")
        return ""

    options = {
        f"{s.title} ({s.session_code}) — {'Active' if s.is_active else 'Fermée'}": s.session_code
        for s in sessions
    }

    selected = st.selectbox("Sélectionnez une session", options=list(options.keys()))
    return options.get(selected, "")


def generate_ai_recommendations(analytics: dict, model: str = None) -> dict:
    """
    Analyse les résultats via LLM et génère des recommandations pédagogiques.

    Returns:
        Dict structuré avec weak_notions, problematic_questions, student_patterns, global_recommendations.
    """
    from core.llm_service import call_llm_json

    # Préparer les données condensées pour le LLM
    per_question = analytics.get("per_question", {})
    per_notion = analytics.get("per_notion", {})
    participants = analytics.get("participants", [])
    global_stats = analytics.get("global_stats", {})

    questions_summary = []
    for q_idx, q in per_question.items():
        questions_summary.append({
            "index": int(q_idx),
            "text": q.get("question_text", ""),
            "success_rate": round(q.get("success_rate", 0) * 100, 1),
            "difficulty": q.get("difficulty_level", ""),
            "notions": q.get("related_notions", []),
        })

    notions_summary = {
        name: round(data.get("avg_success_rate", 0) * 100, 1)
        for name, data in per_notion.items()
    }

    participants_summary = [
        {"name": p["name"], "percentage": p["percentage"]}
        for p in participants[:20]
    ]

    data_json = json.dumps({
        "global": {
            "num_participants": global_stats.get("num_participants", 0),
            "avg_score": round(global_stats.get("avg_score", 0), 1),
            "median_score": round(global_stats.get("median_score", 0), 1),
        },
        "questions": questions_summary,
        "notions": notions_summary,
        "participants": participants_summary,
    }, ensure_ascii=False, indent=2)

    system_prompt = """Tu es un expert en pédagogie et en analyse de résultats d'évaluation.
Analyse les résultats de cette session de quiz et fournis des recommandations concrètes.

FORMAT DE RÉPONSE (JSON strict) :
{
    "weak_notions": [
        {"notion": "Nom de la notion", "success_rate": 45.0, "recommendation": "Recommandation concrète..."}
    ],
    "problematic_questions": [
        {"question_index": 0, "text_preview": "Début de la question...", "issue": "Problème identifié", "suggestion": "Suggestion d'amélioration"}
    ],
    "student_patterns": [
        {"pattern": "Description du pattern observé", "recommendation": "Recommandation pédagogique"}
    ],
    "global_recommendations": [
        "Recommandation globale 1",
        "Recommandation globale 2"
    ]
}"""

    user_prompt = f"""Analyse les résultats suivants et fournis des recommandations pédagogiques :

{data_json}

Identifie :
1. Les notions faibles (taux < 60%) avec des recommandations de remédiation
2. Les questions problématiques (taux < 40% ou > 95%) avec des suggestions
3. Les patterns chez les étudiants (écarts de niveau, lacunes communes)
4. Des recommandations globales pour le formateur"""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.3, use_cache=True)
    return result


def render_ai_recommendations(analytics: dict):
    """Bouton + affichage des recommandations IA."""
    st.markdown("#### Recommandations IA")

    if st.button("Analyser les résultats avec l'IA", key="ai_recommendations_btn"):
        with st.spinner("Analyse en cours..."):
            try:
                reco = generate_ai_recommendations(analytics)
                st.session_state["_ai_recommendations"] = reco
            except Exception as e:
                st.error(f"Erreur lors de l'analyse IA : {e}")
                return

    reco = st.session_state.get("_ai_recommendations")
    if not reco:
        st.caption("Cliquez sur le bouton pour obtenir des recommandations personnalisées.")
        return

    # Notions faibles
    weak = reco.get("weak_notions", [])
    if weak:
        with st.expander(f"Notions faibles ({len(weak)})", expanded=True):
            for item in weak:
                rate = item.get("success_rate", 0)
                color = "#ff1744" if rate < 40 else "#ffab00"
                st.markdown(
                    f"<span style='color:{color};font-weight:600'>{item.get('notion', '?')} "
                    f"({rate:.0f}%)</span> — {item.get('recommendation', '')}",
                    unsafe_allow_html=True,
                )

    # Questions problématiques
    problematic = reco.get("problematic_questions", [])
    if problematic:
        with st.expander(f"Questions problématiques ({len(problematic)})"):
            for item in problematic:
                st.markdown(
                    f"**Q{item.get('question_index', 0) + 1}** : {item.get('issue', '')}\n\n"
                    f"*Suggestion :* {item.get('suggestion', '')}"
                )

    # Patterns étudiants
    patterns = reco.get("student_patterns", [])
    if patterns:
        with st.expander(f"Patterns observés ({len(patterns)})"):
            for item in patterns:
                st.markdown(f"**{item.get('pattern', '')}**\n\n{item.get('recommendation', '')}")

    # Recommandations globales
    global_reco = reco.get("global_recommendations", [])
    if global_reco:
        with st.expander("Recommandations globales", expanded=True):
            for r in global_reco:
                st.markdown(f"- {r}")
