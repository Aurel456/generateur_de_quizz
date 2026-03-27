"""
exercise_verifier.py — Vérification LLM des exercices (trou et cas_pratique).

Le LLM tente de résoudre l'exercice en relisant le document source.
Si il échoue, l'exercice est reformulé (jusqu'à 3 tentatives) ou supprimé.
Pour les calculs dans les cas pratiques, le code Python de vérification est exécuté.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from core.llm_service import call_llm_json, count_tokens, MODEL_NAME
from generation.exercise_generator import Exercise, _verify_exercise_direct
from processing.document_processor import TextChunk

logger = logging.getLogger(__name__)


@dataclass
class ExerciseVerificationAttempt:
    """Un essai de vérification d'un exercice."""
    attempt_num: int
    llm_result: dict  # Réponse structurée du LLM
    is_correct: bool
    reasoning: str
    was_reformulated: bool = False


@dataclass
class ExerciseVerificationResult:
    """Résultat de la vérification d'un exercice."""
    exercise_index: int
    original_exercise: Exercise
    final_exercise: Optional[Exercise]  # None si supprimé
    attempts: List[ExerciseVerificationAttempt] = field(default_factory=list)
    status: str = "pending"  # "verified", "reformulated", "deleted"


def _build_source_text(chunks: List[TextChunk], max_tokens: int = 12000) -> str:
    """Construit le texte source à partir des chunks."""
    text_parts = []
    total_tokens = 0
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.text)
        if total_tokens + chunk_tokens > max_tokens:
            break
        text_parts.append(chunk.text)
        total_tokens += chunk_tokens
    return "\n\n".join(text_parts)


# ── Vérification TROU ────────────────────────────────────────────────────────

def _verify_trou_with_llm(
    exercise: Exercise,
    source_text: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Tuple[dict, str]:
    """
    Le LLM tente de remplir les blancs de l'exercice en relisant le document source.

    Returns:
        ({"filled_blanks": [{"position": 1, "answer": "..."}]}, reasoning)
    """
    blanks_description = "\n".join(
        f"  Blanc {b['position']}: {b.get('context', '(pas de contexte)')}"
        for b in exercise.blanks
    )

    system_prompt = """Tu es un étudiant qui passe un examen.
Tu dois remplir les blancs de l'exercice en te basant UNIQUEMENT sur le document fourni.

RÈGLES :
1. Lis attentivement le document
2. Pour chaque blanc, donne la réponse exacte (terme, valeur ou notion)
3. Justifie chaque réponse
4. Réponds UNIQUEMENT avec un JSON valide

FORMAT DE RÉPONSE (JSON strict) :
{
    "filled_blanks": [
        {"position": 1, "answer": "ta réponse"},
        {"position": 2, "answer": "ta réponse"}
    ],
    "reasoning": "Explication de ton raisonnement basé sur le document..."
}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text}
---

EXERCICE À TROU :
{exercise.statement}

BLANCS À REMPLIR :
{blanks_description}

Remplis chaque blanc avec la bonne réponse."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.2, enable_thinking=enable_thinking)
    reasoning = result.get("reasoning", "")
    return result, reasoning


def _check_trou_answers(exercise: Exercise, llm_result: dict) -> bool:
    """Compare les réponses du LLM avec les blancs attendus."""
    filled = llm_result.get("filled_blanks", [])
    if not filled:
        return False

    llm_answers = {b["position"]: b["answer"].strip().lower() for b in filled if "position" in b and "answer" in b}
    expected = {b["position"]: b["answer"].strip().lower() for b in exercise.blanks}

    correct_count = 0
    for pos, expected_answer in expected.items():
        llm_answer = llm_answers.get(pos, "")
        # Comparaison flexible : contient ou égalité
        if llm_answer == expected_answer or expected_answer in llm_answer or llm_answer in expected_answer:
            correct_count += 1

    # Au moins 70% des blancs doivent être corrects
    return correct_count >= len(expected) * 0.7


# ── Vérification CAS PRATIQUE ────────────────────────────────────────────────

def _verify_cas_pratique_with_llm(
    exercise: Exercise,
    source_text: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Tuple[dict, str]:
    """
    Le LLM tente de répondre aux sous-questions du cas pratique.

    Returns:
        ({"answers": [{"question_index": 0, "answer": "..."}]}, reasoning)
    """
    sub_q_text = "\n".join(
        f"  Q{i+1}. {sq['question']}"
        for i, sq in enumerate(exercise.sub_questions)
    )

    system_prompt = """Tu es un étudiant qui passe un examen de cas pratique.
Tu dois répondre aux sous-questions en te basant UNIQUEMENT sur le document fourni et les données de l'énoncé.

RÈGLES :
1. Lis attentivement le document et l'énoncé
2. Réponds à chaque sous-question avec précision
3. Si un calcul est demandé, montre les étapes
4. Réponds UNIQUEMENT avec un JSON valide

FORMAT DE RÉPONSE (JSON strict) :
{
    "answers": [
        {"question_index": 0, "answer": "Ta réponse détaillée..."},
        {"question_index": 1, "answer": "Ta réponse détaillée..."}
    ],
    "reasoning": "Explication globale de ton raisonnement..."
}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text}
---

