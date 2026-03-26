"""
quiz_verifier.py — Vérification LLM des questions QCM.

Le LLM relit le document source et tente de répondre aux questions comme un étudiant.
Si il échoue, la question est reformulée (jusqu'à 3 tentatives) ou supprimée.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.llm_service import call_llm_json, count_tokens, MODEL_NAME
from generation.quiz_generator import Quiz, QuizQuestion
from processing.document_processor import TextChunk

logger = logging.getLogger(__name__)


@dataclass
class VerificationAttempt:
    """Un essai de vérification d'une question."""
    attempt_num: int
    llm_answers: List[str]
    expected_answers: List[str]
    is_correct: bool
    reasoning: str
    was_reformulated: bool = False


@dataclass
class QuestionVerificationResult:
    """Résultat de la vérification d'une question."""
    question_index: int
    original_question: QuizQuestion
    final_question: Optional[QuizQuestion]  # None si supprimée
    attempts: List[VerificationAttempt] = field(default_factory=list)
    status: str = "pending"  # "verified", "reformulated", "deleted"


def _build_source_text(chunks: List[TextChunk], max_tokens: int = 12000) -> str:
    """Construit le texte source à partir des chunks, en respectant une limite de tokens."""
    text_parts = []
    total_tokens = 0
    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.text)
        if total_tokens + chunk_tokens > max_tokens:
            break
        text_parts.append(chunk.text)
        total_tokens += chunk_tokens
    return "\n\n".join(text_parts)


def _verify_question_with_llm(
    question: QuizQuestion,
    source_text: str,
    model: Optional[str] = None,
) -> Tuple[List[str], str]:
    """
    Le LLM tente de répondre à la question en lisant le document source,
    comme un étudiant qui passe un examen.

    Returns:
        (réponses_choisies, raisonnement)
    """
    num_correct = len(question.correct_answers)
    choices_text = "\n".join(
        f"  {label}. {text}" for label, text in question.choices.items()
    )

    system_prompt = f"""Tu es un étudiant qui passe un examen QCM.
Tu dois répondre à la question en te basant UNIQUEMENT sur le document fourni.

RÈGLES :
1. Lis attentivement le document
2. Tu dois sélectionner exactement {num_correct} réponse(s)
3. Justifie ton choix en citant le passage pertinent du document
4. Réponds UNIQUEMENT avec un JSON valide

FORMAT DE RÉPONSE (JSON strict) :
{{
    "selected_answers": ["A"],
    "reasoning": "Explication de ton raisonnement basé sur le document..."
}}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text}
---

QUESTION :
{question.question}

CHOIX :
{choices_text}

Sélectionne exactement {num_correct} réponse(s) et explique ton raisonnement."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.2)

    selected = result.get("selected_answers", [])
    reasoning = result.get("reasoning", "")

    return selected, reasoning


def _reformulate_question(
    question: QuizQuestion,
    source_text: str,
    llm_answers: List[str],
    llm_reasoning: str,
    model: Optional[str] = None,
) -> QuizQuestion:
    """
    Le LLM reformule la question pour que les bonnes réponses soient
    clairement identifiables à partir du document source.
    """
    choices_text = "\n".join(
        f"  {label}. {text}" for label, text in question.choices.items()
    )

    system_prompt = """Tu es un expert en création de QCM. Une question a été mal comprise par un étudiant IA.
Tu dois reformuler la question ET les choix de réponse pour que la bonne réponse soit
clairement identifiable à partir du document source, tout en restant pédagogique.

RÈGLES :
1. La question reformulée doit couvrir le même sujet/notion
2. Les bonnes réponses doivent rester les mêmes labels (ex: si A était correct, A reste correct)
3. Reformule l'énoncé pour qu'il soit plus clair et sans ambiguïté
4. Ajuste les choix de réponse si nécessaire (les mauvaises réponses doivent être clairement fausses)
5. Mets à jour l'explication
6. La question doit rester auto-suffisante (pas de référence au document)

FORMAT DE RÉPONSE (JSON strict) :
{
    "question": "Question reformulée...",
    "choices": {"A": "Choix A reformulé", "B": "Choix B reformulé"},
    "correct_answers": ["A"],
    "explanation": "Explication mise à jour..."
}"""

    user_prompt = f"""DOCUMENT SOURCE :
---
{source_text}
---

QUESTION ORIGINALE :
{question.question}

CHOIX ORIGINAUX :
{choices_text}

BONNES RÉPONSES ATTENDUES : {question.correct_answers}

RÉPONSE DE L'ÉTUDIANT IA : {llm_answers}
RAISONNEMENT DE L'ÉTUDIANT : {llm_reasoning}

L'étudiant a répondu {llm_answers} au lieu de {question.correct_answers}.
Reformule la question et les choix pour éliminer l'ambiguïté."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.4)

    new_question = QuizQuestion(
        question=result.get("question", question.question),
        choices=result.get("choices", question.choices),
        correct_answers=result.get("correct_answers", question.correct_answers),
        explanation=result.get("explanation", question.explanation),
        source_pages=question.source_pages,
        difficulty_level=question.difficulty_level,
        source_document=question.source_document,
        citation=question.citation,
        related_notions=question.related_notions,
    )

    # Validation : les bonnes réponses doivent exister dans les choix
    if not all(ans in new_question.choices for ans in new_question.correct_answers):
        logger.warning("Reformulation invalide : bonnes réponses absentes des choix, on garde l'original")
        return question

    return new_question


