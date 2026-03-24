"""
quiz_generator.py — Génération de quizz QCM à partir de chunks de texte.
"""

import string
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.llm_service import call_llm_json, call_llm_vision_json, count_tokens, MODEL_CONTEXT_WINDOW
from processing.document_processor import TextChunk
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from generation.notion_detector import Notion


@dataclass
class QuizQuestion:
    """Une question de quizz QCM."""
    question: str
    choices: Dict[str, str]  # {"A": "...", "B": "...", ...}
    correct_answers: List[str]  # ["A", "C"]
    explanation: str = ""
    source_pages: List[int] = field(default_factory=list)
    difficulty_level: str = ""
    source_document: str = ""
    citation: str = ""
    related_notions: List[str] = field(default_factory=list)  # Titres des notions couvertes


@dataclass
class Quiz:
    """Un quizz complet."""
    title: str
    difficulty: str
    questions: List[QuizQuestion] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# Persona par défaut — modifiable par l'utilisateur dans l'interface
QUIZ_DEFAULT_PERSONA = (
    "Tu es un expert en pédagogie et en création de quizz éducatifs. "
    "Tu maîtrises le domaine couvert par les documents fournis et tu sais formuler "
    "des questions précises, claires et pédagogiquement pertinentes."
)

# Règles fixes affichées en lecture seule dans l'interface (pour information)
QUIZ_FIXED_RULES_DISPLAY = """RÈGLES FIXES (non modifiables — garantissent la qualité et le parsing) :
• Nombre de choix et de bonnes réponses : configuré dans les paramètres
• Les questions doivent être AUTONOMES (répondables sans le document source)
• Chaque explication doit inclure une CITATION exacte du texte source
• INTERDIT : "selon le texte", "d'après le document", "dans le passage"...
• Formulations précises uniquement — pas de "Quel est le principal...", "Parmi les suivants..."
• Ne jamais mentionner le nombre de bonnes réponses dans l'énoncé
• Format de réponse : JSON strict avec champs question/choices/correct_answers/explanation/citation/source_page/related_notions"""

# Mapping difficulté → instructions pour le LLM
DIFFICULTY_PROMPTS = {
    "facile": (
        "Génère des questions FACILES portant sur des faits fondamentaux du domaine. "
        "Les questions doivent porter sur des définitions, des dates, ou des faits simples "
        "qu'un étudiant ayant suivi la formation devrait connaître. "
        "Les mauvaises réponses doivent être clairement fausses."
    ),
    "moyen": (
        "Génère des questions de difficulté MOYENNE qui testent la compréhension des concepts. "
        "Les questions peuvent nécessiter de relier plusieurs informations, "
        "comprendre des concepts, ou interpréter des données. "
        "Les mauvaises réponses doivent être plausibles mais incorrectes."
    ),
    "difficile": (
        "Génère des questions DIFFICILES qui testent l'analyse et la synthèse. "
        "Les questions doivent nécessiter une réflexion approfondie, "
        "la capacité à faire des inférences, ou à appliquer des concepts à des situations nouvelles. "
        "Les mauvaises réponses doivent être plausibles mais incorrectes. "
    ),
}


