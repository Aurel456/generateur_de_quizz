"""
quiz_verifier.py — Vérification LLM des questions QCM.

Le LLM relit le document source et tente de répondre aux questions comme un étudiant.
Si il échoue, la question est reformulée (jusqu'à 3 tentatives) ou supprimée.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.llm_service import call_llm_json, count_tokens, MODEL_NAME
from generation.quiz_generator import Quiz, QuizQuestion, QUIZ_FIXED_RULES_DISPLAY
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
    enable_thinking: bool = True,
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

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.2, enable_thinking=enable_thinking)

    selected = result.get("selected_answers", [])
    reasoning = result.get("reasoning", "")

    return selected, reasoning


def _reformulate_question(
    question: QuizQuestion,
    source_text: str,
    llm_answers: List[str],
    llm_reasoning: str,
    model: Optional[str] = None,
    enable_thinking: bool = True,
) -> QuizQuestion:
    """
    Reformule globalement la question : énoncé, choix, explication, citation
    et notions liées, en passant au LLM le chunk source, l'ensemble des règles
    de génération, et la question complète actuelle.

    Cœur de la refonte v5 : la question doit rester répondable PAR UN ÉTUDIANT
    QUI N'A PAS ACCÈS AU DOCUMENT — donc on bannit toute référence au texte
    source dans l'énoncé et les choix. La reformulation utilise le chunk
    UNIQUEMENT pour s'assurer que la bonne réponse correspond effectivement à
    une connaissance enseignée, jamais comme prétexte d'une question
    auto-référentielle.
    """
    choices_text = "\n".join(
        f"  {label}. {text}" for label, text in question.choices.items()
    )
    notions_str = ", ".join(question.related_notions) if question.related_notions else "(non renseigné)"

    system_prompt = f"""Tu es un expert en création de QCM pédagogiques.

CONTEXTE — POURQUOI ON REFORMULE :
Une IA-étudiante (qui simule un humain ayant suivi la formation) a tenté de répondre à la
question en s'appuyant sur le document source ET sur ses connaissances générales du domaine.
Elle a échoué. Cela signifie que la question :
  • soit contient une AMBIGUÏTÉ qui rend plusieurs choix défendables,
  • soit FAIT RÉFÉRENCE AU TEXTE (« selon le document », « dans le passage »...) alors que
    l'étudiant final n'a PAS le document sous les yeux au moment du quiz,
  • soit attend un détail qui n'est pas réellement enseigné par le contenu cité,
  • soit a des distracteurs (mauvaises réponses) trop ambigus.

Ta mission : reformuler GLOBALEMENT cette question pour la rendre AUTONOME et NON-AMBIGUË.

RÈGLE FONDAMENTALE (cœur de la reformulation) :
La question doit pouvoir être répondue par un étudiant qui a SUIVI LA FORMATION mais qui
N'A PAS ACCÈS AU DOCUMENT au moment où il répond. L'énoncé contient donc tout le contexte
nécessaire et n'utilise jamais de tournures qui supposent que l'étudiant lit le passage.

INTERDICTIONS ABSOLUES dans l'énoncé et les choix :
  • « selon le texte », « d'après le document », « dans le passage », « le texte mentionne »,
    « l'auteur affirme », « comme indiqué dans », « tel qu'écrit », « le document précise »
  • toute formulation qui supposerait que l'étudiant a le passage sous les yeux

RÈGLES DE REFORMULATION :
1. Conserve le SUJET et la NOTION testée (`related_notions`) — c'est la même connaissance.
2. Les LABELS des bonnes réponses sont préservés : si A était correct, A reste correct
   (mais le contenu textuel du choix A peut changer pour être plus clair).
3. Reformule l'énoncé pour qu'il soit auto-suffisant : tout le contexte nécessaire est
   intégré DANS l'énoncé (un nom propre, une date, une situation concrète).
4. Les distracteurs (mauvaises réponses) doivent être plausibles mais clairement fausses
   pour qui maîtrise la notion — pas de pièges syntaxiques, pas d'ambiguïtés.
5. Mets à jour l'EXPLICATION pour qu'elle reflète la nouvelle formulation et reste
   pédagogiquement utile (pourquoi la bonne réponse est correcte, pourquoi les autres
   sont fausses).
6. Mets à jour la CITATION du passage source si la reformulation s'éloigne de la citation
   d'origine. Garde une citation EXACTE du chunk fourni si possible.
