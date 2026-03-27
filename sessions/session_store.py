"""
session_store.py — Backend SQLite pour les sessions de quizz partagées.

Gère la création de sessions, la soumission de résultats et le calcul d'analytics.
"""

import json
import os
import random
import sqlite3
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("QUIZ_SESSIONS_DB", "shared_data/quiz_sessions.db")


@dataclass
class WorkSession:
    work_session_id: str
    work_code: str
    title: str
    draft_quiz_json: str
    draft_notions_json: str
    owner_name: str
    last_modified: str
    created_at: str
    status: str = "draft"  # "draft" | "published"
    draft_exercises_json: str = "[]"  # Exercices brouillon de l'atelier


@dataclass
class QuizSession:
    session_id: str
    session_code: str
    title: str
    quiz_json: str
    notions_json: str
    created_at: str
    is_active: bool = True
    # Pool fields (None for regular sessions)
    pool_json: Optional[str] = None
    subset_size: Optional[int] = None
    pass_threshold: float = 0.7
    exercises_json: str = "[]"  # Exercices associés à la session


@dataclass
class ParticipantResult:
    result_id: str
    session_id: str
    participant_name: str
    answers_json: str
    score: int
    total: int
    per_question_json: str
    submitted_at: str


def _get_connection() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec WAL mode pour la concurrence."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crée les tables si elles n'existent pas et migre les colonnes manquantes."""
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                session_id TEXT PRIMARY KEY,
                session_code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                quiz_json TEXT NOT NULL,
                notions_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS work_sessions (
                work_session_id TEXT PRIMARY KEY,
                work_code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                draft_quiz_json TEXT NOT NULL,
                draft_notions_json TEXT DEFAULT '[]',
                owner_name TEXT DEFAULT '',
                last_modified TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'draft'
            );
            CREATE TABLE IF NOT EXISTS participant_results (
                result_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                participant_name TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                per_question_json TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES quiz_sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_results_session ON participant_results(session_id);
        """)
        conn.commit()

        # Migrations backward-compatible (ignorées si la colonne existe déjà)
        for alter_sql in [
            "ALTER TABLE quiz_sessions ADD COLUMN pool_json TEXT DEFAULT NULL",
            "ALTER TABLE quiz_sessions ADD COLUMN subset_size INTEGER DEFAULT NULL",
            "ALTER TABLE quiz_sessions ADD COLUMN pass_threshold REAL DEFAULT 0.7",
            "ALTER TABLE participant_results ADD COLUMN attempt_number INTEGER DEFAULT 1",
            "ALTER TABLE participant_results ADD COLUMN seen_question_indices TEXT DEFAULT '[]'",
            "ALTER TABLE quiz_sessions ADD COLUMN exercises_json TEXT DEFAULT '[]'",
            "ALTER TABLE work_sessions ADD COLUMN draft_exercises_json TEXT DEFAULT '[]'",
        ]:
            try:
                conn.execute(alter_sql)
                conn.commit()
            except Exception:
                pass
    finally:
        conn.close()


def _generate_session_code(length: int = 6) -> str:
    """Génère un code de session court et unique."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def create_session(
    quiz_data: dict,
    notions_data: list,
    title: str,
    exercises_data: Optional[list] = None,
) -> QuizSession:
    """
    Crée une nouvelle session de quizz partagée.

    Args:
        quiz_data: Dict sérialisable du Quiz (questions, etc.)
        notions_data: Liste de dicts sérialisables des Notions
        title: Titre de la session
        exercises_data: Liste de dicts sérialisables des Exercices (optionnel)

    Returns:
        QuizSession créée
    """
    init_db()
    conn = _get_connection()
    try:
        session_id = str(uuid.uuid4())
        session_code = _generate_session_code()

        # S'assurer que le code est unique
        while conn.execute(
            "SELECT 1 FROM quiz_sessions WHERE session_code = ?", (session_code,)
        ).fetchone():
            session_code = _generate_session_code()

        created_at = datetime.now().isoformat()
        quiz_json = json.dumps(quiz_data, ensure_ascii=False)
        notions_json = json.dumps(notions_data, ensure_ascii=False)
        exercises_json = json.dumps(exercises_data or [], ensure_ascii=False)

        conn.execute(
            """INSERT INTO quiz_sessions
            (session_id, session_code, title, quiz_json, notions_json, created_at, is_active, exercises_json)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (session_id, session_code, title, quiz_json, notions_json, created_at, exercises_json),
        )
        conn.commit()

        return QuizSession(
            session_id=session_id,
            session_code=session_code,
            title=title,
            quiz_json=quiz_json,
            notions_json=notions_json,
            created_at=created_at,
            is_active=True,
            exercises_json=exercises_json,
        )
    finally:
        conn.close()


def get_session(session_code: str) -> Optional[QuizSession]:
    """Récupère une session par son code."""
    init_db()
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM quiz_sessions WHERE session_code = ?", (session_code,)
        ).fetchone()
        if not row:
            return None
        return QuizSession(
            session_id=row["session_id"],
            session_code=row["session_code"],
            title=row["title"],
            quiz_json=row["quiz_json"],
            notions_json=row["notions_json"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
            pool_json=row["pool_json"],
            subset_size=row["subset_size"],
            pass_threshold=row["pass_threshold"] if row["pass_threshold"] is not None else 0.7,
            exercises_json=row["exercises_json"] if "exercises_json" in row.keys() else "[]",
        )
    finally:
        conn.close()


def submit_result(
    session_code: str,
    participant_name: str,
    answers: Dict[str, List[str]],
    questions_override: Optional[List[dict]] = None,
) -> Optional[ParticipantResult]:
    """
    Soumet les réponses d'un participant et calcule le score côté serveur.

    Args:
        session_code: Code de la session
        participant_name: Nom du participant
        answers: Dict {question_index_str: [labels_selectionnés]}
        questions_override: Pour les sessions pool — liste des questions du sous-ensemble
            (avec _pool_index). Remplace quiz_json pour le scoring.

    Returns:
        ParticipantResult avec le score calculé, ou None si session invalide
    """
    session = get_session(session_code)
    if not session or not session.is_active:
        return None

    if questions_override is not None:
        questions = questions_override
    else:
        quiz_data = json.loads(session.quiz_json)
        questions = quiz_data.get("questions", [])

    # Calculer le score
    score = 0
    total = len(questions)
    per_question = {}
    seen_indices = []

    for i, q in enumerate(questions):
        correct = set(q.get("correct_answers", []))
        selected = set(answers.get(str(i), []))
        is_correct = correct == selected
        pool_idx = q.get("_pool_index")
        key = str(pool_idx) if pool_idx is not None else str(i)
        per_question[key] = is_correct
        if is_correct:
            score += 1
        if pool_idx is not None:
            seen_indices.append(pool_idx)

    # Sauvegarder
    conn = _get_connection()
    try:
        prev_count = conn.execute(
            "SELECT COUNT(*) FROM participant_results WHERE session_id = ? AND participant_name = ?",
            (session.session_id, participant_name),
        ).fetchone()[0]
        attempt_number = prev_count + 1

        result_id = str(uuid.uuid4())
        submitted_at = datetime.now().isoformat()

        conn.execute(
            """INSERT INTO participant_results
            (result_id, session_id, participant_name, answers_json, score, total, per_question_json,
             submitted_at, attempt_number, seen_question_indices)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result_id,
                session.session_id,
                participant_name,
                json.dumps(answers, ensure_ascii=False),
                score,
                total,
                json.dumps(per_question),
                submitted_at,
                attempt_number,
                json.dumps(seen_indices),
            ),
        )
        conn.commit()

        return ParticipantResult(
            result_id=result_id,
            session_id=session.session_id,
            participant_name=participant_name,
            answers_json=json.dumps(answers, ensure_ascii=False),
            score=score,
            total=total,
            per_question_json=json.dumps(per_question),
            submitted_at=submitted_at,
        )
    finally:
        conn.close()