def _build_quiz_prompt(
    text: str,
    difficulty: str,
    num_questions: int,
    num_choices: int,
    num_correct: int,
    choice_labels: List[str],
    difficulty_prompts: Optional[Dict[str, str]] = None,
    notions_text: str = "",
    source_document: str = "",
    existing_questions: Optional[List[str]] = None,
    variable_correct: bool = False,
    persona: str = "",
    notion_mixing: bool = True,
) -> tuple:
    """Construit le prompt système et utilisateur pour la génération de quizz."""
    
    labels_str = ", ".join(choice_labels[:num_choices])
    prompts = difficulty_prompts or DIFFICULTY_PROMPTS
    diff_instruction = prompts.get(difficulty, DIFFICULTY_PROMPTS.get(difficulty, ""))
    
    notions_block = ""
    if notions_text:
        notions_block = f"""\n\n{notions_text}\nLes questions doivent prioritairement couvrir ces notions fondamentales."""
    
    active_persona = persona.strip() if persona.strip() else QUIZ_DEFAULT_PERSONA
    system_prompt = f"""{active_persona}
Tu dois générer exactement {num_questions} questions QCM (Questions à Choix Multiples).

CONTEXTE IMPORTANT :
Les étudiants suivent une formation (souvent en présentiel ou avec des supports) mais ils ne possèdent
PAS le document source au moment du quizz. Les questions doivent donc être AUTONOMES et répondables
uniquement grâce aux connaissances acquises pendant la formation, SANS avoir le document sous les yeux.

RÈGLES STRICTES :
1. Chaque question doit avoir exactement {num_choices} choix de réponse ({labels_str})
2. {"Varie le nombre de bonnes réponses entre 1 et " + str(num_choices - 1) + " selon la question. Certaines questions ont 1 seule bonne réponse, d'autres en ont 2 ou plus. Ne mentionne JAMAIS le nombre de bonnes réponses dans l'énoncé de la question." if variable_correct else f"Chaque question doit avoir exactement {num_correct} bonne(s) réponse(s)"}
3. {diff_instruction}
4. Chaque question doit inclure une explication de la réponse avec une CITATION exacte du texte source.
   L'explication doit être factuelle et ne jamais affirmer quelque chose qui n'est pas directement
   supporté par le texte source.
5. Les questions doivent être variées et couvrir différentes parties du texte
6. Les choix de réponse doivent être du même type et de longueur similaire
7. Pour chaque question, précise la PAGE EXACTE de la source
8. Le niveau de difficulté est : {difficulty}
9. INTERDIT : N'utilise JAMAIS de formulations comme "selon le texte", "d'après le document",
   "dans le passage", "le texte mentionne", "l'auteur affirme", etc.
   Chaque question doit être auto-suffisante et fournir tout le contexte nécessaire dans son énoncé.
10. FORMULATION PRÉCISE : Chaque question doit avoir un énoncé non-ambigu et spécifique.
    Évite les formulations vagues comme "Quel est le principal...", "Parmi les suivants, lequel...",
    "Quelle est la meilleure...". Préfère des questions précises avec un contexte clair.
    Le nombre de bonnes réponses ne doit jamais figurer dans l'énoncé (ne pas écrire "Quelles sont
    les 2 raisons..." si num_correct=2 — le nombre de réponses attendues est déjà indiqué à l'étudiant).
{"11. Pour chaque question, indique dans 'related_notions' le(s) titre(s) exact(s) des notions fondamentales couvertes par cette question. Utilise les titres tels qu'ils apparaissent dans la liste des notions." if notions_text else ""}
{"12. NOTIONS PAR QUESTION : Chaque question doit couvrir UNE SEULE notion à la fois. Le champ 'related_notions' doit contenir exactement 1 élément. Ne mélange pas plusieurs notions dans une même question." if (notions_text and not notion_mixing) else ""}
{notions_block}{f"""

QUESTIONS DÉJÀ GÉNÉRÉES — À NE PAS DUPLIQUER :
Les questions suivantes ont déjà été générées pour ce quizz. Tes nouvelles questions doivent porter sur des sujets différents et ne pas être similaires à celles-ci :
{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(existing_questions))}
""" if existing_questions else ""}
FORMAT DE RÉPONSE (JSON strict) :
{{
    "questions": [
        {{
            "question": "La question posée ?",
            "choices": {{{", ".join(f'"{l}": "Choix {l}"' for l in choice_labels[:num_choices])}}},
            "correct_answers": {list(choice_labels[:num_correct])},
            "explanation": "Explication détaillée de la bonne réponse...",
            "citation": "Citation exacte du passage du texte qui justifie la réponse...",
            "source_page": 1,
            "difficulty_level": "{difficulty}",
            "related_notions": ["Titre notion 1", "Titre notion 2"]
        }}
    ]
}}"""

    doc_context = f" (document : {source_document})" if source_document else ""
    user_prompt = f"""Voici le texte source{doc_context} pour générer les questions :

---
{text}
---

Génère exactement {num_questions} questions QCM de niveau {difficulty}."""
    
    return system_prompt, user_prompt


def _parse_quiz_questions(
    result: dict,
    chunk: TextChunk,
    difficulty: str,
) -> List[QuizQuestion]:
    """Parse le JSON retourné par le LLM en liste de QuizQuestion."""
    questions = []
    for q_data in result.get("questions", []):
        try:
            source_page = q_data.get("source_page")
            if source_page:
                source_pages = [source_page] if isinstance(source_page, int) else chunk.source_pages
            else:
                source_pages = chunk.source_pages

            choices = q_data["choices"]
            correct_answers = q_data["correct_answers"]

            question = QuizQuestion(
                question=q_data["question"],
                choices=choices,
                correct_answers=correct_answers,
                explanation=q_data.get("explanation", ""),
                source_pages=source_pages,
                difficulty_level=q_data.get("difficulty_level", difficulty),
                source_document=chunk.source_document,
                citation=q_data.get("citation", ""),
                related_notions=q_data.get("related_notions", []),
            )
            if all(ans in question.choices for ans in question.correct_answers):
                questions.append(question)
        except (KeyError, TypeError):
            continue
    return questions


