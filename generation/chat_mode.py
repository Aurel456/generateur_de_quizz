"""
chat_mode.py — Mode libre : génération de quizz/exercices via conversation LLM.

Machine à états pour guider la conversation :
WELCOME → TOPIC_DISCOVERY → NOTION_GENERATION → NOTION_VALIDATION → GENERATION_CONFIG → GENERATING → COMPLETE

Génération directe : le LLM génère les questions directement à partir du sujet
et des notions, sans passer par un document synthétique intermédiaire.
"""

import string
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.llm_service import call_llm_chat, call_llm_chat_json
from generation.notion_detector import Notion
from generation.quiz_generator import Quiz, QuizQuestion
from generation.exercise_generator import Exercise


class ChatState(str, Enum):
    WELCOME = "welcome"
    TOPIC_DISCOVERY = "topic"
    NOTION_GENERATION = "notions"
    NOTION_VALIDATION = "validation"
    GENERATION_CONFIG = "config"
    GENERATING = "generating"
    COMPLETE = "complete"


@dataclass
class ChatSession:
    state: ChatState = ChatState.WELCOME
    messages: List[Dict[str, str]] = field(default_factory=list)
    topic: str = ""
    notions: List[Notion] = field(default_factory=list)
    quiz: Optional[Quiz] = None
    exercises: Optional[list] = None
    # Config extraite de la conversation (pré-remplissage)
    suggested_config: Optional[Dict] = None


# ─── System prompts par état ─────────────────────────────────────────────────

_SYSTEM_PROMPTS = {
    ChatState.WELCOME: """Tu es un assistant pédagogique expert en création de quizz et exercices.
L'utilisateur veut générer un quizz ou des exercices sur un sujet, SANS document source.
Ton rôle est de comprendre précisément le sujet et les besoins de l'utilisateur.

Commence par accueillir l'utilisateur chaleureusement et demande-lui :
- Sur quel sujet/thème il veut un quizz ou des exercices
- Quel est le contexte (formation, révision, certification...)

Sois concis et engageant. Réponds en français.""",

    ChatState.TOPIC_DISCOVERY: """Tu es un assistant pédagogique expert. L'utilisateur t'a indiqué un sujet.
Tu dois maintenant approfondir pour bien cerner le périmètre :
- Quels aspects spécifiques du sujet ?
- Quel niveau de difficulté global ? (débutant, intermédiaire, avancé)
- Y a-t-il des sous-thèmes à inclure ou exclure ?
- Combien de questions veut-il ? Quel type (QCM, exercices) ?

IMPORTANT : Retiens bien les préférences de l'utilisateur concernant le nombre de questions,
le niveau de difficulté, le type de génération. Ces infos seront réutilisées plus tard.

Pose 2-3 questions ciblées pour affiner le sujet. Ne pose pas trop de questions d'un coup.

Quand tu estimes avoir assez d'informations pour générer des notions fondamentales pertinentes,
termine ta réponse par la ligne exacte : [TRANSITION:notions]

Sois concis. Réponds en français.""",

    ChatState.NOTION_GENERATION: """Tu es un expert pédagogique. À partir de la conversation précédente,
tu dois identifier les notions fondamentales (concepts clés, définitions, théorèmes, principes)
que l'utilisateur devrait maîtriser sur le sujet discuté.

Réponds UNIQUEMENT avec un objet JSON valide au format suivant :
{
    "notions": [
        {
            "title": "Titre concis de la notion",
            "description": "Description claire en 1-3 phrases"
        }
    ]
}

Génère entre 5 et 15 notions couvrant les aspects clés du sujet discuté.
Les notions doivent être suffisamment précises pour servir de base à la génération de questions.""",
}


def _get_system_prompt(state: ChatState) -> str:
    """Retourne le system prompt pour un état donné."""
    return _SYSTEM_PROMPTS.get(state, "Tu es un assistant pédagogique expert. Réponds en français.")


