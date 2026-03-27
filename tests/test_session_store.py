"""Tests pour sessions/session_store.py — CRUD SQLite."""

import json
import pytest
from sessions.session_store import (
    init_db,
    create_session,
    get_session,
    submit_result,
    get_session_analytics,
    list_sessions,
    deactivate_session,
    QuizSession,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base SQLite via fichier temporaire."""
    db_path = str(tmp_path / "test_sessions.db")
    monkeypatch.setattr("sessions.session_store.DB_PATH", db_path)
    init_db()
    return db_path


@pytest.fixture
def sample_quiz_data():
    """quiz_data est un dict (pas une liste)."""
    return {
        "questions": [
            {
                "question": "Q1?",
                "choices": {"A": "a", "B": "b"},
                "correct_answers": ["A"],
                "explanation": "Explication",
                "difficulty_level": "facile",
                "related_notions": ["Notion1"],
            }
        ]
    }


@pytest.fixture
def sample_notions():
    return [{"title": "Notion1", "description": "Description"}]


def _create(db, quiz_data, notions, title="Test Session", **kwargs):
    session = create_session(quiz_data, notions, title, **kwargs)
    return session.session_code


def test_create_and_get_session(db, sample_quiz_data, sample_notions):
    code = _create(db, sample_quiz_data, sample_notions)
    assert len(code) == 6
    session = get_session(code)
    assert session is not None
    assert session.title == "Test Session"
    assert session.is_active is True


def test_session_not_found(db):
    assert get_session("ZZZZZZ") is None


def test_submit_result(db, sample_quiz_data, sample_notions):
    code = _create(db, sample_quiz_data, sample_notions)
    submit_result(code, "Alice", {"0": ["A"]})
    analytics = get_session_analytics(code)
    assert analytics is not None
    assert analytics["global_stats"]["num_participants"] == 1


def test_multiple_participants(db, sample_quiz_data, sample_notions):
    code = _create(db, sample_quiz_data, sample_notions)
    submit_result(code, "Alice", {"0": ["A"]})
    submit_result(code, "Bob", {"0": ["B"]})
    analytics = get_session_analytics(code)
    assert analytics["global_stats"]["num_participants"] == 2


def test_list_sessions(db, sample_quiz_data, sample_notions):
    _create(db, sample_quiz_data, sample_notions, "S1")
    _create(db, sample_quiz_data, sample_notions, "S2")
    sessions = list_sessions()
    assert len(sessions) >= 2


def test_deactivate_session(db, sample_quiz_data, sample_notions):
    code = _create(db, sample_quiz_data, sample_notions)
    deactivate_session(code)
    session = get_session(code)
    assert session.is_active is False


def test_create_session_with_exercises(db, sample_quiz_data, sample_notions):
    exercises = [{"statement": "Test exercise", "expected_answer": "42"}]
    code = _create(db, sample_quiz_data, sample_notions, exercises_data=exercises)
    session = get_session(code)
    assert session is not None
    ex = json.loads(session.exercises_json)
    assert len(ex) == 1