def generate_quiz_from_chunk(
    chunk: TextChunk,
    difficulty: str = "moyen",
    num_questions: int = 5,
    num_choices: int = 4,
    num_correct: int = 1,
    difficulty_prompts: Optional[Dict[str, str]] = None,
    model: Optional[str] = None,
    notions_text: str = "",
    vision_mode: bool = False,
    existing_questions: Optional[List[str]] = None,
    variable_correct: bool = False,
    persona: str = "",
    notion_mixing: bool = True,
) -> List[QuizQuestion]:
    """
    Génère des questions de quizz à partir d'un seul chunk de texte.
    """
    choice_labels = list(string.ascii_uppercase[:num_choices])

    system_prompt, user_prompt = _build_quiz_prompt(
        chunk.text, difficulty, num_questions, num_choices, num_correct, choice_labels,
        difficulty_prompts, notions_text=notions_text, source_document=chunk.source_document,
        existing_questions=existing_questions, variable_correct=variable_correct,
        persona=persona, notion_mixing=notion_mixing,
    )

    # Appel au LLM (vision ou texte)
    if vision_mode and chunk.page_images:
        result = call_llm_vision_json(system_prompt, user_prompt, chunk.page_images, model=model, temperature=0.6)
    else:
        result = call_llm_json(system_prompt, user_prompt, model=model, temperature=0.6)

    return _parse_quiz_questions(result, chunk, difficulty)


def _distribute_questions(chunks: List[TextChunk], count: int) -> List[int]:
    """Répartit un nombre de questions proportionnellement entre les chunks."""
    total_tokens = sum(c.token_count for c in chunks)
    questions_per_chunk = []
    remaining = count

    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            n = max(remaining, 0)
        else:
            ratio = chunk.token_count / total_tokens if total_tokens > 0 else 1 / len(chunks)
            n = round(count * ratio)
            n = min(n, remaining)
        questions_per_chunk.append(n)
        remaining -= n
        if remaining <= 0:
            questions_per_chunk.extend([0] * (len(chunks) - len(questions_per_chunk)))
            break

    return questions_per_chunk


