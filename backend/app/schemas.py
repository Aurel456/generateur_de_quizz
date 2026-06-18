"""DTO Pydantic du backend (contrat d'API). Distincts des dataclasses métier."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


# ── Documents ────────────────────────────────────────────────────────────────
class DocumentStats(ApiModel):
    name: str
    num_pages: int = 0
    total_tokens: int = 0


class UploadResponse(ApiModel):
    doc_id: str
    num_chunks: int
    total_tokens: int
    documents: list[DocumentStats]
    chunks_preview: list[dict]


# ── Notions ──────────────────────────────────────────────────────────────────
class NotionDTO(ApiModel):
    title: str
    description: str = ""
    source_document: str = ""
    source_pages: list[int] = Field(default_factory=list)
    enabled: bool = True
    category: str = ""
    question_count: int = 0


class DetectNotionsRequest(ApiModel):
    doc_id: str


class DetectNotionsResponse(ApiModel):
    notions: list[NotionDTO]


# ── Quiz ─────────────────────────────────────────────────────────────────────
class GenerateQuizRequest(ApiModel):
    doc_id: str
    difficulty_counts: dict[str, int] = Field(default_factory=lambda: {"moyen": 5})
    num_choices: int = Field(default=4, ge=2, le=6)
    num_correct: int = Field(default=1, ge=1)
    variable_correct: bool = False
    vrai_faux: bool = False
    humor: bool = False
    batch_mode: bool = False
    persona: str = ""
    user_instructions: str = ""
    notions: list[NotionDTO] = Field(default_factory=list)


class QuizQuestionDTO(ApiModel):
    question: str
    choices: dict[str, str]
    correct_answers: list[str] = Field(default_factory=list)
    explanation: str = ""
    source_pages: list[int] = Field(default_factory=list)
    difficulty_level: str = ""
    source_document: str = ""
    citation: str = ""
    related_notions: list[str] = Field(default_factory=list)


class QuizResponse(ApiModel):
    title: str
    difficulty: str
    questions: list[QuizQuestionDTO]


class ImproveQuestionRequest(ApiModel):
    question: QuizQuestionDTO
    instruction: str = Field(..., min_length=1, max_length=2_000)


# ── Exercices ────────────────────────────────────────────────────────────────
class ExerciseDTO(ApiModel):
    statement: str
    expected_answer: str = ""
    steps: list[str] = Field(default_factory=list)
    num_steps: int = 0
    correction: str = ""
    verification_code: str = ""
    verified: bool = False
    verification_output: str = ""
    source_pages: list[int] = Field(default_factory=list)
    source_document: str = ""
    citation: str = ""
    difficulty_level: str = "moyen"
    related_notions: list[str] = Field(default_factory=list)
    exercise_type: str = "calcul"
    blanks: list[dict] = Field(default_factory=list)
    sub_questions: list[dict] = Field(default_factory=list)
    sub_parts: list[dict] = Field(default_factory=list)
    pedagogical_comment: str = ""


class GenerateExercisesRequest(ApiModel):
    doc_id: str
    difficulty_counts: dict[str, int] = Field(default_factory=lambda: {"moyen": 3})
    exercise_type: str = Field(default="calcul", pattern="^(calcul|trou|cas_pratique)$")
    batch_mode: bool = False
    persona: str = ""
    user_instructions: str = ""
    notions: list[NotionDTO] = Field(default_factory=list)


class ExercisesResponse(ApiModel):
    exercises: list[ExerciseDTO]


class ImproveExerciseRequest(ApiModel):
    exercise: ExerciseDTO
    instruction: str = Field(..., min_length=1, max_length=2_000)


# ── Sessions partagées (tranche participant) ─────────────────────────────────
class CreateSessionRequest(ApiModel):
    title: str = Field(..., min_length=1, max_length=200)
    questions: list[QuizQuestionDTO]
    notions: list[NotionDTO] = Field(default_factory=list)


class CreateSessionResponse(ApiModel):
    session_code: str
    title: str


class ParticipantChoice(ApiModel):
    """Question telle que vue par un participant : SANS les bonnes réponses."""

    question: str
    choices: dict[str, str]
    difficulty_level: str = ""
    related_notions: list[str] = Field(default_factory=list)


class ParticipantSessionResponse(ApiModel):
    session_code: str
    title: str
    is_active: bool
    questions: list[ParticipantChoice]


class SubmitAnswersRequest(ApiModel):
    participant_name: str = Field(..., min_length=1, max_length=120)
    # {index_question (str): [labels sélectionnés]}
    answers: dict[str, list[str]]


class QuestionCorrection(ApiModel):
    index: int
    is_correct: bool
    correct_answers: list[str]
    explanation: str = ""
    citation: str = ""


class SubmitAnswersResponse(ApiModel):
    score: int
    total: int
    corrections: list[QuestionCorrection]


# ── Vérification IA des QCM ──────────────────────────────────────────────────
class VerifyQuizRequest(ApiModel):
    doc_id: str
    questions: list[QuizQuestionDTO]


class VerificationResult(ApiModel):
    question_index: int
    status: str  # verified | reformulated | deleted


class VerifyQuizResponse(ApiModel):
    questions: list[QuizQuestionDTO]  # quiz nettoyé (questions supprimées retirées)
    results: list[VerificationResult]


# ── Notions avancées ─────────────────────────────────────────────────────────
class EditNotionsRequest(ApiModel):
    notions: list[NotionDTO]
    instruction: str = Field(..., min_length=1, max_length=2_000)


class MergeNotionsRequest(ApiModel):
    notions: list[NotionDTO]


class MergeNotionsResponse(ApiModel):
    notions: list[NotionDTO]
    summary: str = ""


# ── Acronymes ────────────────────────────────────────────────────────────────
class AcronymDTO(ApiModel):
    acronym: str
    definition: str = ""
    all_definitions: list[str] = Field(default_factory=list)
    source_document: str = ""
    source_pages: list[int] = Field(default_factory=list)
    enabled: bool = True
    from_reference: bool = True


class DetectAcronymsRequest(ApiModel):
    doc_id: str
    use_llm: bool = True


class DetectAcronymsResponse(ApiModel):
    acronyms: list[AcronymDTO]


# ── Exports ──────────────────────────────────────────────────────────────────
class ExportRequest(ApiModel):
    format: str = Field(..., pattern="^(html|csv|moodle)$")
    scope: str = Field(default="quiz", pattern="^(quiz|exercises|combined)$")
    title: str = "Quiz"
    questions: list[QuizQuestionDTO] = Field(default_factory=list)
    exercises: list[ExerciseDTO] = Field(default_factory=list)
    acronyms: list[AcronymDTO] = Field(default_factory=list)


# ── Ateliers formateurs (work sessions) ──────────────────────────────────────
class CreateWorkshopRequest(ApiModel):
    title: str = Field(..., min_length=1, max_length=200)
    owner_name: str = ""
    questions: list[QuizQuestionDTO] = Field(default_factory=list)
    exercises: list[ExerciseDTO] = Field(default_factory=list)
    notions: list[NotionDTO] = Field(default_factory=list)
    acronyms: list[AcronymDTO] = Field(default_factory=list)


class UpdateWorkshopRequest(ApiModel):
    editor_name: str = ""
    questions: list[QuizQuestionDTO] = Field(default_factory=list)
    exercises: list[ExerciseDTO] = Field(default_factory=list)
    notions: list[NotionDTO] = Field(default_factory=list)
    acronyms: list[AcronymDTO] = Field(default_factory=list)


class WorkshopResponse(ApiModel):
    work_code: str
    title: str
    owner_name: str = ""
    status: str = "draft"
    last_modified: str = ""
    questions: list[QuizQuestionDTO] = Field(default_factory=list)
    exercises: list[ExerciseDTO] = Field(default_factory=list)
    notions: list[NotionDTO] = Field(default_factory=list)


class WorkshopSummary(ApiModel):
    work_code: str
    title: str
    owner_name: str = ""
    status: str = "draft"
    last_modified: str = ""


class PublishWorkshopRequest(ApiModel):
    session_title: str = ""
    pool_mode: bool = False
    subset_size: int | None = None
    pass_threshold: float = 0.7


# ── Mode libre (chat) ────────────────────────────────────────────────────────
class ChatMessageRequest(ApiModel):
    message: str = Field(..., min_length=1, max_length=5_000)


class ChatResponse(ApiModel):
    chat_id: str
    message: str
    state: str
    notions: list[NotionDTO] = Field(default_factory=list)
    suggested_config: dict | None = None


class ChatGenerateRequest(ApiModel):
    difficulty_counts: dict[str, int] = Field(default_factory=lambda: {"moyen": 5})
    num_choices: int = Field(default=4, ge=2, le=6)
    num_correct: int = Field(default=1, ge=1)
    vrai_faux: bool = False
    variable_correct: bool = False


# ── Stats globales ───────────────────────────────────────────────────────────
class GlobalStats(ApiModel):
    total_questions: int = 0
    total_documents: int = 0
    total_tokens: int = 0
    total_sessions: int = 0


# ── Jobs asynchrones ─────────────────────────────────────────────────────────
class JobCreatedResponse(ApiModel):
    """Réponse immédiate d'un POST asynchrone : l'identifiant à interroger ensuite."""

    job_id: str


class JobStatusResponse(ApiModel):
    """Instantané d'une tâche : progression, items au fil de l'eau, résultat final."""

    job_id: str
    kind: str
    status: str  # pending | running | done | error
    current: int = 0
    total: int = 0
    message: str = ""
    items: list[dict] = Field(default_factory=list)  # items incrémentaux (questions, exercices…)
    result: dict | None = None  # payload final (présent quand status == done)
    error: str = ""