def _build_messages_with_system(session: ChatSession, system_prompt: str) -> List[Dict[str, str]]:
    """Construit la liste de messages avec le system prompt actuel."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(session.messages)
    return messages


def init_session() -> Tuple[str, ChatSession]:
    """
    Initialise une nouvelle session de chat et retourne le message d'accueil.

    Returns:
        (message_accueil, session)
    """
    session = ChatSession(state=ChatState.WELCOME)

    welcome_msg = (
        "👋 Bonjour ! Je suis votre assistant pour créer des quizz et exercices.\n\n"
        "Vous n'avez pas besoin de document — dites-moi simplement **sur quel sujet** "
        "vous souhaitez générer des questions.\n\n"
        "Par exemple : *« Je veux un quizz de 10 questions faciles sur Kubernetes »*, "
        "*« Des exercices de thermodynamique niveau L2 »*, etc.\n\n"
        "N'hésitez pas à préciser le **nombre de questions**, le **niveau de difficulté** "
        "et le **type** (QCM, exercices, ou les deux)."
    )

    session.messages.append({"role": "assistant", "content": welcome_msg})
    session.state = ChatState.TOPIC_DISCOVERY

    return welcome_msg, session


def process_user_message(
    session: ChatSession,
    user_input: str,
    model: Optional[str] = None,
) -> Tuple[str, ChatSession]:
    """
    Traite un message utilisateur, fait avancer la machine à états,
    et retourne la réponse du LLM + la session mise à jour.
    """
    # Ajouter le message utilisateur à l'historique
    session.messages.append({"role": "user", "content": user_input})

    # Capturer le sujet au premier message utilisateur
    if session.state == ChatState.TOPIC_DISCOVERY and not session.topic:
        session.topic = user_input

    # Phase de découverte du sujet
    if session.state == ChatState.TOPIC_DISCOVERY:
        system_prompt = _get_system_prompt(ChatState.TOPIC_DISCOVERY)
        messages = _build_messages_with_system(session, system_prompt)

        response = call_llm_chat(messages, model=model, temperature=0.7)

        # Détecter la transition automatique
        if "[TRANSITION:notions]" in response:
            response = response.replace("[TRANSITION:notions]", "").strip()
            response += "\n\n🧠 **Je génère les notions fondamentales...**"
            session.messages.append({"role": "assistant", "content": response})
            session.state = ChatState.NOTION_GENERATION

            # Générer les notions automatiquement
            notions = generate_notions_from_chat(session, model=model)
            session.notions = notions
            session.state = ChatState.NOTION_VALIDATION

            # Extraire la config suggérée depuis la conversation
            session.suggested_config = extract_generation_config(session, model=model)

            # Construire le message de présentation des notions
            notions_text = "\n".join(
                f"{i+1}. **{n.title}** — {n.description}"
                for i, n in enumerate(notions)
            )
            notions_msg = (
                f"📚 Voici les **{len(notions)} notions fondamentales** que j'ai identifiées :\n\n"
                f"{notions_text}\n\n"
                "✅ **Validez ces notions** pour passer à la configuration du quizz, "
                "ou modifiez-les avec les contrôles ci-dessous."
            )
            session.messages.append({"role": "assistant", "content": notions_msg})
            return notions_msg, session
        else:
            session.messages.append({"role": "assistant", "content": response})
            return response, session

    # Phase de validation des notions (interaction libre)
    if session.state == ChatState.NOTION_VALIDATION:
        # L'utilisateur peut demander des modifications aux notions via le chat
        system_prompt = (
            "Tu es un assistant pédagogique. L'utilisateur peut te demander de modifier "
            "les notions fondamentales (ajouter, supprimer, reformuler). "
            "Si l'utilisateur valide les notions ou veut passer à la génération, "
            "termine par [TRANSITION:config]\n"
            "Réponds en français de manière concise."
        )
        messages = _build_messages_with_system(session, system_prompt)
        response = call_llm_chat(messages, model=model, temperature=0.7)

        if "[TRANSITION:config]" in response:
            response = response.replace("[TRANSITION:config]", "").strip()
            session.state = ChatState.GENERATION_CONFIG
            response += "\n\n⚙️ **Configurez maintenant le quizz/exercices** avec les options ci-dessous."

        session.messages.append({"role": "assistant", "content": response})
        return response, session

    # État par défaut
    session.messages.append({"role": "assistant", "content": "Je suis prêt à vous aider. Quel sujet vous intéresse ?"})
    return "Je suis prêt à vous aider. Quel sujet vous intéresse ?", session


def generate_notions_from_chat(
    session: ChatSession,
    model: Optional[str] = None,
) -> List[Notion]:
    """
    Extrait des notions structurées depuis l'historique de conversation.
    """
    system_prompt = _get_system_prompt(ChatState.NOTION_GENERATION)
    messages = _build_messages_with_system(session, system_prompt)
    # Ajouter une instruction explicite pour générer les notions
    messages.append({
        "role": "user",
        "content": (
            "À partir de notre conversation, génère la liste des notions fondamentales "
            "au format JSON demandé."
        )
    })

    result = call_llm_chat_json(messages, model=model, temperature=0.5)

    notions = []
    for n_data in result.get("notions", []):
        try:
            notions.append(Notion(
                title=n_data["title"],
                description=n_data.get("description", ""),
                source_document="Généré par IA",
                source_pages=[],
                enabled=True,
            ))
        except (KeyError, TypeError):
            continue

    return notions


def extract_generation_config(
    session: ChatSession,
    model: Optional[str] = None,
) -> Dict:
    """
    Extrait les préférences de génération depuis l'historique de conversation.

    Analyse les messages pour identifier :
    - Le type souhaité (quiz, exercices, les deux)
    - Le nombre de questions par niveau de difficulté
    - Le nombre de choix (pour QCM)

    Returns:
        Dict avec les clés : gen_type, facile, moyen, difficile, num_choices, num_correct
    """
    system_prompt = """Tu es un assistant qui analyse une conversation pour extraire les préférences
