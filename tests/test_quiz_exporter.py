"""Tests pour export/quiz_exporter.py — HTML/CSV export."""

import pytest
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FakeQuestion:
    question: str = "Q1?"
    choices: Dict[str, str] = field(default_factory=lambda: {"A": "a", "B": "b"})
    correct_answers: List[str] = field(default_factory=lambda: ["A"])
    explanation: str = "Explication"
    difficulty_level: str = "facile"
    source_document: str = "doc.pdf"
    citation: str = ""
    source_pages: List[int] = field(default_factory=lambda: [1])
    related_notions: List[str] = field(default_factory=lambda: ["Notion1"])


@dataclass
class FakeQuiz:
    title: str = "Test Quiz"
    difficulty: str = "facile"
    questions: List[FakeQuestion] = field(default_factory=lambda: [FakeQuestion()])
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeExercise:
    statement: str = "Calculez 2+2"
    expected_answer: str = "4"
    steps: List[str] = field(default_factory=lambda: ["2+2=4"])
    correction: str = "Le résultat est 4."
    exercise_type: str = "calcul"
    difficulty_level: str = "facile"
    source_document: str = "doc.pdf"
    source_pages: List[int] = field(default_factory=lambda: [1])
    related_notions: List[str] = field(default_factory=lambda: ["Math"])
    blanks: list = field(default_factory=list)
    sub_questions: list = field(default_factory=list)
    verification_code: str = ""
    citation: str = ""
    verified: bool = True
    verification_output: str = ""


def test_export_quiz_html():
    from export.quiz_exporter import export_quiz_html
    quiz = FakeQuiz()
    html = export_quiz_html(quiz)
    assert "<html" in html.lower()
    assert "Q1?" in html


def test_export_quiz_csv():
    from export.quiz_exporter import export_quiz_csv
    quiz = FakeQuiz()
    csv_content = export_quiz_csv(quiz)
    assert "Q1?" in csv_content
    # CSV uses ; as separator
    assert ";" in csv_content


def test_export_exercises_html():
    from export.quiz_exporter import export_exercises_html
    exercises = [FakeExercise()]
    html = export_exercises_html(exercises)
    assert "<html" in html.lower()
    assert "Calculez 2+2" in html


def test_export_combined_html():
    from export.quiz_exporter import export_combined_html
    quiz = FakeQuiz()
    exercises = [FakeExercise()]
    html = export_combined_html(quiz, exercises)
    assert "<html" in html.lower()
    assert "Q1?" in html
    assert "Calculez 2+2" in html


def test_export_combined_csv():
    from export.quiz_exporter import export_combined_csv
    quiz = FakeQuiz()
    exercises = [FakeExercise()]
    csv_content = export_combined_csv(quiz, exercises)
    assert "QUIZ QCM" in csv_content
    assert "EXERCICES" in csv_content
    assert "Q1?" in csv_content
    assert "Calculez 2+2" in csv_content
