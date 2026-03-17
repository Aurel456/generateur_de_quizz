"""
analytics.py — Dashboard analytics pour les sessions de quizz partagées.

Graphiques interactifs (plotly) et métriques pour analyser les résultats.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from session_store import get_session_analytics, list_sessions, deactivate_session


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
