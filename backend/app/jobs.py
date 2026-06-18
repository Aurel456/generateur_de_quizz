"""Tâches asynchrones avec suivi de progression.

Les générations/vérifications LLM sont longues (plusieurs minutes) : les exécuter de
façon synchrone expose à des timeouts de proxy et ne donne aucun retour à l'utilisateur.

Principe : `POST /…-async` enregistre une tâche, la lance dans un pool de threads (le
métier est bloquant — appels HTTP au LLM) et renvoie immédiatement un `job_id`. Le
frontend interroge ensuite `GET /jobs/{id}` (polling) ou `GET /jobs/{id}/stream` (SSE)
pour afficher la progression et les items au fil de l'eau.

On réutilise les `progress_callback(current, total)` et `on_item(item)` déjà présents
dans la logique métier (`generation/*`).

Limites assumées (v1, cohérentes avec `doc_store`) : stockage en mémoire, mono-instance,
éviction des plus anciens jobs terminés. Pour le multi-instances, déporter vers Redis.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

log = logging.getLogger(__name__)

# Statuts possibles d'un job.
PENDING = "pending"
RUNNING = "running"
DONE = "done"
ERROR = "error"
_TERMINAL = (DONE, ERROR)


class Job:
    """État d'une tâche asynchrone. Tous les accès aux champs mutables sont protégés
    par `_lock` car ils sont écrits depuis le thread worker et lus depuis la requête."""

    def __init__(self, job_id: str, kind: str) -> None:
        self.id = job_id
        self.kind = kind
        self.status = PENDING
        self.current = 0
        self.total = 0
        self.message = ""
        self.items: list[dict] = []
        self.result: dict | None = None
        self.error = ""
        self.created_at = time.time()
        self.updated_at = self.created_at
        self._lock = threading.Lock()

    # ── Callbacks appelés depuis le thread worker (logique métier) ───────────
    def progress(self, current: int, total: int | None = None) -> None:
        with self._lock:
            self.current = int(current)
            if total is not None:
                self.total = int(total)
            self.updated_at = time.time()

    def set_message(self, message: str) -> None:
        with self._lock:
            self.message = str(message)
            self.updated_at = time.time()

    def add_item(self, item: dict) -> None:
        with self._lock:
            self.items.append(item)
            self.updated_at = time.time()

    # ── Transitions de cycle de vie (réservées au JobStore) ──────────────────
    def _mark_running(self) -> None:
        with self._lock:
            self.status = RUNNING
            self.updated_at = time.time()

    def _mark_done(self, result: dict | None) -> None:
        with self._lock:
            self.result = result
            self.status = DONE
            if self.total and self.current < self.total:
                self.current = self.total
            self.updated_at = time.time()

    def _mark_error(self, message: str) -> None:
        with self._lock:
            self.status = ERROR
            self.error = message or "Erreur interne pendant le traitement."
            self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        """Vue immuable de l'état courant (sérialisable JSON)."""
        with self._lock:
            return {
                "job_id": self.id,
                "kind": self.kind,
                "status": self.status,
                "current": self.current,
                "total": self.total,
                "message": self.message,
                "items": list(self.items),
                "result": self.result,
                "error": self.error,
            }

    @property
    def finished(self) -> bool:
        with self._lock:
            return self.status in _TERMINAL


class JobStore:
    def __init__(self, max_workers: int = 4, max_jobs: int = 200) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._max_jobs = max_jobs

    def submit(self, kind: str, fn: Callable[[Job], dict | None]) -> str:
        """Enregistre et lance une tâche. `fn(job)` reçoit le Job pour reporter la
        progression (job.progress / job.add_item) et doit renvoyer le résultat final."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id, kind)
        with self._lock:
            self._evict_locked()
            self._jobs[job_id] = job
        self._executor.submit(self._run, job, fn)
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: Job, fn: Callable[[Job], dict | None]) -> None:
        job._mark_running()
        try:
            result = fn(job)
            job._mark_done(result)
        except Exception as exc:  # noqa: BLE001 — l'erreur est remontée au client via le job
            log.exception("Job %s (%s) en échec", job.id, job.kind)
            job._mark_error(str(exc))

    def _evict_locked(self) -> None:
        """Évince les jobs terminés les plus anciens quand la limite est atteinte."""
        if len(self._jobs) < self._max_jobs:
            return
        terminated = sorted(
            (j for j in self._jobs.values() if j.finished),
            key=lambda j: j.updated_at,
        )
        to_remove = len(self._jobs) - self._max_jobs + 1
        for job in terminated[: max(1, to_remove)]:
            self._jobs.pop(job.id, None)


job_store = JobStore()
