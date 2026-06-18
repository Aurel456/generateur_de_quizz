"""Chatbot « assistant formateur » : aide à l'usage de l'application.

Distinct du mode libre (`/chat`, qui génère des quiz) : ici l'assistant répond aux
questions d'utilisation (« comment créer une session pool ? », « à quoi sert le mode
Vision ? »…) à partir d'un prompt système décrivant le fonctionnement de l'outil.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.schemas import AssistantChatRequest, AssistantChatResponse
from core.llm_service import call_llm_chat

router = APIRouter(prefix="/assistant", tags=["assistant"])
log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Tu es l'assistant d'aide du « Générateur de Quiz » (application de formation DGFIP). "
    "Tu aides les formateurs à UTILISER l'outil ; tu ne génères pas toi-même de quiz. "
    "Réponds de façon concise, en français, en t'appuyant sur le fonctionnement suivant :\n"
    "- Onglet Générer : 1) déposer un ou plusieurs documents (PDF/DOCX/PPTX/ODT/TXT), options "
    "avancées (taille de bloc, mode Vision pour les PDF en images, mode One-shot, DPI). "
    "2) Détecter/éditer les notions (ajout, regroupement par thématique, fusion IA, mélange). "
    "3) Configurer le quiz (niveaux facile/moyen/difficile, nb de choix, Vrai/Faux, persona, "
    "consignes libres avec analyse style/périmètre, prompts éditables par niveau, raisonnement). "
    "4) Générer (progression en temps réel), éditer les questions (manuel ou IA), vérifier par IA, "
    "annuler (historique). On peut aussi générer un quiz « sans document » depuis la base du modèle.\n"
    "- Exercices : calcul (auto-vérifiés par exécution Python), texte à trou, cas pratique ; "
    "édition fine des étapes/blancs/sous-questions.\n"
    "- Acronymes : détection (référentiel + IA), édition IA, ajout/suppression manuelle.\n"
    "- Partage : créer une Session (scoring serveur, bonnes réponses jamais envoyées avant "
    "soumission) ou une Session Pool (chaque participant tire un sous-ensemble, seuil de réussite, "
    "peut réessayer). Analytics : taux par question/notion, classement, recommandations IA, "
    "fermeture de session.\n"
    "- Ateliers : co-édition à 4 onglets (Questions/Exercices/Notions/Outils), réordonnancement, "
    "fusion d'ateliers, publication en session.\n"
    "- Mode libre : générer par conversation sans document.\n"
    "Si une question sort de ce périmètre, invite poliment à reformuler."
)


@router.post("/chat", response_model=AssistantChatResponse)
def chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in payload.messages]
    try:
        reply = call_llm_chat(messages)
    except Exception:
        log.exception("Échec assistant formateur")
        raise HTTPException(status_code=502, detail="L'assistant est momentanément indisponible.")
    return AssistantChatResponse(reply=reply)
