"""
conftest.py — Fixtures partagées pour les tests.
"""

import sys
import os
import pytest

# Ajouter la racine du projet au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_quiz_question_data():
    """Données brutes d'une question quiz (comme retourné par le LLM)."""
    return {
        "question": "Quelle est la capitale de la France ?",
        "choices": {"A": "Paris", "B": "Lyon", "C": "Marseille", "D": "Toulouse"},
        "correct_answers": ["A"],
        "explanation": "Paris est la capitale de la France.",
        "source_pages": [1],
        "difficulty_level": "facile",
        "related_notions": ["Géographie"],
    }


@pytest.fixture
def sample_exercise_data():
    """Données brutes d'un exercice calcul."""
    return {
        "statement": "Calculez 2 + 2",
        "expected_answer": "4",
        "steps": ["2 + 2 = 4"],
        "correction": "Le résultat est 4.",
        "verification_code": "result = 2 + 2\nprint(result)",
        "source_pages": [1],
        "related_notions": ["Arithmétique"],
    }


@pytest.fixture
def sample_exercise_trou_data():
    """Données brutes d'un exercice à trou."""
    return {
        "statement": "La capitale de la France est _____.",
        "expected_answer": "",
        "blanks": [
            {"position": 1, "answer": "Paris", "context": "La capitale de la France est [BLANC]."}
        ],
        "correction": "Paris est la capitale de la France.",
        "source_pages": [1],
        "related_notions": ["Géographie"],
    }


@pytest.fixture
def sample_exercise_cas_pratique_data():
    """Données brutes d'un exercice cas pratique."""
    return {
        "statement": "Une entreprise réalise un CA de 100 000€.",
        "expected_answer": "",
        "sub_questions": [
            {"question": "Quel est le CA ?", "answer": "100 000€"},
            {"question": "Quel est le bénéfice si la marge est de 20% ?", "answer": "20 000€"},
        ],
        "correction": "CA = 100k, bénéfice = 20k",
        "verification_code": "result = 100000 * 0.2\nprint(result)",
        "source_pages": [2],
        "related_notions": ["Comptabilité"],
    }
