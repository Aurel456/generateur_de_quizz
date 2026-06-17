"""Statistiques globales (réutilise core.stats_manager)."""
import logging

from fastapi import APIRouter

from backend.app.schemas import GlobalStats

router = APIRouter(prefix="/stats", tags=["stats"])
log = logging.getLogger(__name__)


@router.get("/global", response_model=GlobalStats)
def global_stats() -> GlobalStats:
    try:
        from core.stats_manager import load_stats

        return GlobalStats(**load_stats())
    except Exception:
        # GLOBAL_STATS non configuré ou fichier illisible : on renvoie des zéros.
        log.exception("Lecture des stats globales impossible")
        return GlobalStats()
