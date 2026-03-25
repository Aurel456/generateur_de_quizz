import json
import os
from threading import Lock

from dotenv import load_dotenv
load_dotenv(".env")


STATS_FILE = os.getenv("GLOBAL_STATS")
_lock = Lock()

_DEFAULT_STATS = {"total_questions": 0, "total_documents": 0, "total_tokens": 0, "total_sessions": 0}


def load_stats():
    """Charge les statistiques globales depuis le fichier JSON."""
    if not os.path.exists(STATS_FILE):
        return dict(_DEFAULT_STATS)
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Migration : ajouter les clés manquantes
        for k, v in _DEFAULT_STATS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_DEFAULT_STATS)


def increment_stats(questions=0, documents=0, tokens=0, sessions=0):
    """Incrémente les statistiques globales et les sauvegarde de manière thread-safe."""
    with _lock:
        if not os.path.exists(STATS_FILE):
            stats = dict(_DEFAULT_STATS)
        else:
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
                for k, v in _DEFAULT_STATS.items():
                    stats.setdefault(k, v)
            except Exception:
                stats = dict(_DEFAULT_STATS)

        stats["total_questions"] += questions
        stats["total_documents"] += documents
        stats["total_tokens"] += tokens
        stats["total_sessions"] += sessions

        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)

    return stats