de génération de quizz/exercices exprimées par l'utilisateur.

Réponds UNIQUEMENT avec un objet JSON valide au format suivant :
{
    "gen_type": "quiz",
    "facile": 0,
    "moyen": 5,
    "difficile": 0,
    "num_choices": 4,
    "num_correct": 1
}

Règles :
- "gen_type" : "quiz" si l'utilisateur veut un QCM, "exercices" si exercices, "les_deux" si les deux.
  Si non précisé, mets "quiz".
- "facile", "moyen", "difficile" : nombre de questions par niveau.
  Si l'utilisateur dit juste un nombre total (ex: "10 questions"), répartis selon le niveau mentionné.
  Ex: "10 questions faciles" → facile=10, moyen=0, difficile=0
  Ex: "5 questions" sans précision → facile=0, moyen=5, difficile=0
  Ex: "10 questions dont 5 faciles et 5 difficiles" → facile=5, moyen=0, difficile=5
  Si l'utilisateur n'a rien mentionné, mets facile=0, moyen=5, difficile=0.
- "num_choices" : nombre de choix par question QCM (défaut 4)
- "num_correct" : nombre de bonnes réponses par question (défaut 1)

Analyse TOUTE la conversation pour trouver ces informations."""

    messages = [{"role": "system", "content": system_prompt}]
    # Ajouter l'historique de conversation (sans les system prompts)
    for msg in session.messages:
        messages.append(msg)
    messages.append({
        "role": "user",
        "content": "Analyse la conversation ci-dessus et extrais les préférences de génération au format JSON."
    })

    try:
        result = call_llm_chat_json(messages, model=model, temperature=0.2)
        return {
            "gen_type": result.get("gen_type", "quiz"),
            "facile": int(result.get("facile", 0)),
            "moyen": int(result.get("moyen", 5)),
            "difficile": int(result.get("difficile", 0)),
            "num_choices": int(result.get("num_choices", 4)),
            "num_correct": int(result.get("num_correct", 1)),
        }
    except Exception:
        # Fallback par défaut
        return {
            "gen_type": "quiz",
            "facile": 0,
            "moyen": 5,
            "difficile": 0,
            "num_choices": 4,
            "num_correct": 1,
        }


# ─── Génération directe (sans document synthétique) ─────────────────────────


def generate_quiz_direct(
    session: ChatSession,
    difficulty_counts: Dict[str, int],
    num_choices: int = 4,
    num_correct: int = 1,
    model: Optional[str] = None,
    progress_callback=None,
    batch_mode: bool = False,
) -> Quiz:
    """
    Génère un quizz QCM directement à partir du sujet et des notions,
    sans passer par un document synthétique intermédiaire.
    """
    choice_labels = list(string.ascii_uppercase[:num_choices])
    labels_str = ", ".join(choice_labels)

    active_notions = [n for n in session.notions if n.enabled]
    notions_list = "\n".join(
        f"- {n.title} : {n.description}" for n in active_notions
    )

    all_questions: List[QuizQuestion] = []
    difficulties = [(d, c) for d, c in difficulty_counts.items() if c > 0]
    total_steps = len(difficulties)
    current_step = 0

    def _build_direct_quiz_prompt(difficulty, count):
        sys = f"""Tu es un expert en pédagogie et en création de quizz éducatifs.
Tu dois générer exactement {count} questions QCM de niveau {difficulty}.

