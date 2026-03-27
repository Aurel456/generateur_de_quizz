"""Tests pour core/models.py — Validation Pydantic."""

import pytest
from pydantic import ValidationError
from core.models import (
    QuizQuestionModel,
    ExerciseModel,
    NotionModel,
    validate_quiz_question,
    validate_exercise,
    validate_exercises_response,
)


class TestQuizQuestionModel:
    def test_valid_question(self, sample_quiz_question_data):
        model = QuizQuestionModel.model_validate(sample_quiz_question_data)
        assert model.question == "Quelle est la capitale de la France ?"
        assert model.correct_answers == ["A"]

    def test_correct_answers_not_in_choices(self):
        data = {
            "question": "Test",
            "choices": {"A": "a", "B": "b"},
            "correct_answers": ["C"],
            "explanation": "",
        }
        with pytest.raises(ValidationError, match="absents des choices"):
            QuizQuestionModel.model_validate(data)

    def test_empty_correct_answers(self):
        data = {
            "question": "Test",
            "choices": {"A": "a"},
            "correct_answers": [],
            "explanation": "",
        }
        with pytest.raises(ValidationError, match="ne peut pas être vide"):
            QuizQuestionModel.model_validate(data)

    def test_source_page_to_source_pages(self):
        data = {
            "question": "Test",
            "choices": {"A": "a"},
            "correct_answers": ["A"],
            "source_page": 5,
        }
        model = QuizQuestionModel.model_validate(data)
        assert model.source_pages == [5]

    def test_validate_quiz_question_helper(self, sample_quiz_question_data):
        result = validate_quiz_question(sample_quiz_question_data)
        assert "source_page" not in result
        assert result["question"] == "Quelle est la capitale de la France ?"


class TestExerciseModel:
    def test_valid_calcul(self, sample_exercise_data):
        model = ExerciseModel.model_validate(sample_exercise_data)
        assert model.statement == "Calculez 2 + 2"
        assert model.verification_code == "result = 2 + 2\nprint(result)"

    def test_valid_trou(self, sample_exercise_trou_data):
        model = ExerciseModel.model_validate(sample_exercise_trou_data)
        assert len(model.blanks) == 1
        assert model.blanks[0].answer == "Paris"

    def test_valid_cas_pratique(self, sample_exercise_cas_pratique_data):
        model = ExerciseModel.model_validate(sample_exercise_cas_pratique_data)
        assert len(model.sub_questions) == 2

    def test_validate_exercise_helper(self, sample_exercise_data):
        result = validate_exercise(sample_exercise_data)
        assert "source_page" not in result

    def test_validate_exercises_response(self, sample_exercise_data):
        data = {"exercises": [sample_exercise_data, sample_exercise_data]}
        results = validate_exercises_response(data)
        assert len(results) == 2


class TestNotionModel:
    def test_valid_notion(self):
        model = NotionModel.model_validate({
            "title": "Géographie",
            "description": "Étude des territoires",
        })
        assert model.title == "Géographie"

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError, match="ne peut pas être vide"):
            NotionModel.model_validate({"title": "  ", "description": "test"})
