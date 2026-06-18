"""Suivi des tâches asynchrones : polling JSON et flux SSE.

Le frontend appelle un endpoint `…-async` (qui renvoie un `job_id`) puis :
- interroge `GET /jobs/{id}` en boucle (polling — robuste derrière tout reverse-proxy), ou
- s'abonne à `GET /jobs/{id}/stream` (Server-Sent Events — nécessite `proxy_buffering off`).
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.jobs import job_store
from backend.app.schemas import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])
log = logging.getLogger(__name__)

# Intervalle d'émission des événements SSE (s) tant que le job tourne.
_SSE_INTERVAL = 0.4


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tâche inconnue ou expirée.")
    return JobStatusResponse(**job.snapshot())


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Tâche inconnue ou expirée.")

    async def event_gen():
        while True:
            snapshot = job.snapshot()
            yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            if snapshot["status"] in ("done", "error"):
                break
            await asyncio.sleep(_SSE_INTERVAL)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # désactive le buffering nginx pour le flux SSE
        },
    )
