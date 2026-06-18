"""Prompts par défaut, éditables par niveau (quiz & exercices).

Le frontend récupère ces valeurs pour pré-remplir des champs éditables ; il renvoie
ensuite les prompts modifiés dans `difficulty_prompts` (quiz) / `custom_exercise_prompts`
(exercices). Les *règles fixes* (format JSON, nombre de choix…) restent dans la logique
métier et sont seulement décrites ici en lecture seule.
"""
from fastapi import APIRouter

from backend.app.schemas import PromptDefaultsResponse
from generation.exercise_generator import (
    DEFAULT_EXERCISE_PROMPTS,
    DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE,
    DEFAULT_EXERCISE_PROMPTS_TROU,
)
from generation.quiz_generator import DIFFICULTY_PROMPTS

router = APIRouter(prefix="/prompts", tags=["prompts"])

_FIXED_RULES = {
    "quiz": (
        "Règles non modifiables (appliquées automatiquement) : format de sortie JSON strict, "
        "nombre de choix et de bonnes réponses selon la configuration, libellés A/B/C…, "
        "citations issues du document, cohérence des notions. Les champs ci-dessous ne pilotent "
        "que le STYLE et le niveau de difficulté."
    ),
    "exercises": (
        "Règles non modifiables : structure JSON par type d'exercice (énoncé, étapes, "
        "blancs ou sous-questions selon le type), code de vérification pour le calcul, "
        "citations. Les champs ci-dessous ne pilotent que le niveau de difficulté."
    ),
}


@router.get("/defaults", response_model=PromptDefaultsResponse)
def defaults() -> PromptDefaultsResponse:
    return PromptDefaultsResponse(
        quiz=dict(DIFFICULTY_PROMPTS),
        exercises={
            "calcul": dict(DEFAULT_EXERCISE_PROMPTS),
            "trou": dict(DEFAULT_EXERCISE_PROMPTS_TROU),
            "cas_pratique": dict(DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE),
        },
        fixed_rules=_FIXED_RULES,
    )
