"""Tests de l'infra de tâches asynchrones (`backend/app/jobs.py`).

Ces tests n'ont AUCUNE dépendance lourde (ni LLM, ni traitement documentaire) : ils
valident la mécanique du JobStore (progression, items, succès, erreur, éviction) et
tournent hors ligne. Exécution : `pytest backend/tests/test_jobs.py` ou directement
`python backend/tests/test_jobs.py`.
"""
import sys
import time
from pathlib import Path

# Rend les packages du repo importables quel que soit le dossier de lancement.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.jobs import DONE, ERROR, JobStore  # noqa: E402


def _wait(store: JobStore, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = store.get(job_id)
        assert job is not None
        snap = job.snapshot()
        if snap["status"] in (DONE, ERROR):
            return snap
        time.sleep(0.02)
    raise AssertionError("La tâche ne s'est pas terminée dans le délai imparti.")


def test_job_success_with_progress_and_items():
    store = JobStore(max_workers=2)

    def task(job):
        job.progress(0, 3)
        for i in range(3):
            job.add_item({"i": i})
            job.progress(i + 1, 3)
        return {"count": 3}

    snap = _wait(store, store.submit("test", task))
    assert snap["status"] == DONE
    assert snap["result"] == {"count": 3}
    assert len(snap["items"]) == 3
    assert snap["current"] == 3 and snap["total"] == 3


def test_job_error_is_captured():
    store = JobStore()

    def task(job):
        raise ValueError("boom")

    snap = _wait(store, store.submit("test", task))
    assert snap["status"] == ERROR
    assert "boom" in snap["error"]
    assert snap["result"] is None


def test_done_forces_progress_to_total():
    store = JobStore()

    def task(job):
        job.progress(2, 5)  # on quitte sans atteindre le total
        return {}

    snap = _wait(store, store.submit("test", task))
    assert snap["status"] == DONE
    assert snap["current"] == snap["total"] == 5


def test_unknown_job_returns_none():
    store = JobStore()
    assert store.get("inconnu") is None


def test_eviction_keeps_within_limit():
    store = JobStore(max_workers=2, max_jobs=5)
    ids = []
    for _ in range(20):
        # On attend chaque job juste après l'avoir soumis : il ne peut être évincé
        # que par un submit ULTÉRIEUR, donc il existe encore pendant son propre wait.
        jid = store.submit("t", lambda job: {"ok": True})
        _wait(store, jid)
        ids.append(jid)
    alive = sum(1 for i in ids if store.get(i) is not None)
    assert alive <= 5, f"trop de jobs conservés : {alive}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in tests:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(tests)} tests passés.")
