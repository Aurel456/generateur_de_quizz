"""Backend FastAPI du générateur de quiz — migration DSFR (branche dev-dsfr).

Ce service REÉUTILISE la logique métier existante (packages `core`, `generation`,
`processing`, `sessions`, `export`) sans la dupliquer : il l'expose en API REST pour
le nouveau frontend Vue + DSFR, en parallèle de l'app Streamlit (approche strangler).

Lancement (depuis la racine du repo) :
    uvicorn backend.main:app --reload
"""
import sys
from pathlib import Path

# Rendre les packages métier du repo importables quel que soit le dossier de lancement.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.api import (  # noqa: E402
    acronyms,
    chat,
    documents,
    exercises,
    exports,
    health,
    jobs,
    notions,
    quiz,
    sessions,
    stats,
    workshops,
)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(notions.router)
app.include_router(acronyms.router)
app.include_router(quiz.router)
app.include_router(exercises.router)
app.include_router(exports.router)
app.include_router(sessions.router)
app.include_router(workshops.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(jobs.router)


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running"}