7. Conserve la difficulté ({question.difficulty_level or 'non renseignée'}).
8. FORMULATION OBLIGATOIRE : Le champ 'question' DOIT être une véritable question
   interrogative (point d'interrogation final, mot interrogatif ou verbe conjugué).
   INTERDIT : titre nominal (« Les délais de prescription »), fragment, consigne impérative.
9. CLARTÉ : pas de phrase tronquée, énoncé exploitable seul.

RAPPEL DES RÈGLES DE QUALITÉ DU QCM (issues du générateur) :
{QUIZ_FIXED_RULES_DISPLAY}

FORMAT DE RÉPONSE (JSON strict — uniquement ces champs) :
{{
    "question": "Question reformulée se terminant par un point d'interrogation ?",
    "choices": {{"A": "Choix A reformulé", "B": "Choix B reformulé"}},
    "correct_answers": ["A"],
    "explanation": "Explication détaillée mise à jour : pourquoi la bonne réponse est correcte ET pourquoi chaque mauvaise réponse est fausse.",
    "citation": "Citation exacte du passage source qui justifie la bonne réponse (ou citation existante si toujours pertinente)."
}}"""

    user_prompt = f"""CHUNK SOURCE (référentiel — l'étudiant ne l'a PAS au moment du quiz) :
---
{source_text}
---

QUESTION ACTUELLE À REFORMULER (tous les champs) :
- Énoncé : {question.question}
- Choix :
{choices_text}
- Bonnes réponses attendues : {question.correct_answers}
- Explication actuelle : {question.explanation or '(vide)'}
- Citation actuelle : {question.citation or '(vide)'}
- Difficulté : {question.difficulty_level or '(non précisée)'}
- Notions liées : {notions_str}

DIAGNOSTIC DE L'ÉCHEC :
L'IA-étudiante a répondu {llm_answers} au lieu de {question.correct_answers}.
Son raisonnement : {llm_reasoning or '(non fourni)'}

TÂCHE :
Reformule globalement la question (énoncé + choix + explication + citation) pour que
l'étudiant final, SANS le document mais avec la formation, puisse identifier sans
ambiguïté la bonne réponse. Conserve les labels des bonnes réponses, la difficulté
et la notion testée."""

    result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.4, enable_thinking=enable_thinking)

    new_question = QuizQuestion(
        question=result.get("question", question.question),
        choices=result.get("choices", question.choices),
        correct_answers=result.get("correct_answers", question.correct_answers),
        explanation=result.get("explanation", question.explanation),
        source_pages=question.source_pages,
        difficulty_level=question.difficulty_level,
        source_document=question.source_document,
        citation=result.get("citation", question.citation),
        related_notions=question.related_notions,
    )

    # Validation : les bonnes réponses doivent exister dans les choix
    if not all(ans in new_question.choices for ans in new_question.correct_answers):
        logger.warning("Reformulation invalide : bonnes réponses absentes des choix, on garde l'original")
        return question

    # Validation : l'énoncé reformulé doit être une vraie question
    if not _looks_like_question(new_question.question):
        logger.warning(
            "Reformulation invalide : énoncé non interrogatif (%r), on garde l'original",
            new_question.question[:80],
        )
        return question

    # Validation : pas de troncature / énoncé trop court
    if len(new_question.question.strip()) < 15:
        logger.warning("Reformulation invalide : énoncé trop court, on garde l'original")
        return question

    return new_question


def _looks_like_question(text: str) -> bool:
    """Vérifie qu'une chaîne ressemble à une vraie question interrogative."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped.endswith("?"):
        return False
    # Doit contenir un verbe ou un mot interrogatif — heuristique simple
    # (contient un espace + pas uniquement quelques mots nominaux)
    words = stripped.rstrip("?").strip().split()
    if len(words) < 3:
        return False
    lowered = stripped.lower()
    interrogatives = (
        "que ", "qu'", "quel", "quelle", "quels", "quelles",
        "comment", "pourquoi", "combien", "lequel", "laquelle",
        "lesquels", "lesquelles", "où", "quand", "dans quel",
        "à quel", "de quel", "par quel", "est-", "est-ce", "peut-",
        "doit-", "faut-il", "y a-t-il", "a-t-",
    )
    if any(tok in lowered for tok in interrogatives):
        return True
    # Fallback : présence d'un verbe conjugué courant
    common_verbs = (" est ", " sont ", " a ", " ont ", " peut ", " doit ", " faut ")
    return any(v in f" {lowered} " for v in common_verbs)


def verify_quiz(
    quiz: Quiz,
    chunks: List[TextChunk],
    model: Optional[str] = None,
    max_reformulations: int = 3,
    progress_callback: Optional[Callable] = None,
    batch_mode: bool = False,
    enable_thinking: bool = True,
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
                        current_question, source_text, model=model,
                        enable_thinking=enable_thinking,
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
                        enable_thinking=enable_thinking,
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