def get_session_results(session_code: str) -> List[ParticipantResult]:
    """Récupère tous les résultats d'une session."""
    session = get_session(session_code)
    if not session:
        return []

    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM participant_results WHERE session_id = ? ORDER BY submitted_at",
            (session.session_id,),
        ).fetchall()
        return [
            ParticipantResult(
                result_id=r["result_id"],
                session_id=r["session_id"],
                participant_name=r["participant_name"],
                answers_json=r["answers_json"],
                score=r["score"],
                total=r["total"],
                per_question_json=r["per_question_json"],
                submitted_at=r["submitted_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()



def get_session_analytics(session_code: str) -> Optional[dict]:
    """
    Calcule les analytics complètes d'une session.

    Returns:
        Dict avec per_question, per_notion, participants, global_stats
    """
    session = get_session(session_code)
    if not session:
        return None

    results = get_session_results(session_code)
    # Pour les sessions pool, les questions sont dans pool_json
    if session.pool_json:
        questions = json.loads(session.pool_json)
    else:
        quiz_data = json.loads(session.quiz_json)
        questions = quiz_data.get("questions", [])

    if not results:
        return {
            "per_question": {},
            "per_notion": {},
            "participants": [],
            "global_stats": {
                "avg_score": 0,
                "median_score": 0,
                "num_participants": 0,
                "total_questions": len(questions),
            },
            "session": {"title": session.title, "code": session.session_code, "created_at": session.created_at, "is_active": session.is_active},
        }

    # Per-question success rate
    per_question = {}
    for i, q in enumerate(questions):
        correct_count = 0
        for r in results:
            per_q = json.loads(r.per_question_json)
            if per_q.get(str(i), False):
                correct_count += 1
        per_question[str(i)] = {
            "question_text": q.get("question", f"Question {i+1}"),
            "success_rate": correct_count / len(results) if results else 0,
            "total_attempts": len(results),
            "correct_count": correct_count,
            "difficulty_level": q.get("difficulty_level", "moyen"),
            "related_notions": q.get("related_notions", []),
        }

    # Per-notion success rate (agrégé depuis les questions)
    per_notion = {}
    for q_idx, q_stats in per_question.items():
        for notion_title in q_stats.get("related_notions", []):
            if notion_title not in per_notion:
                per_notion[notion_title] = {"success_rates": [], "question_count": 0}
            per_notion[notion_title]["success_rates"].append(q_stats["success_rate"])
            per_notion[notion_title]["question_count"] += 1

    for notion_title, data in per_notion.items():
        data["avg_success_rate"] = mean(data["success_rates"]) if data["success_rates"] else 0

    # Participants
    participants = []
    scores = []
    for r in results:
        pct = (r.score / r.total * 100) if r.total > 0 else 0
        participants.append({
            "name": r.participant_name,
            "score": r.score,
            "total": r.total,
            "percentage": round(pct, 1),
            "submitted_at": r.submitted_at,
        })
        scores.append(pct)

    # Global stats
    global_stats = {
        "avg_score": round(mean(scores), 1) if scores else 0,
        "median_score": round(median(scores), 1) if scores else 0,
        "num_participants": len(results),
        "total_questions": len(questions),
    }

    return {
        "per_question": per_question,
        "per_notion": per_notion,
        "participants": sorted(participants, key=lambda p: p["percentage"], reverse=True),
        "global_stats": global_stats,
        "session": {"title": session.title, "code": session.session_code, "created_at": session.created_at, "is_active": session.is_active},
    }


def deactivate_session(session_code: str) -> bool:
    """Désactive une session (plus de soumissions possibles)."""
    conn = _get_connection()
    try:
        result = conn.execute(
            "UPDATE quiz_sessions SET is_active = 0 WHERE session_code = ?",
            (session_code,),
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def list_sessions() -> List[QuizSession]:
    """Liste toutes les sessions créées."""
    init_db()
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM quiz_sessions ORDER BY created_at DESC"
        ).fetchall()
        return [
            QuizSession(
                session_id=r["session_id"],
                session_code=r["session_code"],
                title=r["title"],
                quiz_json=r["quiz_json"],
                notions_json=r["notions_json"],
                created_at=r["created_at"],
                is_active=bool(r["is_active"]),
                pool_json=r["pool_json"],
                subset_size=r["subset_size"],
                pass_threshold=r["pass_threshold"] if r["pass_threshold"] is not None else 0.7,
            )
            for r in rows
        ]
    finally:
        conn.close()


# ─── Pool de questions ────────────────────────────────────────────────────────

def create_pool_session(
    pool_quiz_data: dict,
    notions_data: list,
    title: str,
    subset_size: int,
    pass_threshold: float = 0.7,
) -> QuizSession:
    """
    Crée une session avec un pool de questions.
    Chaque participant voit un sous-ensemble de subset_size questions.

    Args:
        pool_quiz_data: Dict quiz complet (avec toutes les questions du pool)
        notions_data: Liste de notions sérialisables
        title: Titre de la session
        subset_size: Nombre de questions présentées à chaque participant
        pass_threshold: Score minimum (ratio 0–1) pour valider la session

    Returns:
        QuizSession créée
    """
    init_db()
    conn = _get_connection()
    try:
        session_id = str(uuid.uuid4())
        session_code = _generate_session_code()

        while conn.execute(
            "SELECT 1 FROM quiz_sessions WHERE session_code = ?", (session_code,)
        ).fetchone():
            session_code = _generate_session_code()

        created_at = datetime.now().isoformat()
        pool_json = json.dumps(pool_quiz_data.get("questions", []), ensure_ascii=False)
        # quiz_json contient les métadonnées (sans questions — elles viennent du pool)
        quiz_meta = {k: v for k, v in pool_quiz_data.items() if k != "questions"}
        quiz_meta["questions"] = []
        quiz_json = json.dumps(quiz_meta, ensure_ascii=False)
        notions_json = json.dumps(notions_data, ensure_ascii=False)

        conn.execute(
            """INSERT INTO quiz_sessions
            (session_id, session_code, title, quiz_json, notions_json, created_at, is_active,
             pool_json, subset_size, pass_threshold)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (session_id, session_code, title, quiz_json, notions_json, created_at,
             pool_json, subset_size, pass_threshold),
        )
        conn.commit()

        return QuizSession(
            session_id=session_id,
            session_code=session_code,
            title=title,
            quiz_json=quiz_json,
            notions_json=notions_json,
            created_at=created_at,
            is_active=True,
            pool_json=pool_json,
            subset_size=subset_size,
            pass_threshold=pass_threshold,
        )
    finally:
        conn.close()


def _sample_subset_by_difficulty(
    pool_questions: List[dict],
    subset_size: int,
    exclude_indices: set = None,
) -> List[tuple]:
    """
    Sélectionne subset_size questions du pool de façon proportionnelle par difficulté,
    en excluant les indices déjà vus.

    Returns:
        Liste de (pool_index, question_dict)
    """
    if exclude_indices is None:
        exclude_indices = set()

    available = [
        (i, q) for i, q in enumerate(pool_questions)
        if i not in exclude_indices
    ]

    if not available:
        # Toutes vues — réinitialiser depuis le pool complet
        available = list(enumerate(pool_questions))

    if len(available) <= subset_size:
        random.shuffle(available)
        return available

    # Regrouper par difficulté
    by_diff: Dict[str, List[tuple]] = {"facile": [], "moyen": [], "difficile": []}
    for i, q in available:
        diff = q.get("difficulty_level", "moyen")
        if diff not in by_diff:
            diff = "moyen"
        by_diff[diff].append((i, q))

    total_avail = len(available)
    result: List[tuple] = []
    remaining = subset_size

    for diff in ["facile", "moyen", "difficile"]:
        pool_diff = by_diff[diff]
        if not pool_diff or remaining <= 0:
            continue
        proportion = len(pool_diff) / total_avail
        count = max(1, round(proportion * subset_size))
        count = min(count, len(pool_diff), remaining)
        result.extend(random.sample(pool_diff, count))
        remaining -= count

    # Compléter si nécessaire
    if remaining > 0:
        already = {i for i, _ in result}
        leftover = [(i, q) for i, q in available if i not in already]
        if leftover:
            result.extend(random.sample(leftover, min(remaining, len(leftover))))

    random.shuffle(result)
    return result


def get_next_subset(session_code: str, participant_name: str) -> Optional[List[dict]]:
    """
    Retourne un sous-ensemble de questions non encore vues par ce participant.

    Les questions retournées ont un champ `_pool_index` indiquant leur position
    dans le pool global, utilisé pour le scoring côté serveur.

    Returns:
        Liste de question dicts avec _pool_index, ou None si pas une session pool.
    """
    session = get_session(session_code)
    if not session or not session.pool_json:
        return None

    pool_questions = json.loads(session.pool_json)
    subset_size = session.subset_size or len(pool_questions)

    # Collecter les indices déjà vus lors des passages précédents
    conn = _get_connection()
    try:
        rows = conn.execute(
            """SELECT seen_question_indices FROM participant_results
            WHERE session_id = ? AND participant_name = ?
            ORDER BY submitted_at""",
            (session.session_id, participant_name),
        ).fetchall()
    finally:
        conn.close()

    seen_indices: set = set()
    for row in rows:
        try:
            indices = json.loads(row["seen_question_indices"] or "[]")
            seen_indices.update(indices)
        except (json.JSONDecodeError, TypeError):
            pass

    subset = _sample_subset_by_difficulty(pool_questions, subset_size, seen_indices)

    result = []
    for pool_idx, q in subset:
        q_copy = dict(q)
        q_copy["_pool_index"] = pool_idx
        result.append(q_copy)

    return result


# ─── Ateliers formateurs (work sessions) ─────────────────────────────────────

def create_work_session(
    quiz_data: dict,
    notions_data: list,
    title: str,
    owner_name: str = "",
    exercises_data: Optional[list] = None,
) -> WorkSession:
    """
    Crée un atelier de travail collaboratif pour formateurs.

    Args:
        quiz_data: Dict quiz sérialisable (questions, etc.)
        notions_data: Liste de notions sérialisables
        title: Titre de l'atelier
        owner_name: Nom du créateur
        exercises_data: Liste de dicts sérialisables des Exercices (optionnel)

    Returns:
        WorkSession créée
    """
    init_db()
    conn = _get_connection()
    try:
        work_session_id = str(uuid.uuid4())
        work_code = _generate_session_code()

        while conn.execute(
            "SELECT 1 FROM work_sessions WHERE work_code = ?", (work_code,)
        ).fetchone():
            work_code = _generate_session_code()

        now = datetime.now().isoformat()
        draft_quiz_json = json.dumps(quiz_data, ensure_ascii=False)
        draft_notions_json = json.dumps(notions_data, ensure_ascii=False)
        draft_exercises_json = json.dumps(exercises_data or [], ensure_ascii=False)

        conn.execute(
            """INSERT INTO work_sessions
            (work_session_id, work_code, title, draft_quiz_json, draft_notions_json,
             owner_name, last_modified, created_at, status, draft_exercises_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
            (work_session_id, work_code, title, draft_quiz_json, draft_notions_json,
             owner_name, now, now, draft_exercises_json),
        )
        conn.commit()

        return WorkSession(
            work_session_id=work_session_id,
            work_code=work_code,
            title=title,
            draft_quiz_json=draft_quiz_json,
            draft_notions_json=draft_notions_json,
            owner_name=owner_name,
            last_modified=now,
            created_at=now,
            status="draft",
            draft_exercises_json=draft_exercises_json,
        )
    finally:
        conn.close()


def get_work_session(work_code: str) -> Optional[WorkSession]:
    """Récupère un atelier par son code."""
    init_db()
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE work_code = ?", (work_code,)
        ).fetchone()
        if not row:
            return None
        return WorkSession(
            work_session_id=row["work_session_id"],
            work_code=row["work_code"],
            title=row["title"],
            draft_quiz_json=row["draft_quiz_json"],
            draft_notions_json=row["draft_notions_json"],
            owner_name=row["owner_name"],
            last_modified=row["last_modified"],
            created_at=row["created_at"],
            status=row["status"],
            draft_exercises_json=row["draft_exercises_json"] if "draft_exercises_json" in row.keys() else "[]",
        )
    finally:
        conn.close()


def update_work_session_draft(
    work_code: str,
    quiz_data: dict,
    editor_name: str = "",
    notions_data: Optional[list] = None,
    exercises_data: Optional[list] = None,
) -> bool:
    """Sauvegarde le brouillon d'un atelier (dernier à sauvegarder gagne)."""
    conn = _get_connection()
    try:
        now = datetime.now().isoformat()
        draft_quiz_json = json.dumps(quiz_data, ensure_ascii=False)
        updates = {"draft_quiz_json": draft_quiz_json, "last_modified": now, "owner_name": editor_name}
        if notions_data is not None:
            updates["draft_notions_json"] = json.dumps(notions_data, ensure_ascii=False)
        if exercises_data is not None:
            updates["draft_exercises_json"] = json.dumps(exercises_data, ensure_ascii=False)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [work_code]
        result = conn.execute(
            f"UPDATE work_sessions SET {set_clause} WHERE work_code = ?", values
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def publish_work_session(
    work_code: str,
    session_title: Optional[str] = None,
) -> Optional[QuizSession]:
    """
    Publie un atelier en créant une session étudiante correspondante.

    Returns:
        QuizSession créée, ou None si l'atelier est introuvable.
    """
    ws = get_work_session(work_code)
    if not ws:
        return None

    quiz_data = json.loads(ws.draft_quiz_json)
    notions_data = json.loads(ws.draft_notions_json)
    exercises_data = json.loads(ws.draft_exercises_json) if ws.draft_exercises_json else []
    title = session_title or ws.title

    session = create_session(quiz_data, notions_data, title, exercises_data=exercises_data)

    # Marquer l'atelier comme publié
    conn = _get_connection()
    try:
        conn.execute(
            "UPDATE work_sessions SET status = 'published' WHERE work_code = ?", (work_code,)
        )
        conn.commit()
    finally:
        conn.close()

    return session


def list_work_sessions() -> List[WorkSession]:
    """Liste tous les ateliers formateurs."""
    init_db()
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM work_sessions ORDER BY last_modified DESC"
        ).fetchall()
        return [
            WorkSession(
                work_session_id=r["work_session_id"],
                work_code=r["work_code"],
                title=r["title"],
                draft_quiz_json=r["draft_quiz_json"],
                draft_notions_json=r["draft_notions_json"],
                owner_name=r["owner_name"],
                last_modified=r["last_modified"],
                created_at=r["created_at"],
                status=r["status"],
            )
            for r in rows
        ]
    finally:
        conn.close()
