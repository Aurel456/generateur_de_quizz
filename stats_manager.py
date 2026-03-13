import json
import os
from threading import Lock

STATS_FILE = "/app/shared_data/global_stats.json"
_lock = Lock()

def load_stats():
    """Charge les statistiques globales depuis le fichier JSON."""
    if not os.path.exists(STATS_FILE):
        return {"total_questions": 0, "total_documents": 0, "total_tokens": 0}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"total_questions": 0, "total_documents": 0, "total_tokens": 0}

def increment_stats(questions=0, documents=0, tokens=0):
    """Incrémente les statistiques globales et les sauvegarde de manière thread-safe."""
    with _lock:
        # Recharger sous lock pour éviter les conditions de course
        if not os.path.exists(STATS_FILE):
            stats = {"total_questions": 0, "total_documents": 0, "total_tokens": 0}
        else:
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
            except Exception:
                stats = {"total_questions": 0, "total_documents": 0, "total_tokens": 0}
        
        stats["total_questions"] += questions
        stats["total_documents"] += documents
        stats["total_tokens"] += tokens
        
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
        
    return stats
