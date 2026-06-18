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
    max_correct: int | None = None
    vrai_faux: bool = False
    humor: bool = False
    batch_mode: bool = False
    persona: str = ""
    user_instructions: str = ""
    # Si True, la consigne libre est classée (style vs périmètre) : la partie « périmètre »
    # filtre les chunks, la partie « style » est injectée dans le prompt de génération.
    classify_instructions: bool = False
    # Prompts éditables par niveau (facile/moyen/difficile). None → prompts par défaut.
    difficulty_prompts: dict[str, str] | None = None
    # Réglages avancés.
    enable_thinking: bool = True
    notion_mixing: bool = True
    notions: list[NotionDTO] = Field(default_factory=list)


# ── Quiz sans document (base de connaissance du LLM) ──────────────────────────
class GenerateQuizFromKnowledgeRequest(ApiModel):
    topic: str = Field(..., min_length=1, max_length=500)
    additional_context: str = ""
    difficulty_counts: dict[str, int] = Field(default_factory=lambda: {"moyen": 5})
    num_choices: int = Field(default=4, ge=2, le=6)
    num_correct: int = Field(default=1, ge=1)
    variable_correct: bool = False
    max_correct: int | None = None
    vrai_faux: bool = False
    batch_mode: bool = False
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
    classify_instructions: bool = False
    # Prompts éditables par niveau pour le type d'exercice choisi. None → défauts.
    custom_exercise_prompts: dict[str, str] | None = None
    enable_thinking: bool = True
    notion_mixing: bool = True
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
    exercises: list[ExerciseDTO] = Field(default_factory=list)


class CreatePoolSessionRequest(ApiModel):
    """Session « pool » : chaque participant reçoit un sous-ensemble aléatoire."""

    title: str = Field(..., min_length=1, max_length=200)
    questions: list[QuizQuestionDTO]
    notions: list[NotionDTO] = Field(default_factory=list)
    subset_size: int = Field(..., ge=1)
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


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
    is_pool: bool = False  # session pool : passer par GET /sessions/{code}/subset
    questions: list[ParticipantChoice]


class PoolSubsetResponse(ApiModel):
    """Sous-ensemble servi à un participant d'une session pool. `pool_indices` est
    renvoyé tel quel au submit pour reconstruire le corrigé côté serveur (stateless)."""

    session_code: str
    title: str
    is_active: bool
    pass_threshold: float = 0.7
    pool_indices: list[int]
    questions: list[ParticipantChoice]


class SubmitAnswersRequest(ApiModel):
    participant_name: str = Field(..., min_length=1, max_length=120)
    # {index_question (str): [labels sélectionnés]}
    answers: dict[str, list[str]]
    # Session pool : indices du sous-ensemble reçu (ordre = ordre des questions vues).
    pool_indices: list[int] | None = None


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


class EditAcronymsRequest(ApiModel):
    acronyms: list[AcronymDTO]
    instruction: str = Field(..., min_length=1, max_length=2_000)


class EditAcronymsResponse(ApiModel):
    acronyms: list[AcronymDTO]
    summary: str = ""


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
    # Notions éditées/validées dans le chat (remplacent celles de la session si fournies).
    notions: list[NotionDTO] = Field(default_factory=list)


class ChatGenerateExercisesRequest(ApiModel):
    difficulty_counts: dict[str, int] = Field(default_factory=lambda: {"moyen": 3})
    batch_mode: bool = False
    notions: list[NotionDTO] = Field(default_factory=list)


# ── Assistant formateur (chatbot d'aide à l'usage) ───────────────────────────
class AssistantMessage(ApiModel):
    role: str  # user | assistant
    content: str = Field(..., min_length=1, max_length=5_000)


class AssistantChatRequest(ApiModel):
    messages: list[AssistantMessage] = Field(..., min_length=1)


class AssistantChatResponse(ApiModel):
    reply: str


# ── Stats globales ───────────────────────────────────────────────────────────
class GlobalStats(ApiModel):
    total_questions: int = 0
    total_documents: int = 0
    total_tokens: int = 0
    total_sessions: int = 0


# ── Prompts éditables par niveau ─────────────────────────────────────────────
class PromptDefaultsResponse(ApiModel):
    """Prompts par défaut (règles éditables par niveau) côté quiz et exercices.

    Les *règles fixes* (structure JSON, contraintes de format) ne sont pas éditables :
    elles sont décrites en lecture seule dans `fixed_rules` à titre informatif.
    """

    quiz: dict[str, str]  # {facile, moyen, difficile}
    exercises: dict[str, dict[str, str]]  # {calcul: {…}, trou: {…}, cas_pratique: {…}}
    fixed_rules: dict[str, str] = Field(default_factory=dict)  # {quiz: "...", exercises: "..."}


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
