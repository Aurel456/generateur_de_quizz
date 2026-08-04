/** Client API du backend FastAPI. Tous les appels réseau passent par ce module. */
const API_BASE = (import.meta.env.VITE_APP_BACKEND_HOST ?? '').replace(/\/$/, '');

export interface Notion {
    title: string;
    description: string;
    source_document: string;
    source_pages: number[];
    enabled: boolean;
    category: string;
    question_count: number;
}

export interface DocumentStats {
    name: string;
    num_pages: number;
    total_tokens: number;
}

export interface UploadResponse {
    doc_id: string;
    num_chunks: number;
    total_tokens: number;
    documents: DocumentStats[];
    chunks_preview: { source_document: string; source_pages: number[]; text_preview: string }[];
    /** Sigles reconnus dès l'upload via le référentiel (sans appel LLM). */
    acronyms: Acronym[];
}

export interface QuizQuestion {
    question: string;
    choices: Record<string, string>;
    correct_answers: string[];
    explanation: string;
    source_pages: number[];
    difficulty_level: string;
    source_document: string;
    citation: string;
    related_notions: string[];
}

export type ExerciseType = 'calcul' | 'trou' | 'cas_pratique';

export interface Exercise {
    statement: string;
    expected_answer: string;
    steps: string[];
    correction: string;
    verified: boolean;
    verification_output: string;
    source_pages: number[];
    source_document: string;
    citation: string;
    difficulty_level: string;
    related_notions: string[];
    exercise_type: ExerciseType;
    blanks: { position?: number; answer?: string; context?: string }[];
    sub_questions: { question?: string; answer?: string }[];
    pedagogical_comment: string;
    [key: string]: unknown;
}

export interface GenerateExercisesPayload {
    doc_id: string;
    difficulty_counts: Record<string, number>;
    exercise_type: ExerciseType;
    persona: string;
    user_instructions: string;
    classify_instructions?: boolean;
    custom_exercise_prompts?: Record<string, string> | null;
    batch_mode: boolean;
    notion_mixing?: boolean;
    notions: Notion[];
    /** Glossaire injecté dans le prompt (sigles actifs uniquement). */
    acronyms: Acronym[];
}

export interface GenerateQuizPayload {
    doc_id: string;
    difficulty_counts: Record<string, number>;
    num_choices: number;
    num_correct: number;
    variable_correct: boolean;
    max_correct?: number | null;
    vrai_faux: boolean;
    humor: boolean;
    batch_mode: boolean;
    persona: string;
    user_instructions: string;
    classify_instructions?: boolean;
    difficulty_prompts?: Record<string, string> | null;
    notion_mixing?: boolean;
    notions: Notion[];
    acronyms: Acronym[];
}

export interface GenerateQuizFromKnowledgePayload {
    topic: string;
    additional_context: string;
    difficulty_counts: Record<string, number>;
    num_choices: number;
    num_correct: number;
    variable_correct: boolean;
    max_correct?: number | null;
    vrai_faux: boolean;
    batch_mode: boolean;
    notions: Notion[];
}

/** Résultat de la détection des notions : notions + sigles inconnus (même passe LLM). */
export interface DetectNotionsResult {
    notions: Notion[];
    acronyms: Acronym[];
    failed_chunks: number;
    total_chunks: number;
}

/** Prompts par défaut éditables par niveau (+ description des règles fixes). */
export interface PromptDefaults {
    quiz: Record<string, string>;
    exercises: Record<string, Record<string, string>>;
    fixed_rules: Record<string, string>;
}

export interface ParticipantQuestion {
    question: string;
    choices: Record<string, string>;
    difficulty_level: string;
    related_notions: string[];
}

export interface ParticipantSession {
    session_code: string;
    title: string;
    is_active: boolean;
    is_pool: boolean;
    questions: ParticipantQuestion[];
}

export interface PoolSubset {
    session_code: string;
    title: string;
    is_active: boolean;
    pass_threshold: number;
    pool_indices: number[];
    questions: ParticipantQuestion[];
}

export interface Correction {
    index: number;
    is_correct: boolean;
    correct_answers: string[];
    explanation: string;
    citation: string;
}

