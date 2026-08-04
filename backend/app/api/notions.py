"""Détection des notions fondamentales (réutilise generation.notion_detector)."""
import logging

from fastapi import APIRouter, HTTPException

from backend.app.converters import dict_to_notion, notion_to_dict
from backend.app.doc_store import DocEntry, doc_store
from backend.app.jobs import Job, job_store
from backend.app.schemas import (
    AcronymDTO,
    DetectNotionsRequest,
    DetectNotionsResponse,
    EditNotionsRequest,
    JobCreatedResponse,
    MergeNotionsRequest,
    MergeNotionsResponse,
    NotionDTO,
)
from generation.notion_detector import (
    detect_notions_and_acronyms,
    edit_notions_with_llm,
    merge_similar_notions,
)

router = APIRouter(prefix="/notions", tags=["notions"])
log = logging.getLogger(__name__)


def _resolve_doc(doc_id: str) -> DocEntry:
    entry = doc_store.get(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document inconnu ou expiré (doc_id).")
    return entry


def _run_detection(
    entry: DocEntry,
    known_acronyms: list[str],
    *,
    progress_callback=None,
    on_item=None,
    job: Job | None = None,
) -> DetectNotionsResponse:
    """Notions + acronymes inconnus en une seule passe LLM par bloc (comme Streamlit).

    `on_item` est appelé à chaque *nouvelle* notion : le client peut ainsi les afficher
    au fil de l'eau, la liste finale restant autoritaire (les notions déjà trouvées sont
    enrichies bloc après bloc).
    """
    failures: list[int] = []

    def on_error(index: int, _exc: Exception) -> None:
        failures.append(index)
        if job is not None:
            job.set_message(f"⚠️ {len(failures)} bloc(s) non analysé(s) — voir les logs serveur.")

    notions, acronyms = detect_notions_and_acronyms(
        entry.chunks,
        known_acronyms=known_acronyms,
        vision_mode=entry.vision,
        progress_callback=progress_callback,
        on_item=on_item,
        on_error=on_error,
    )

    # Tous les blocs en échec : le résultat serait vide sans explication — on remonte
    # l'erreur plutôt que de renvoyer « 0 notion » silencieusement.
    if entry.chunks and len(failures) == len(entry.chunks):
        raise RuntimeError(
            "Aucun bloc n'a pu être analysé par le modèle (service LLM indisponible "
            "ou réponse illisible)."
        )

    return DetectNotionsResponse(
        notions=[NotionDTO(**notion_to_dict(n)) for n in notions],
        acronyms=[
            AcronymDTO(
                acronym=a["acronym"],
                definition=a.get("definition", ""),
                all_definitions=[a["definition"]] if a.get("definition") else [],
                source_document=a.get("source_document", ""),
                source_pages=a.get("source_pages", []),
                enabled=True,
                from_reference=False,
            )
            for a in acronyms
        ],
        failed_chunks=len(failures),
        total_chunks=len(entry.chunks),
    )


# Endpoint synchrone (def) : l'appel LLM est bloquant et FastAPI l'exécute dans un
# threadpool, sans bloquer la boucle asyncio.
@router.post("/detect", response_model=DetectNotionsResponse)
def detect(payload: DetectNotionsRequest) -> DetectNotionsResponse:
    entry = _resolve_doc(payload.doc_id)
    try:
        return _run_detection(entry, payload.known_acronyms)
    except Exception:
        log.exception("Échec détection des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de la détection des notions.")


@router.post("/detect-async", response_model=JobCreatedResponse)
def detect_async(payload: DetectNotionsRequest) -> JobCreatedResponse:
    entry = _resolve_doc(payload.doc_id)

    def task(job: Job) -> dict:
        return _run_detection(
            entry,
            payload.known_acronyms,
            progress_callback=job.progress,
            on_item=lambda n: job.add_item(notion_to_dict(n)),
            job=job,
        ).model_dump()

    return JobCreatedResponse(job_id=job_store.submit("notions", task))


@router.post("/edit", response_model=DetectNotionsResponse)
def edit(payload: EditNotionsRequest) -> DetectNotionsResponse:
    """Modifie la liste de notions via une instruction en langage naturel (LLM)."""
    current = [dict_to_notion(n.model_dump()) for n in payload.notions]
    try:
        # `edit_notions_with_llm` renvoie (notions, explication).
        updated, _explanation = edit_notions_with_llm(current, payload.instruction)
    except Exception:
        log.exception("Échec édition des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de l'édition des notions.")
    return DetectNotionsResponse(notions=[NotionDTO(**notion_to_dict(n)) for n in updated])


@router.post("/merge", response_model=MergeNotionsResponse)
def merge(payload: MergeNotionsRequest) -> MergeNotionsResponse:
    """Fusionne les notions similaires/redondantes via le LLM."""
    current = [dict_to_notion(n.model_dump()) for n in payload.notions]
    try:
        merged, summary = merge_similar_notions(current)
    except Exception:
        log.exception("Échec fusion des notions")
        raise HTTPException(status_code=502, detail="Erreur lors de la fusion des notions.")
    return MergeNotionsResponse(
        notions=[NotionDTO(**notion_to_dict(n)) for n in merged],
        summary=str(summary or ""),
    )