CAS PRATIQUE :
{exercise.statement}

SOUS-QUESTIONS :
{sub_q_text}

Réponds à chaque sous-question."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.2, enable_thinking=enable_thinking)
    reasoning = result.get("reasoning", "")
    return result, reasoning


def _check_cas_pratique_answers(exercise: Exercise, llm_result: dict) -> bool:
    """
    Vérifie les réponses du LLM pour un cas pratique.
    Pour les sous-questions numériques : exécution du code de vérification.
    Pour les autres : le LLM a pu répondre = l'exercice est cohérent.
    """
    answers = llm_result.get("answers", [])
    if not answers:
        return False

    # Si un code de vérification existe, l'exécuter
    if exercise.verification_code:
        test_exercise = Exercise(
            statement=exercise.statement,
            expected_answer="",
            verification_code=exercise.verification_code,
            exercise_type="calcul",
        )
        test_exercise = _verify_exercise_direct(test_exercise)
        if not test_exercise.verified:
            return False

    # Le LLM a fourni des réponses pour au moins la moitié des sous-questions
    return len(answers) >= len(exercise.sub_questions) * 0.5


# ── Reformulation ────────────────────────────────────────────────────────────

def _reformulate_exercise(
    exercise: Exercise,
    source_text: str,
    llm_result: dict,
    reasoning: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Exercise:
    """Reformule un exercice pour le rendre plus clair et vérifiable."""

    if exercise.exercise_type == "trou":
        return _reformulate_trou(exercise, source_text, llm_result, reasoning, model, enable_thinking=enable_thinking)
    elif exercise.exercise_type == "cas_pratique":
        return _reformulate_cas_pratique(exercise, source_text, llm_result, reasoning, model, enable_thinking=enable_thinking)
    return exercise


def _reformulate_trou(
    exercise: Exercise,
    source_text: str,
    llm_result: dict,
    reasoning: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Exercise:
    """Reformule un exercice à trou."""
    blanks_text = "\n".join(
        f"  Blanc {b['position']}: attendu=\"{b['answer']}\", contexte=\"{b.get('context', '')}\""
        for b in exercise.blanks
    )

    system_prompt = """Tu es un expert en création d'exercices à trou.
Un exercice a été mal résolu par un étudiant IA. Reformule-le pour qu'il soit plus clair.

RÈGLES :
1. Garde le même sujet/thème
2. Fournis suffisamment de contexte autour des blancs
3. Les réponses attendues doivent être clairement déductibles du cours
4. Au minimum 3 phrases, dont au moins une de contexte sans blanc

FORMAT DE RÉPONSE (JSON strict) :
{
    "statement": "Texte reformulé avec _____...",
    "blanks": [{"position": 1, "answer": "réponse", "context": "phrase avec [BLANC]"}],
    "correction": "Correction reformulée..."
}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text[:6000]}
---

EXERCICE ORIGINAL :
{exercise.statement}

BLANCS ATTENDUS :
{blanks_text}

RÉPONSES DE L'ÉTUDIANT IA : {llm_result.get('filled_blanks', [])}
RAISONNEMENT : {reasoning}

Reformule l'exercice pour éliminer l'ambiguïté."""

    try:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.4, enable_thinking=enable_thinking)
        return Exercise(
            statement=result.get("statement", exercise.statement),
            expected_answer="",
            blanks=result.get("blanks", exercise.blanks),
            correction=result.get("correction", exercise.correction),
            source_pages=exercise.source_pages,
            source_document=exercise.source_document,
            citation=exercise.citation,
            difficulty_level=exercise.difficulty_level,
            related_notions=exercise.related_notions,
            exercise_type="trou",
            verified=False,
            verification_output="",
        )
    except Exception as e:
        logger.warning("Reformulation trou échouée: %s", e)
        return exercise


def _reformulate_cas_pratique(
    exercise: Exercise,
    source_text: str,
    llm_result: dict,
    reasoning: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> Exercise:
    """Reformule un exercice de cas pratique."""
    sub_q_text = "\n".join(
        f"  Q{i+1}. {sq['question']} → Réponse attendue: {sq['answer'][:100]}"
        for i, sq in enumerate(exercise.sub_questions)
    )

    system_prompt = """Tu es un expert en création de cas pratiques.
Un exercice a été mal résolu par un étudiant IA. Reformule-le pour qu'il soit plus clair.

RÈGLES :
1. Garde le même sujet/thème et le même niveau de difficulté
2. L'énoncé doit fournir toutes les données nécessaires
3. Les sous-questions doivent être progressives et claires
4. Si des calculs sont demandés, fournis un verification_code Python

FORMAT DE RÉPONSE (JSON strict) :
{
    "statement": "Énoncé reformulé...",
    "sub_questions": [{"question": "Q1?", "answer": "Réponse..."}],
    "correction": "Correction reformulée...",
    "verification_code": "# Code Python optionnel..."
}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text[:6000]}
---

CAS PRATIQUE ORIGINAL :
{exercise.statement}

SOUS-QUESTIONS :
{sub_q_text}

RÉPONSES DE L'ÉTUDIANT IA : {llm_result.get('answers', [])}
RAISONNEMENT : {reasoning}

Reformule le cas pratique pour éliminer l'ambiguïté."""

    try:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.4, enable_thinking=enable_thinking)
        return Exercise(
            statement=result.get("statement", exercise.statement),
            expected_answer="",
            sub_questions=result.get("sub_questions", exercise.sub_questions),
            correction=result.get("correction", exercise.correction),
            verification_code=result.get("verification_code", exercise.verification_code),
            source_pages=exercise.source_pages,
            source_document=exercise.source_document,
            citation=exercise.citation,
            difficulty_level=exercise.difficulty_level,
            related_notions=exercise.related_notions,
            exercise_type="cas_pratique",
            verified=False,
            verification_output="",
        )
    except Exception as e:
        logger.warning("Reformulation cas pratique échouée: %s", e)
        return exercise


# ── Fonction principale ──────────────────────────────────────────────────────

def verify_exercises(
    exercises: List[Exercise],
    chunks: List[TextChunk],
    model: Optional[str] = None,
    max_reformulations: int = 3,
    progress_callback: Optional[Callable] = None,
    enable_thinking: bool = True,
) -> Tuple[List[Exercise], List[ExerciseVerificationResult]]:
    """
    Vérifie les exercices trou et cas_pratique via le LLM.
    Les exercices de type "calcul" sont ignorés (déjà vérifiés par exécution Python).

    Args:
        exercises: Liste d'exercices à vérifier.
        chunks: Chunks de texte source.
        model: Modèle LLM à utiliser.
        max_reformulations: Nombre max de reformulations.
        progress_callback: Callback(completed, total).

    Returns:
        (exercices_vérifiés, résultats_de_vérification)
    """
    source_text = _build_source_text(chunks)
    results: List[ExerciseVerificationResult] = []
    verified_exercises: List[Exercise] = []

    total = len(exercises)

    for idx, exercise in enumerate(exercises):
        if progress_callback:
            progress_callback(idx, total)

        # Les exercices calcul sont déjà vérifiés par exécution Python
        if exercise.exercise_type == "calcul":
            verified_exercises.append(exercise)
            results.append(ExerciseVerificationResult(
                exercise_index=idx,
                original_exercise=exercise,
                final_exercise=exercise,
                status="verified" if exercise.verified else "deleted",
            ))
            continue

        vr = ExerciseVerificationResult(
            exercise_index=idx,
            original_exercise=exercise,
            final_exercise=None,
        )

        current_exercise = exercise
        verified = False

        for attempt_num in range(max_reformulations + 1):
            try:
                # Vérification selon le type
                if current_exercise.exercise_type == "trou":
                    llm_result, reasoning = _verify_trou_with_llm(
                        current_exercise, source_text, model=model,
                        enable_thinking=enable_thinking,
                    )
                    is_correct = _check_trou_answers(current_exercise, llm_result)
                elif current_exercise.exercise_type == "cas_pratique":
                    llm_result, reasoning = _verify_cas_pratique_with_llm(
                        current_exercise, source_text, model=model,
                        enable_thinking=enable_thinking,
                    )
                    is_correct = _check_cas_pratique_answers(current_exercise, llm_result)
                else:
                    break

                attempt = ExerciseVerificationAttempt(
                    attempt_num=attempt_num,
                    llm_result=llm_result,
                    is_correct=is_correct,
                    reasoning=reasoning,
                    was_reformulated=(attempt_num > 0),
                )
                vr.attempts.append(attempt)

                logger.info(
                    "Ex%d (%s) tentative %d: %s",
                    idx + 1, current_exercise.exercise_type, attempt_num,
                    "OK" if is_correct else "FAIL",
                )

                if is_correct:
                    verified = True
                    current_exercise.verified = True
                    current_exercise.verification_output = (
                        f"Vérifié par LLM (tentative {attempt_num + 1}). "
                        + reasoning[:200]
                    )
                    vr.final_exercise = current_exercise
                    vr.status = "verified" if attempt_num == 0 else "reformulated"
                    verified_exercises.append(current_exercise)
                    break

                if attempt_num < max_reformulations:
                    logger.info("Ex%d: reformulation (tentative %d)...", idx + 1, attempt_num + 1)
                    current_exercise = _reformulate_exercise(
                        current_exercise, source_text,
                        llm_result, reasoning, model=model,
                        enable_thinking=enable_thinking,
                    )

            except Exception as e:
                logger.warning("Ex%d tentative %d erreur: %s", idx + 1, attempt_num, e)
                attempt = ExerciseVerificationAttempt(
                    attempt_num=attempt_num,
                    llm_result={},
                    is_correct=False,
                    reasoning=f"Erreur: {e}",
                )
                vr.attempts.append(attempt)

        if not verified:
            vr.status = "deleted"
            vr.final_exercise = None
            logger.warning(
                "Ex%d (%s): supprimé après %d reformulations",
                idx + 1, current_exercise.exercise_type, max_reformulations,
            )

        results.append(vr)

    if progress_callback:
        progress_callback(total, total)

    return verified_exercises, results
