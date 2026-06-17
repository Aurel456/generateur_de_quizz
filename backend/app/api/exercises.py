"""Génération et amélioration d'exercices (réutilise generation.exercise_generator).

⚠️ Pour le type « calcul », la génération exécute du code Python de vérification dans un
sous-processus sandboxé (cf. generation/calc_agent.py) — comme l'app Streamlit. À
n'utiliser qu'en environnement de confiance.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import dict_to_exercise, dict_to_notion, exercise_to_dict
from backend.app.doc_store import doc_store
from backend.app.schemas import (
    ExerciseDTO,
    ExercisesResponse,
    GenerateExercisesRequest,
    ImproveExerciseRequest,
)
from core.llm_service import VISION_MODEL_NAME
from generation.exercise_generator import generate_exercises
from generation.question_editor import improve_exercise_with_llm

router = APIRouter(prefix="/exercises", tags=["exercises"])
log = logging.getLogger(__name__)
_VISION_MODEL = VISION_MODEL_NAME or None


@router.post("/generate", response_model=ExercisesResponse)
def generate(payload: GenerateExercisesRequest) -> ExercisesResponse:
    entry = doc_store.get(payload.doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")

    counts = {k: v for k, v in payload.difficulty_counts.items() if v > 0}
    if not counts:
        raise HTTPException(status_code=400, detail="Indiquez au moins un exercice à générer.")

    notions = [dict_to_notion(n.model_dump()) for n in payload.notions if n.enabled]

    try:
        exercises = generate_exercises(
            entry.chunks,
            difficulty_counts=counts,
            exercise_type=payload.exercise_type,
            persona=payload.persona,
            user_instructions=payload.user_instructions,
            notions=notions or None,
            vision_mode=entry.vision,
            batch_mode=payload.batch_mode,
            model=_VISION_MODEL if entry.vision else None,
        )
    except Exception:
        log.exception("Échec génération des exercices")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération des exercices.")

    return ExercisesResponse(exercises=[ExerciseDTO(**exercise_to_dict(e)) for e in exercises])


@router.post("/improve", response_model=ExerciseDTO)
def improve(payload: ImproveExerciseRequest) -> ExerciseDTO:
    exercise = dict_to_exercise(payload.exercise.model_dump())
    try:
        improved = improve_exercise_with_llm(exercise, payload.instruction)
    except Exception:
        log.exception("Échec amélioration de l'exercice")
        raise HTTPException(status_code=502, detail="Erreur lors de l'amélioration de l'exercice.")
    return ExerciseDTO(**exercise_to_dict(improved))
