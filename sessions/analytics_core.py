"""
analytics_core.py — Logique d'analytics SANS dépendance UI (ni Streamlit ni Plotly).

Extrait de `analytics.py` pour être réutilisable par le backend FastAPI (migration DSFR)
comme par l'app Streamlit. Le calcul des métriques brutes vit dans
`sessions.session_store.get_session_analytics` ; ce module ajoute l'analyse LLM.
"""

import json
from typing import Optional


def generate_ai_recommendations(analytics: dict, model: Optional[str] = None) -> dict:
    """
    Analyse les résultats via LLM et génère des recommandations pédagogiques.

    Returns:
        Dict structuré avec weak_notions, problematic_questions, student_patterns,
        global_recommendations.
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