SUJET : {session.topic}

NOTIONS FONDAMENTALES À COUVRIR :
{notions_list}

Les questions doivent prioritairement couvrir ces notions fondamentales.

RÈGLES STRICTES :
1. Chaque question doit avoir exactement {num_choices} choix de réponse ({labels_str})
2. Chaque question doit avoir exactement {num_correct} bonne(s) réponse(s)
3. Chaque question doit inclure une explication de la réponse
4. Les questions doivent être variées et couvrir différentes notions
5. Les choix de réponse doivent être du même type et de longueur similaire
6. Le niveau de difficulté est : {difficulty}
7. Chaque question doit être auto-suffisante et fournir tout le contexte nécessaire
8. Pour chaque question, indique dans 'related_notions' le(s) titre(s) exact(s) des notions couvertes

FORMAT DE RÉPONSE (JSON strict) :
{{
    "questions": [
        {{
            "question": "La question posée ?",
            "choices": {{{", ".join(f'"{l}": "Choix {l}"' for l in choice_labels)}}},
            "correct_answers": {list(choice_labels[:num_correct])},
            "explanation": "Explication détaillée de la bonne réponse...",
            "difficulty_level": "{difficulty}",
            "related_notions": ["Titre notion 1", "Titre notion 2"]
        }}
    ]
}}"""
        usr = f"Génère exactement {count} questions QCM de niveau {difficulty} sur le sujet '{session.topic}'."
        return sys, usr

    def _parse_direct_quiz_result(result, difficulty):
        questions = []
        for q_data in result.get("questions", []):
            try:
                question = QuizQuestion(
                    question=q_data["question"],
                    choices=q_data["choices"],
                    correct_answers=q_data["correct_answers"],
                    explanation=q_data.get("explanation", ""),
                    source_pages=[],
                    difficulty_level=q_data.get("difficulty_level", difficulty),
                    source_document="Généré par IA",
                    citation="",
                    related_notions=q_data.get("related_notions", []),
                )
                if all(ans in question.choices for ans in question.correct_answers):
                    questions.append(question)
            except (KeyError, TypeError):
                continue
        return questions

    # ─── MODE BATCH ────────────────────────────────────────────────────────
    if batch_mode and total_steps > 1:
        from generation.batch_service import BatchRequest, run_batch_json
        from core.llm_service import MODEL_NAME as _MODEL_NAME

        batch_requests = []
        task_map = {}
        for idx, (difficulty, count) in enumerate(difficulties):
            sys_prompt, usr_prompt = _build_direct_quiz_prompt(difficulty, count)
            custom_id = f"chat_quiz_{difficulty}_{idx}"
            batch_requests.append(BatchRequest(
                custom_id=custom_id,
                system_prompt=sys_prompt,
                user_prompt=usr_prompt,
                model=model or _MODEL_NAME,
                temperature=0.6,
            ))
            task_map[custom_id] = difficulty

        if progress_callback:
            progress_callback(0, total_steps)

        results = run_batch_json(
            batch_requests,
            progress_callback=lambda done, total: progress_callback(done, total) if progress_callback else None,
        )

        for custom_id, parsed_json in results.items():
            difficulty = task_map.get(custom_id)
            if difficulty:
                all_questions.extend(_parse_direct_quiz_result(parsed_json, difficulty))
    # ─── MODE SÉQUENTIEL ───────────────────────────────────────────────────
    else:
        for difficulty, count in difficulties:
            if progress_callback:
                progress_callback(current_step, total_steps)

            sys_prompt, usr_prompt = _build_direct_quiz_prompt(difficulty, count)
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt},
            ]
            result = call_llm_chat_json(messages, model=model, temperature=0.6)
            all_questions.extend(_parse_direct_quiz_result(result, difficulty))
            current_step += 1

    if progress_callback:
        progress_callback(total_steps, total_steps)

    return Quiz(
        title=f"Quizz — {session.topic}",
        difficulty="mixte",
        questions=all_questions,
    )


def generate_exercises_direct(
    session: ChatSession,
    difficulty_counts: Dict[str, int],
    model: Optional[str] = None,
    progress_callback=None,
    batch_mode: bool = False,
) -> List[Exercise]:
    """
    Génère des exercices directement à partir du sujet et des notions,
    sans passer par un document synthétique intermédiaire.
    """
    active_notions = [n for n in session.notions if n.enabled]
    notions_list = "\n".join(
        f"- {n.title} : {n.description}" for n in active_notions
    )

    all_exercises: List[Exercise] = []
    difficulties = [(d, c) for d, c in difficulty_counts.items() if c > 0]
    total_steps = len(difficulties)
    current_step = 0

    def _build_direct_exercise_prompt(difficulty, count):
        sys = f"""Tu es un expert pédagogique qui crée des exercices de niveau {difficulty.upper()}.