export interface SubmitResult {
    score: number;
    total: number;
    corrections: Correction[];
}

export interface AnalyticsData {
    global_stats: {
        avg_score: number;
        median_score: number;
        num_participants: number;
        total_questions: number;
    };
    per_question: Record<
        string,
        {
            question_text: string;
            success_rate: number;
            total_attempts: number;
            correct_count: number;
            difficulty_level: string;
            related_notions: string[];
        }
    >;
    per_notion: Record<string, { avg_success_rate: number; question_count: number }>;
    participants: { name: string; score: number; total: number; percentage: number }[];
    session: { title: string; code: string; created_at: string; is_active: boolean };
}

export interface Recommendations {
    weak_notions: { notion: string; success_rate: number; recommendation: string }[];
    problematic_questions: {
        question_index: number;
        text_preview: string;
        issue: string;
        suggestion: string;
    }[];
    student_patterns: { pattern: string; recommendation: string }[];
    global_recommendations: string[];
}

export interface Acronym {
    acronym: string;
    definition: string;
    all_definitions: string[];
    source_document: string;
    source_pages: number[];
    enabled: boolean;
    from_reference: boolean;
}

export interface VerificationResult {
    question_index: number;
    status: 'verified' | 'reformulated' | 'deleted' | string;
}

export interface WorkshopSummary {
    work_code: string;
    title: string;
    owner_name: string;
    status: string;
    last_modified: string;
}

export interface Workshop extends WorkshopSummary {
    questions: QuizQuestion[];
    exercises: Exercise[];
    notions: Notion[];
    acronyms: Acronym[];
}

export interface ChatResponse {
    chat_id: string;
    message: string;
    state: string;
    notions: Notion[];
    suggested_config: Record<string, unknown> | null;
}

export interface GlobalStats {
    total_questions: number;
    total_documents: number;
    total_tokens: number;
    total_sessions: number;
}

export interface ExportPayload {
    format: 'html' | 'csv' | 'moodle' | 'scenari';
    scope: 'quiz' | 'exercises' | 'combined';
    title: string;
    questions: QuizQuestion[];
    exercises: Exercise[];
    acronyms: Acronym[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
        let detail = `Erreur HTTP ${response.status}`;
        try {
            const body = await response.json();
            if (body?.detail) detail = body.detail;
        } catch {
            /* corps non-JSON */
        }
        throw new Error(detail);
    }
    return response.json() as Promise<T>;
}

// ── Tâches asynchrones (jobs) ────────────────────────────────────────────────
export interface JobStatus {
    job_id: string;
    kind: string;
    status: 'pending' | 'running' | 'done' | 'error' | string;
    current: number;
    total: number;
    message: string;
    items: Record<string, unknown>[];
    result: Record<string, unknown> | null;
    error: string;
}

/** Callback de progression : reçoit chaque instantané du job (barre + items au fil de l'eau). */
export type JobProgress = (status: JobStatus) => void;

