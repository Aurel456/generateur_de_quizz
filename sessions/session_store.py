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
class QuizSession:
    session_id: str
    session_code: str
    title: str
    quiz_json: str
    notions_json: str
    created_at: str
    is_active: bool = True


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
    """Crée les tables si elles n'existent pas."""
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
    finally:
        conn.close()


def _generate_session_code(length: int = 6) -> str:
    """Génère un code de session court et unique."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def create_session(quiz_data: dict, notions_data: list, title: str) -> QuizSession:
    """
    Crée une nouvelle session de quizz partagée.

    Args:
        quiz_data: Dict sérialisable du Quiz (questions, etc.)
        notions_data: Liste de dicts sérialisables des Notions
        title: Titre de la session

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

        conn.execute(
            """INSERT INTO quiz_sessions
            (session_id, session_code, title, quiz_json, notions_json, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (session_id, session_code, title, quiz_json, notions_json, created_at),
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
        )
    finally:
        conn.close()


def submit_result(
    session_code: str,
    participant_name: str,
    answers: Dict[str, List[str]],
) -> Optional[ParticipantResult]:
    """
    Soumet les réponses d'un participant et calcule le score côté serveur.

    Args:
        session_code: Code de la session
        participant_name: Nom du participant
        answers: Dict {question_index_str: [labels_selectionnés]}

    Returns:
        ParticipantResult avec le score calculé, ou None si session invalide
    """
    session = get_session(session_code)
    if not session or not session.is_active:
        return None

    quiz_data = json.loads(session.quiz_json)
    questions = quiz_data.get("questions", [])

    # Calculer le score
    score = 0
    total = len(questions)
    per_question = {}

    for i, q in enumerate(questions):
        correct = set(q.get("correct_answers", []))
        selected = set(answers.get(str(i), []))
        is_correct = correct == selected
        per_question[str(i)] = is_correct
        if is_correct:
            score += 1

    # Sauvegarder
    conn = _get_connection()
    try:
        result_id = str(uuid.uuid4())
        submitted_at = datetime.now().isoformat()

        conn.execute(
            """INSERT INTO participant_results
            (result_id, session_id, participant_name, answers_json, score, total, per_question_json, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result_id,
                session.session_id,
                participant_name,
                json.dumps(answers, ensure_ascii=False),
                score,
                total,
                json.dumps(per_question),
                submitted_at,
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
            )
            for r in rows
        ]
    finally:
        conn.close()
