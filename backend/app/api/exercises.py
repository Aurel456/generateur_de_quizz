"""Génération et amélioration d'exercices (réutilise generation.exercise_generator).

⚠️ Pour le type « calcul », la génération exécute du code Python de vérification dans un
sous-processus sandboxé (cf. generation/calc_agent.py) — comme l'app Streamlit. À
n'utiliser qu'en environnement de confiance.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import dict_to_exercise, dict_to_notion, exercise_to_dict
from backend.app.doc_store import DocEntry, doc_store
from backend.app.jobs import Job, job_store
from backend.app.schemas import (
    ExerciseDTO,
    ExercisesResponse,
    GenerateExercisesRequest,
    ImproveExerciseRequest,
    JobCreatedResponse,
)
from core.llm_service import VISION_MODEL_NAME
from generation.exercise_generator import generate_exercises
from generation.question_editor import improve_exercise_with_llm

router = APIRouter(prefix="/exercises", tags=["exercises"])
log = logging.getLogger(__name__)
_VISION_MODEL = VISION_MODEL_NAME or None


def _resolve_doc(doc_id: str) -> DocEntry:
    entry = doc_store.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")
    return entry


def _resolve_counts(difficulty_counts: dict[str, int]) -> dict[str, int]:
    counts = {k: v for k, v in difficulty_counts.items() if v > 0}
    if not counts:
        raise HTTPException(status_code=400, detail="Indiquez au moins un exercice à générer.")
    return counts


def _run_generation(
    entry: DocEntry,
    payload: GenerateExercisesRequest,
    counts: dict[str, int],
    *,
    progress_callback=None,
    on_item=None,
) -> ExercisesResponse:
    notions = [dict_to_notion(n.model_dump()) for n in payload.notions if n.enabled]
    stream = on_item is not None and not payload.batch_mode

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
        progress_callback=progress_callback,
        stream=stream,
        on_item=on_item if stream else None,
    )
    return ExercisesResponse(exercises=[ExerciseDTO(**exercise_to_dict(e)) for e in exercises])


@router.post("/generate", response_model=ExercisesResponse)
def generate(payload: GenerateExercisesRequest) -> ExercisesResponse:
    entry = _resolve_doc(payload.doc_id)
    counts = _resolve_counts(payload.difficulty_counts)
    try:
        return _run_generation(entry, payload, counts)
    except Exception:
        log.exception("Échec génération des exercices")
        raise HTTPException(status_code=502, detail="Erreur lors de la génération des exercices.")


@router.post("/generate-async", response_model=JobCreatedResponse)
def generate_async(payload: GenerateExercisesRequest) -> JobCreatedResponse:
    entry = _resolve_doc(payload.doc_id)
    counts = _resolve_counts(payload.difficulty_counts)

    def task(job: Job) -> dict:
        response = _run_generation(
            entry,
            payload,
            counts,
            progress_callback=job.progress,
            on_item=lambda e: job.add_item(exercise_to_dict(e)),
        )
        return response.model_dump()

    return JobCreatedResponse(job_id=job_store.submit("exercises", task))


@router.post("/improve", response_model=ExerciseDTO)
def improve(payload: ImproveExerciseRequest) -> ExerciseDTO:
    exercise = dict_to_exercise(payload.exercise.model_dump())
    try:
        improved = improve_exercise_with_llm(exercise, payload.instruction)
    except Exception:
        log.exception("Échec amélioration de l'exercice")
        raise HTTPException(status_code=502, detail="Erreur lors de l'amélioration de l'exercice.")
    return ExerciseDTO(**exercise_to_dict(improved))