const JOB_POLL_INTERVAL_MS = 700;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function jsonPost(path: string, body: unknown): Promise<{ job_id: string }> {
    return request(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
}

/**
 * Interroge `GET /jobs/{id}` jusqu'à `done`/`error`, en notifiant `onProgress` à chaque
 * instantané. Le polling est robuste derrière tout reverse-proxy. Utilisable seul pour
 * se rebrancher sur une tâche déjà lancée (rechargement de page en pleine génération).
 */
export async function followJob<T>(
    jobId: string,
    onProgress?: JobProgress,
    onStart?: (jobId: string) => void,
): Promise<T> {
    onStart?.(jobId);
    for (;;) {
        const status = await request<JobStatus>(`/jobs/${encodeURIComponent(jobId)}`);
        onProgress?.(status);
        if (status.status === 'done') {
            return (status.result ?? {}) as T;
        }
        if (status.status === 'error') {
            throw new Error(status.error || 'Échec de la tâche.');
        }
        await sleep(JOB_POLL_INTERVAL_MS);
    }
}

/** Lance une tâche asynchrone (`POST …-async` → job_id) puis suit sa progression. */
async function runJob<T>(
    submitPath: string,
    body: unknown,
    onProgress?: JobProgress,
    onStart?: (jobId: string) => void,
): Promise<T> {
    const { job_id } = await jsonPost(submitPath, body);
    return followJob<T>(job_id, onProgress, onStart);
}

export const api = {
    /**
     * Analyse des documents. Le traitement est toujours en **one-shot vision** : le
     * modèle à grand contexte voit les pages telles quelles (schémas, tableaux), et
     * le serveur découpe automatiquement au-delà de son budget de contexte.
     */
    uploadDocuments(files: File[]): Promise<UploadResponse> {
        const form = new FormData();
        files.forEach((file) => form.append('files', file));
        form.append('vision_mode', 'true');
        form.append('one_shot', 'true');
        return request<UploadResponse>('/documents', { method: 'POST', body: form });
    },

    detectNotions(
        docId: string,
        knownAcronyms: string[],
        onProgress?: JobProgress,
        onStart?: (jobId: string) => void,
    ): Promise<DetectNotionsResult> {
        return runJob(
            '/notions/detect-async',
            { doc_id: docId, known_acronyms: knownAcronyms },
            onProgress,
            onStart,
        );
    },

    generateQuiz(
        payload: GenerateQuizPayload,
        onProgress?: JobProgress,
        onStart?: (jobId: string) => void,
    ): Promise<{ title: string; difficulty: string; questions: QuizQuestion[] }> {
        return runJob('/quiz/generate-async', payload, onProgress, onStart);
    },

    generateQuizFromKnowledge(
        payload: GenerateQuizFromKnowledgePayload,
        onProgress?: JobProgress,
        onStart?: (jobId: string) => void,
    ): Promise<{ title: string; difficulty: string; questions: QuizQuestion[] }> {
        return runJob('/quiz/generate-from-knowledge-async', payload, onProgress, onStart);
    },

    getPromptDefaults(): Promise<PromptDefaults> {
        return request('/prompts/defaults');
    },

    improveQuestion(question: QuizQuestion, instruction: string): Promise<QuizQuestion> {
        return request('/quiz/improve-question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, instruction }),
        });
    },

    generateExercises(
        payload: GenerateExercisesPayload,
        onProgress?: JobProgress,
        onStart?: (jobId: string) => void,
    ): Promise<{ exercises: Exercise[] }> {
        return runJob('/exercises/generate-async', payload, onProgress, onStart);
    },

    improveExercise(exercise: Exercise, instruction: string): Promise<Exercise> {
        return request('/exercises/improve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ exercise, instruction }),
        });
    },

    createSession(
        title: string,
        questions: QuizQuestion[],
        notions: Notion[],
        exercises: Exercise[] = [],
        acronyms: Acronym[] = [],
    ): Promise<{ session_code: string; title: string }> {
        return request('/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, questions, notions, exercises, acronyms }),
        });
    },

    createPoolSession(body: {
        title: string;
        questions: QuizQuestion[];
        notions: Notion[];
        subset_size: number;
        pass_threshold: number;
        acronyms: Acronym[];
    }): Promise<{ session_code: string; title: string }> {
        return request('/sessions/create-pool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    deactivateSession(code: string): Promise<{ session_code: string; is_active: boolean }> {
        return request(`/sessions/${encodeURIComponent(code)}/deactivate`, { method: 'POST' });
    },

    getSession(code: string): Promise<ParticipantSession> {
        return request(`/sessions/${encodeURIComponent(code)}`);
    },

    getPoolSubset(code: string, participantName: string): Promise<PoolSubset> {
        const q = `participant_name=${encodeURIComponent(participantName)}`;
        return request(`/sessions/${encodeURIComponent(code)}/subset?${q}`);
    },

    submitAnswers(
        code: string,
        participantName: string,
        answers: Record<string, string[]>,
        poolIndices?: number[],
    ): Promise<SubmitResult> {
        const body: Record<string, unknown> = { participant_name: participantName, answers };
        if (poolIndices) body.pool_indices = poolIndices;
        return request(`/sessions/${encodeURIComponent(code)}/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    getAnalytics(code: string): Promise<AnalyticsData> {
        return request(`/sessions/${encodeURIComponent(code)}/analytics`);
    },

    getRecommendations(code: string): Promise<Recommendations> {
        return request(`/sessions/${encodeURIComponent(code)}/recommendations`, { method: 'POST' });
    },

    verifyQuiz(
        docId: string,
        questions: QuizQuestion[],
        onProgress?: JobProgress,
        onStart?: (jobId: string) => void,
    ): Promise<{ questions: QuizQuestion[]; results: VerificationResult[] }> {
        return runJob('/quiz/verify-async', { doc_id: docId, questions }, onProgress, onStart);
    },

    editNotions(notions: Notion[], instruction: string): Promise<{ notions: Notion[] }> {
        return request('/notions/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notions, instruction }),
        });
    },

    mergeNotions(notions: Notion[]): Promise<{ notions: Notion[]; summary: string }> {
        return request('/notions/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notions }),
        });
    },

    detectAcronyms(docId: string): Promise<{ acronyms: Acronym[] }> {
        return request('/acronyms/detect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_id: docId, use_llm: true }),
        });
    },

    editAcronyms(
        acronyms: Acronym[],
        instruction: string,
    ): Promise<{ acronyms: Acronym[]; summary: string }> {
        return request('/acronyms/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ acronyms, instruction }),
        });
    },

    async downloadExport(payload: ExportPayload): Promise<void> {
        const response = await fetch(`${API_BASE}/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(`Erreur export (${response.status})`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const ext = payload.format === 'moodle' ? 'xml' : payload.format === 'scenari' ? 'zip' : payload.format;
        const a = document.createElement('a');
        a.href = url;
        a.download = `${payload.scope}.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
    },

    // Ateliers
    listWorkshops(): Promise<WorkshopSummary[]> {
        return request('/workshops');
    },
    getWorkshop(code: string): Promise<Workshop> {
        return request(`/workshops/${encodeURIComponent(code)}`);
    },
    createWorkshop(body: {
        title: string;
        owner_name: string;
        questions: QuizQuestion[];
        exercises: Exercise[];
        notions: Notion[];
        acronyms: Acronym[];
    }): Promise<Workshop> {
        return request('/workshops', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },
    updateWorkshop(
        code: string,
        body: {
            editor_name: string;
            questions: QuizQuestion[];
            exercises: Exercise[];
            notions: Notion[];
        },
    ): Promise<Workshop> {
        return request(`/workshops/${encodeURIComponent(code)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },
    publishWorkshop(
        code: string,
        body: { session_title: string; pool_mode: boolean; subset_size: number | null },
    ): Promise<{ session_code: string; title: string }> {
        return request(`/workshops/${encodeURIComponent(code)}/publish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    // Mode libre (chat)
    chatStart(): Promise<ChatResponse> {
        return request('/chat/start', { method: 'POST' });
    },
    chatMessage(chatId: string, message: string): Promise<ChatResponse> {
        return request(`/chat/${encodeURIComponent(chatId)}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
    },
    chatGenerateQuiz(
        chatId: string,
        body: {
            difficulty_counts: Record<string, number>;
            num_choices: number;
            num_correct: number;
            vrai_faux?: boolean;
            variable_correct?: boolean;
            notions?: Notion[];
        },
    ): Promise<{ title: string; questions: QuizQuestion[] }> {
        return request(`/chat/${encodeURIComponent(chatId)}/generate-quiz`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    chatGenerateExercises(
        chatId: string,
        body: { difficulty_counts: Record<string, number>; batch_mode?: boolean; notions?: Notion[] },
    ): Promise<{ exercises: Exercise[] }> {
        return request(`/chat/${encodeURIComponent(chatId)}/generate-exercises`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    getGlobalStats(): Promise<GlobalStats> {
        return request('/stats/global');
    },

    // Assistant formateur (aide à l'usage)
    assistantChat(
        messages: { role: string; content: string }[],
    ): Promise<{ reply: string }> {
        return request('/assistant/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages }),
        });
    },
};