def verify_quiz(
    quiz: Quiz,
    chunks: List[TextChunk],
    model: Optional[str] = None,
    max_reformulations: int = 3,
    progress_callback: Optional[Callable] = None,
    batch_mode: bool = False,
) -> Tuple[Quiz, List[QuestionVerificationResult]]:
    """
    Vérifie toutes les questions d'un quiz via le LLM.

    Le LLM lit le document et tente de répondre. Si il échoue :
    - Reformulation (jusqu'à max_reformulations fois)
    - Suppression si toujours incorrect

    Args:
        batch_mode: Si True, la première passe de vérification est batchée.

    Returns:
        (quiz_nettoyé, résultats_de_vérification)
    """
    source_text = _build_source_text(chunks)
    results: List[QuestionVerificationResult] = []
    verified_questions: List[QuizQuestion] = []

    total = len(quiz.questions)

    # ─── BATCH : première passe de vérification ───────────────────────────
    first_pass_results = {}  # idx → (llm_answers, reasoning)
    if batch_mode and total > 1:
        from generation.batch_service import BatchRequest, run_batch_json

        batch_requests = []
        for idx, question in enumerate(quiz.questions):
            num_correct = len(question.correct_answers)
            choices_text = "\n".join(
                f"  {label}. {text}" for label, text in question.choices.items()
            )
            sys_prompt = f"""Tu es un étudiant qui passe un examen QCM.
Tu dois répondre à la question en te basant UNIQUEMENT sur le document fourni.

RÈGLES :
1. Lis attentivement le document
2. Tu dois sélectionner exactement {num_correct} réponse(s)
3. Justifie ton choix en citant le passage pertinent du document
4. Réponds UNIQUEMENT avec un JSON valide

FORMAT DE RÉPONSE (JSON strict) :
{{
    "selected_answers": ["A"],
    "reasoning": "Explication de ton raisonnement basé sur le document..."
}}"""
            usr_prompt = f"""DOCUMENT SOURCE :
---
{source_text}
---

QUESTION :
{question.question}

CHOIX :
{choices_text}

Sélectionne exactement {num_correct} réponse(s) et explique ton raisonnement."""

            batch_requests.append(BatchRequest(
                custom_id=f"verify_{idx}",
                system_prompt=sys_prompt,
                user_prompt=usr_prompt,
                model=model or MODEL_NAME,
                temperature=0.2,
            ))

        if progress_callback:
            progress_callback(0, total)

        batch_results = run_batch_json(
            batch_requests,
            progress_callback=lambda done, t: progress_callback(done, t) if progress_callback else None,
        )

        for custom_id, parsed in batch_results.items():
            idx = int(custom_id.split("_")[1])
            first_pass_results[idx] = (
                parsed.get("selected_answers", []),
                parsed.get("reasoning", ""),
            )

    # ─── Traitement par question ──────────────────────────────────────────
    for idx, question in enumerate(quiz.questions):
        if progress_callback and not batch_mode:
            progress_callback(idx, total)

        vr = QuestionVerificationResult(
            question_index=idx,
            original_question=question,
            final_question=None,
        )

        current_question = question
        verified = False

        for attempt_num in range(max_reformulations + 1):
            try:
                # Utiliser le résultat batch pour la première passe si disponible
                if attempt_num == 0 and idx in first_pass_results:
                    llm_answers, reasoning = first_pass_results[idx]
                else:
                    llm_answers, reasoning = _verify_question_with_llm(
                        current_question, source_text, model=model
                    )

                is_correct = sorted(llm_answers) == sorted(current_question.correct_answers)

                attempt = VerificationAttempt(
                    attempt_num=attempt_num,
                    llm_answers=llm_answers,
                    expected_answers=list(current_question.correct_answers),
                    is_correct=is_correct,
                    reasoning=reasoning,
                    was_reformulated=(attempt_num > 0),
                )
                vr.attempts.append(attempt)

                logger.info(
                    "Q%d tentative %d: LLM=%s vs attendu=%s → %s",
                    idx + 1, attempt_num, llm_answers,
                    current_question.correct_answers,
                    "OK" if is_correct else "FAIL",
                )

                if is_correct:
                    verified = True
                    vr.final_question = current_question
                    vr.status = "verified" if attempt_num == 0 else "reformulated"
                    verified_questions.append(current_question)
                    break

                if attempt_num < max_reformulations:
                    logger.info("Q%d: reformulation (tentative %d)...", idx + 1, attempt_num + 1)
                    current_question = _reformulate_question(
                        current_question, source_text,
                        llm_answers, reasoning, model=model,
                    )

            except Exception as e:
                logger.warning("Q%d tentative %d erreur: %s", idx + 1, attempt_num, e)
                attempt = VerificationAttempt(
                    attempt_num=attempt_num,
                    llm_answers=[],
                    expected_answers=list(current_question.correct_answers),
                    is_correct=False,
                    reasoning=f"Erreur: {e}",
                )
                vr.attempts.append(attempt)

        if not verified:
            vr.status = "deleted"
            vr.final_question = None
            logger.warning(
                "Q%d: supprimée après %d reformulations", idx + 1, max_reformulations
            )

        results.append(vr)

    if progress_callback:
        progress_callback(total, total)

    # Construire le quiz nettoyé
    verified_quiz = Quiz(
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=verified_questions,
        metadata={
            **quiz.metadata,
            "verification": {
                "original_count": total,
                "verified_count": sum(1 for r in results if r.status == "verified"),
                "reformulated_count": sum(1 for r in results if r.status == "reformulated"),
                "deleted_count": sum(1 for r in results if r.status == "deleted"),
            },
        },
    )

    return verified_quiz, results
