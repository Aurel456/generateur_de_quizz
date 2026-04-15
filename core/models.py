"""
models.py — Modèles Pydantic v2 pour la validation des données LLM.

Migration graduelle : ces modèles sont utilisés pour valider les réponses JSON
du LLM avant conversion vers les dataclasses existants via model_dump().
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator


# ── Quiz ─────────────────────────────────────────────────────────────────────

class QuizQuestionModel(BaseModel):
    """Validation d'une question de quizz QCM."""
    question: str
    choices: Dict[str, str]
    correct_answers: List[str]
    explanation: str = ""
    source_pages: List[int] = []
    source_page: Optional[int] = None  # Alias LLM (parfois retourné à la place de source_pages)
    difficulty_level: str = ""
    source_document: str = ""
    citation: str = ""
    related_notions: List[str] = []

    @field_validator("correct_answers")
    @classmethod
    def answers_must_be_in_choices(cls, v, info):
        choices = info.data.get("choices", {})
        if choices:
            invalid = [a for a in v if a not in choices]
            if invalid:
                raise ValueError(
                    f"correct_answers {invalid} absents des choices {list(choices.keys())}"
                )
        return v

    @field_validator("correct_answers")
    @classmethod
    def at_least_one_answer(cls, v):
        if not v:
            raise ValueError("correct_answers ne peut pas être vide")
        return v

    @model_validator(mode="after")
    def normalize_source_pages(self):
        """Convertit source_page (int) en source_pages (list) si nécessaire."""
        if self.source_page is not None and not self.source_pages:
            self.source_pages = [self.source_page]
        return self


class QuizModel(BaseModel):
    """Validation d'un quizz complet."""
    title: str = ""
    difficulty: str = ""
    questions: List[QuizQuestionModel] = []
    metadata: dict = {}


# ── Exercices ────────────────────────────────────────────────────────────────

class BlankModel(BaseModel):
    """Validation d'un blanc dans un exercice à trou."""
    position: int
    answer: str
    context: str = ""


class SubQuestionModel(BaseModel):
    """Validation d'une sous-question de cas pratique."""
    question: str
    answer: str


class SubPartModel(BaseModel):
    """Sous-partie d'un exercice multi-questions (calcul)."""
    question: str
    expected_answer: str = ""
    steps: List[str] = []
    verification_code: str = ""


class ExerciseModel(BaseModel):
    """Validation d'un exercice (tous types)."""
    statement: str
    expected_answer: str = ""
    steps: List[str] = []
    correction: str = ""
    verification_code: str = ""
    citation: str = ""
    source_page: Optional[int] = None
    source_pages: List[int] = []
    related_notions: List[str] = []
    # Type trou
    blanks: List[BlankModel] = []
    # Type cas pratique
    sub_questions: List[SubQuestionModel] = []
    # Multi-questions (calcul avec Q1, Q2...)
    sub_parts: List[SubPartModel] = []

    @model_validator(mode="after")
    def normalize_source_pages(self):
        if self.source_page is not None and not self.source_pages:
            self.source_pages = [self.source_page]
        return self


class ExerciseListModel(BaseModel):
    """Wrapper pour le format JSON retourné par le LLM."""
    exercises: List[ExerciseModel]


# ── Notions ──────────────────────────────────────────────────────────────────

class NotionModel(BaseModel):
    """Validation d'une notion fondamentale."""
    title: str
    description: str
    source_document: str = ""
    source_pages: List[int] = []
    enabled: bool = True
    category: str = ""
    question_count: int = 0

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Le titre de la notion ne peut pas être vide")
        return v.strip()


class NotionListModel(BaseModel):
    """Wrapper pour la réponse JSON du LLM contenant des notions."""
    notions: List[NotionModel]


# ── Acronymes ───────────────────────────────────────────────────────────────

class AcronymModel(BaseModel):
    """Validation d'un acronyme détecté."""
    acronym: str
    definition: str
    all_definitions: List[str] = []
    source_document: str = ""
    source_pages: List[int] = []
    enabled: bool = True
    from_reference: bool = True

    @field_validator("acronym")
    @classmethod
    def acronym_not_empty(cls, v):
        if not v.strip():
            raise ValueError("L'acronyme ne peut pas être vide")
        return v.strip()


class AcronymListModel(BaseModel):
    """Wrapper pour la réponse JSON du LLM contenant des acronymes."""
    acronyms: List[AcronymModel]


# ── Réponses LLM (wrappers pour streaming structured output) ────────────────

class QuizResponseModel(BaseModel):
    """Réponse LLM pour la génération de quiz."""
    questions: List[QuizQuestionModel]


class ExerciseResponseModel(BaseModel):
    """Réponse LLM pour la génération d'exercices."""
    exercises: List[ExerciseModel]


class NotionResponseModel(BaseModel):
    """Réponse LLM pour la détection de notions."""
    notions: List[NotionModel]


# ── TextChunk ────────────────────────────────────────────────────────────────

class TextChunkModel(BaseModel):
    """Validation d'un chunk de texte extrait."""
    text: str
    source_pages: List[int] = []
    token_count: int = 0
    source_document: str = ""
    page_images: List[str] = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def validate_quiz_question(data: dict) -> dict:
    """
    Valide un dict de question quiz et retourne un dict nettoyé.
    Lève ValidationError si invalide.
    """
    model = QuizQuestionModel.model_validate(data)
    result = model.model_dump(exclude={"source_page"})
    return result


def validate_exercise(data: dict) -> dict:
    """
    Valide un dict d'exercice et retourne un dict nettoyé.
    Lève ValidationError si invalide.
    """
    model = ExerciseModel.model_validate(data)
    result = model.model_dump(exclude={"source_page"})
    return result


def validate_exercises_response(data: dict) -> List[dict]:
    """
    Valide la réponse JSON complète du LLM pour les exercices.
    Retourne une liste de dicts nettoyés.
    """
    model = ExerciseListModel.model_validate(data)
    return [
        ex.model_dump(exclude={"source_page"})
        for ex in model.exercises
    ]