def generate_quiz(
    chunks: List[TextChunk],
    difficulty: Optional[str] = None,
    num_questions: Optional[int] = None,
    difficulty_counts: Optional[Dict[str, int]] = None,
    num_choices: int = 4,
    num_correct: int = 1,
    difficulty_prompts: Optional[Dict[str, str]] = None,
    model: Optional[str] = None,
    progress_callback=None,
    notions: Optional[list] = None,
    batch_mode: bool = False,
    vision_mode: bool = False,
    variable_correct: bool = False,
    persona: str = "",
    notion_mixing: bool = True,
) -> Quiz:
    """
    Génère un quizz complet à partir de plusieurs chunks.

    Args:
        chunks: Liste de TextChunk.
        difficulty: "facile", "moyen", ou "difficile" (si difficulty_counts est None).
        num_questions: Nombre total (si difficulty_counts est None).
        difficulty_counts: Dict {difficulté: nombre}. Ex: {"facile": 5, "moyen": 10}.
        num_choices: Nombre de choix par question (4-7).
        num_correct: Nombre de bonnes réponses par question.
        difficulty_prompts: Prompts personnalisés.
        model: Modèle LLM à utiliser.
        progress_callback: Fonction callback(current, total) pour la progression.
        notions: Liste de notions pour guider la génération.
        batch_mode: Si True, utilise l'API Batch pour les appels parallèles.
        vision_mode: Si True, envoie les images des chunks au modèle vision.

    Returns:
        Quiz complet.
    """
    if not chunks:
        return Quiz(title="Quizz vide", difficulty="mixte")

    # Déterminer les comptes par difficulté
    if difficulty_counts is None:
        if difficulty is None or num_questions is None:
            difficulty_counts = {"moyen": 10}
        else:
            difficulty_counts = {difficulty: num_questions}

    all_questions = []
    diff_keys = [k for k, v in difficulty_counts.items() if v > 0]
    choice_labels = list(string.ascii_uppercase[:num_choices])

    # Préparer le texte des notions
    notions_text = ""
    if notions:
        from generation.notion_detector import notions_to_prompt_text
        notions_text = notions_to_prompt_text(notions)

    # Construire les tâches groupées par niveau de difficulté (pour l'anti-doublons)
    tasks_by_diff: Dict[str, List[tuple]] = {}
    for diff_name, diff_count in difficulty_counts.items():
        if diff_count <= 0:
            continue
        qpc = _distribute_questions(chunks, diff_count)
        tasks_by_diff[diff_name] = [(chunk, n_q) for chunk, n_q in zip(chunks, qpc) if n_q > 0]

    total_steps = sum(len(t) for t in tasks_by_diff.values())
    step_idx = 0

    # ─── MODE BATCH (par niveau séquentiel pour l'anti-doublons) ───────────
    if batch_mode and total_steps > 1:
        from generation.batch_service import BatchRequest, run_batch_json
        from core.llm_service import VISION_MODEL_NAME, MODEL_NAME

        for diff_name, diff_tasks in tasks_by_diff.items():
            # Questions déjà accumulées des niveaux précédents
            accumulated_q_texts = [q.question for q in all_questions] if all_questions else None

            batch_requests = []
            task_map = {}

            for idx, (chunk, n_q) in enumerate(diff_tasks):
                system_prompt, user_prompt = _build_quiz_prompt(
                    chunk.text, diff_name, n_q, num_choices, num_correct, choice_labels,
                    difficulty_prompts, notions_text=notions_text,
                    source_document=chunk.source_document,
                    existing_questions=accumulated_q_texts,
                    variable_correct=variable_correct,
                    persona=persona, notion_mixing=notion_mixing,
                )
                custom_id = f"quiz_{diff_name}_{idx}"
                images = chunk.page_images if (vision_mode and chunk.page_images) else None
                target_model = (VISION_MODEL_NAME or model or MODEL_NAME) if (vision_mode and images) else (model or MODEL_NAME)

                batch_requests.append(BatchRequest(
                    custom_id=custom_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=target_model,
                    temperature=0.6,
                    images=images,
                ))
                task_map[custom_id] = (chunk, diff_name)

            if progress_callback:
                progress_callback(step_idx, total_steps)

            results = run_batch_json(
                batch_requests,
                progress_callback=lambda done, _total, s=step_idx: (
                    progress_callback(s + done, total_steps) if progress_callback else None
                ),
            )

            for custom_id, parsed_json in results.items():
                chunk, diff_name_res = task_map.get(custom_id, (None, None))
                if chunk is None:
                    continue
                questions = _parse_quiz_questions(parsed_json, chunk, diff_name_res)
                all_questions.extend(questions)

            step_idx += len(diff_tasks)

    # ─── MODE SÉQUENTIEL ───────────────────────────────────────────────────
    else:
        for diff_name, diff_tasks in tasks_by_diff.items():
            # Questions déjà accumulées des niveaux précédents
            accumulated_q_texts = [q.question for q in all_questions] if all_questions else None

            for chunk, n_q in diff_tasks:
                step_idx += 1
                if progress_callback:
                    progress_callback(step_idx, total_steps)
                try:
                    questions = generate_quiz_from_chunk(
                        chunk=chunk,
                        difficulty=diff_name,
                        num_questions=n_q,
                        num_choices=num_choices,
                        num_correct=num_correct,
                        difficulty_prompts=difficulty_prompts,
                        model=model,
                        notions_text=notions_text,
                        vision_mode=vision_mode,
                        existing_questions=accumulated_q_texts,
                        variable_correct=variable_correct,
                        persona=persona,
                        notion_mixing=notion_mixing,
                    )
                    all_questions.extend(questions)
                    # Mettre à jour la liste pour les chunks suivants du même niveau
                    accumulated_q_texts = [q.question for q in all_questions]
                except Exception as e:
                    print(f"Erreur sur chunk ({diff_name}): {e}")
                    continue

    if progress_callback:
        progress_callback(total_steps, total_steps)

    quiz = Quiz(
        title="Quizz généré depuis PDF",
        difficulty=", ".join(diff_keys) if len(diff_keys) > 1 else (diff_keys[0] if diff_keys else "inconnue"),
        questions=all_questions,
        metadata={
            "difficulty_counts": difficulty_counts,
            "num_choices": num_choices,
            "num_correct_per_question": num_correct,
            "variable_correct": variable_correct,
            "total_questions_generated": len(all_questions),
            "model": model
        }
    )

    return quiz

