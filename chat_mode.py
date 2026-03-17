"""
chat_mode.py — Mode libre : génération de quizz/exercices via conversation LLM.

Machine à états pour guider la conversation :
WELCOME → TOPIC_DISCOVERY → NOTION_GENERATION → NOTION_VALIDATION → GENERATION_CONFIG → GENERATING → COMPLETE
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from llm_service import call_llm_chat, call_llm_chat_json, count_tokens
from document_processor import TextChunk
from notion_detector import Notion
from quiz_generator import Quiz


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
    synthetic_chunks: List[TextChunk] = field(default_factory=list)
    quiz: Optional[Quiz] = None
    exercises: Optional[list] = None


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
    system_prompt = _get_system_prompt(ChatState.WELCOME)

    welcome_msg = (
        "👋 Bonjour ! Je suis votre assistant pour créer des quizz et exercices.\n\n"
        "Vous n'avez pas besoin de document — dites-moi simplement **sur quel sujet** "
        "vous souhaitez générer des questions.\n\n"
        "Par exemple : *« Je veux un quizz sur Kubernetes »*, "
        "*« Des exercices de thermodynamique niveau L2 »*, etc."
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


def generate_synthetic_chunks(
    session: ChatSession,
    model: Optional[str] = None,
) -> List[TextChunk]:
    """
    Génère des chunks de texte synthétiques à partir des notions validées.
    Le LLM produit un texte éducatif structuré couvrant les notions,
    qui servira de source pour generate_quiz / generate_exercises.
    """
    active_notions = [n for n in session.notions if n.enabled]
    if not active_notions:
        return []

    notions_list = "\n".join(
        f"- {n.title} : {n.description}" for n in active_notions
    )

    system_prompt = """Tu es un expert pédagogique. Tu dois rédiger un texte éducatif structuré
qui couvre toutes les notions fondamentales fournies.

Ce texte servira de base à la génération de questions de quizz et d'exercices.
Il doit être :
- Détaillé et factuel (avec des définitions, formules, exemples concrets, valeurs numériques)
- Structuré par section (une par notion ou groupe de notions liées)
- Riche en informations vérifiables (chiffres, dates, formules, comparaisons)
- Autonome (compréhensible sans contexte extérieur)

Écris un texte de 2000 à 4000 mots couvrant exhaustivement les notions."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"Sujet : {session.topic}\n\n"
            f"Notions à couvrir :\n{notions_list}\n\n"
            "Rédige le texte éducatif structuré."
        )}
    ]

    text = call_llm_chat(messages, model=model, temperature=0.5)

    # Créer un ou plusieurs chunks
    tokens = count_tokens(text)
    chunk = TextChunk(
        text=text,
        source_pages=[],
        token_count=tokens,
        source_document="Généré par IA",
    )

    return [chunk]
