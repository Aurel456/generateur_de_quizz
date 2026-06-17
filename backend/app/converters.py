"""Conversions entre les dataclasses métier existantes et des dicts JSON-sérialisables.

On s'appuie sur `dataclasses.asdict` pour rester robuste si les dataclasses évoluent,
et on filtre les champs lourds (images base64) hors des réponses API.
"""
from dataclasses import asdict, fields
from typing import Any

from generation.acronym_detector import Acronym
from generation.exercise_generator import Exercise
from generation.notion_detector import Notion
from generation.quiz_generator import Quiz, QuizQuestion
from processing.document_processor import TextChunk


def notion_to_dict(notion: Notion) -> dict[str, Any]:
    return asdict(notion)


def dict_to_notion(data: dict[str, Any]) -> Notion:
    allowed = {f.name for f in fields(Notion)}
    return Notion(**{k: v for k, v in data.items() if k in allowed})


def question_to_dict(question: QuizQuestion) -> dict[str, Any]:
    return asdict(question)


def dict_to_question(data: dict[str, Any]) -> QuizQuestion:
    allowed = {f.name for f in fields(QuizQuestion)}
    return QuizQuestion(**{k: v for k, v in data.items() if k in allowed})


def quiz_from_questions(questions: list[dict[str, Any]], title: str = "Quiz") -> Quiz:
    """Reconstruit un objet Quiz à partir de dicts de questions (DTO → métier)."""
    return Quiz(title=title, difficulty="mixte", questions=[dict_to_question(q) for q in questions])


def acronym_to_dict(acronym: Acronym) -> dict[str, Any]:
    return asdict(acronym)


def dict_to_acronym(data: dict[str, Any]) -> Acronym:
    allowed = {f.name for f in fields(Acronym)}
    return Acronym(**{k: v for k, v in data.items() if k in allowed})


def exercise_to_dict(exercise: Exercise) -> dict[str, Any]:
    return asdict(exercise)


def dict_to_exercise(data: dict[str, Any]) -> Exercise:
    allowed = {f.name for f in fields(Exercise)}
    return Exercise(**{k: v for k, v in data.items() if k in allowed})


def chunk_preview(chunk: TextChunk, max_chars: int = 280) -> dict[str, Any]:
    """Aperçu léger d'un chunk (sans les images base64)."""
    text = chunk.text or ""
    return {
        "source_document": chunk.source_document,
        "source_pages": chunk.source_pages,
        "token_count": chunk.token_count,
        "text_preview": text[:max_chars] + ("…" if len(text) > max_chars else ""),
    }