Tu dois créer exactement {count} exercice(s) sur le sujet donné.

SUJET : {session.topic}

NOTIONS FONDAMENTALES À COUVRIR :
{notions_list}

Les exercices doivent couvrir ces notions fondamentales.

RÈGLES :
1. Chaque exercice doit avoir une réponse numérique claire et vérifiable
2. L'énoncé doit être clair, complet et auto-suffisant
3. La résolution doit être décomposée en étapes claires et numérotées
4. Le code Python doit reproduire INTÉGRALEMENT les calculs étape par étape
5. Le code NE DOIT PAS se contenter de poser result = <valeur_finale>
6. Le code doit stocker le résultat final dans une variable nommée 'result'
7. Le code doit afficher chaque étape intermédiaire avec print()
8. Pour chaque exercice, indique dans 'related_notions' le(s) titre(s) exact(s) des notions couvertes

FORMAT DE RÉPONSE (JSON strict) :
{{
    "exercises": [
        {{
            "statement": "Énoncé complet de l'exercice...",
            "expected_answer": "42.5",
            "steps": [
                "Étape 1 : ...",
                "Étape 2 : ..."
            ],
            "correction": "Correction détaillée...",
            "verification_code": "# Code Python complet\\nresult = ...",
            "difficulty_level": "{difficulty}",
            "related_notions": ["Titre notion 1"]
        }}
    ]
}}"""
        usr = f"Génère exactement {count} exercice(s) de niveau {difficulty} sur le sujet '{session.topic}'."
        return sys, usr

    def _parse_direct_exercise_result(result, difficulty):
        exercises = []
        for ex_data in result.get("exercises", []):
            try:
                steps = ex_data.get("steps", [])
                exercise = Exercise(
                    statement=ex_data["statement"],
                    expected_answer=str(ex_data.get("expected_answer", "")),
                    steps=steps,
                    num_steps=len(steps),
                    correction=ex_data.get("correction", ""),
                    verification_code=ex_data.get("verification_code", ""),
                    verified=False,
                    verification_output="",
                    source_pages=[],
                    source_document="Généré par IA",
                    citation="",
                    difficulty_level=ex_data.get("difficulty_level", difficulty),
                    related_notions=ex_data.get("related_notions", []),
                )
                exercises.append(exercise)
            except (KeyError, TypeError):
                continue
        return exercises

    # ─── MODE BATCH ────────────────────────────────────────────────────────
    if batch_mode and total_steps > 1:
        from generation.batch_service import BatchRequest, run_batch_json
        from llm_service import MODEL_NAME as _MODEL_NAME

        batch_requests = []
        task_map = {}
        for idx, (difficulty, count) in enumerate(difficulties):
            sys_prompt, usr_prompt = _build_direct_exercise_prompt(difficulty, count)
            custom_id = f"chat_ex_{difficulty}_{idx}"
            batch_requests.append(BatchRequest(
                custom_id=custom_id,
                system_prompt=sys_prompt,
                user_prompt=usr_prompt,
                model=model or _MODEL_NAME,
                temperature=0.5,
            ))
            task_map[custom_id] = difficulty

        if progress_callback:
            progress_callback(0, total_steps)

        results = run_batch_json(
            batch_requests,
            progress_callback=lambda done, total: progress_callback(done, total) if progress_callback else None,
        )

        for custom_id, parsed_json in results.items():
            difficulty = task_map.get(custom_id)
            if difficulty:
                all_exercises.extend(_parse_direct_exercise_result(parsed_json, difficulty))
    # ─── MODE SÉQUENTIEL ───────────────────────────────────────────────────
    else:
        for difficulty, count in difficulties:
            if progress_callback:
                progress_callback(current_step, total_steps)

            sys_prompt, usr_prompt = _build_direct_exercise_prompt(difficulty, count)
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt},
            ]
            result = call_llm_chat_json(messages, model=model, temperature=0.5)
            all_exercises.extend(_parse_direct_exercise_result(result, difficulty))
            current_step += 1

    if progress_callback:
        progress_callback(total_steps, total_steps)

    return all_exercises
