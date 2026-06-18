import { defineStore } from 'pinia';
import {
    api,
    type Acronym,
    type Exercise,
    type ExerciseType,
    type GenerateQuizFromKnowledgePayload,
    type JobStatus,
    type Notion,
    type PromptDefaults,
    type QuizQuestion,
    type UploadResponse,
    type VerificationResult,
} from '@/services/api';

type Busy =
    | ''
    | 'upload'
    | 'notions'
    | 'acronyms'
    | 'quiz'
    | 'exercises'
    | 'verify'
    | 'session'
    | 'workshop';

/** Progression d'une tâche asynchrone longue (génération / vérification). */
interface Progress {
    active: boolean;
    kind: string;
    current: number;
    total: number;
    message: string;
    itemCount: number;
}

const EMPTY_PROGRESS: Progress = {
    active: false,
    kind: '',
    current: 0,
    total: 0,
    message: '',
    itemCount: 0,
};

/** Instantané pour l'historique des modifications (undo). */
interface Snapshot {
    questions: QuizQuestion[];
    exercises: Exercise[];
}

const MAX_HISTORY = 20;

const deepClone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

interface GenerationState {
    upload: UploadResponse | null;
    notions: Notion[];
    acronyms: Acronym[];
    questions: QuizQuestion[];
    exercises: Exercise[];
    verifyResults: VerificationResult[];
    quizTitle: string;
    busy: Busy;
    error: string;
    progress: Progress;
    promptDefaults: PromptDefaults | null;
    history: Snapshot[];
}

export const useGenerationStore = defineStore('generation', {
    state: (): GenerationState => ({
        upload: null,
        notions: [],
        acronyms: [],
        questions: [],
        exercises: [],
        verifyResults: [],
        quizTitle: '',
        busy: '',
        error: '',
        progress: { ...EMPTY_PROGRESS },
        promptDefaults: null,
        history: [],
    }),
    getters: {
        docId: (state) => state.upload?.doc_id ?? '',
        enabledNotions: (state) => state.notions.filter((n) => n.enabled),
        progressPercent: (state) =>
            state.progress.total > 0
                ? Math.min(100, Math.round((state.progress.current / state.progress.total) * 100))
                : 0,
        canUndo: (state) => state.history.length > 0,
        /** Nombre de questions rattachées à chaque notion (par titre). */
        notionQuestionCounts: (state): Record<string, number> => {
            const counts: Record<string, number> = {};
            for (const q of state.questions) {
                for (const title of q.related_notions ?? []) {
                    counts[title] = (counts[title] ?? 0) + 1;
                }
            }
            return counts;
        },
    },
    actions: {
        reset() {
            this.$reset();
        },

        async loadPromptDefaults() {
            if (this.promptDefaults) return;
            try {
                this.promptDefaults = await api.getPromptDefaults();
            } catch {
                /* non bloquant : l'édition des prompts restera indisponible */
            }
        },

        // ── Historique des modifications (undo) ──────────────────────────────
        /** Enregistre l'état courant (questions + exercices) avant une modification. */
        _pushHistory() {
            this.history.push({
                questions: deepClone(this.questions),
                exercises: deepClone(this.exercises),
            });
            if (this.history.length > MAX_HISTORY) this.history.shift();
        },

        undo() {
            const snap = this.history.pop();
            if (!snap) return;
            this.questions = snap.questions;
            this.exercises = snap.exercises;
        },

        _startProgress(kind: string) {
            this.progress = { ...EMPTY_PROGRESS, active: true, kind };
        },

        _endProgress() {
            this.progress = { ...EMPTY_PROGRESS };
        },

        /** Met à jour l'état de progression à partir d'un instantané de job. */
        _onProgress(status: JobStatus) {
            this.progress = {
                active: true,
                kind: status.kind || this.progress.kind,
                current: status.current,
                total: status.total,
                message: status.message,
                itemCount: status.items.length,
            };
        },

        async uploadDocuments(files: File[], visionMode = false) {
            this.busy = 'upload';
            this.error = '';
            try {
                this.upload = await api.uploadDocuments(files, visionMode);
                this.notions = [];
                this.acronyms = [];
                this.questions = [];
                this.exercises = [];
                this.verifyResults = [];
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’upload.';
            } finally {
                this.busy = '';
            }
        },

        async detectNotions() {
            if (!this.docId) return;
            this.busy = 'notions';
            this.error = '';
            this._startProgress('notions');
            try {
                const { notions } = await api.detectNotions(this.docId, (s) => this._onProgress(s));
                this.notions = notions;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la détection.';
            } finally {
                this.busy = '';
                this._endProgress();
            }
        },

        async generateQuiz(config: {
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
        }) {
            if (!this.docId) return;
            this.busy = 'quiz';
            this.error = '';
            this.questions = [];
            this.verifyResults = [];
            this._startProgress('quiz');
            try {
                const result = await api.generateQuiz(
                    { doc_id: this.docId, notions: this.notions, ...config },
                    (s) => {
                        this._onProgress(s);
                        // Affichage incrémental : les questions s'affichent au fil de l'eau.
                        this.questions = s.items as unknown as QuizQuestion[];
                    },
                );
                this.questions = result.questions; // liste finale (autoritaire)
                this.quizTitle = result.title;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
            }
        },

        /** Quiz à partir de la base de connaissance du LLM (sans document) — accumulation. */
        async generateQuizFromKnowledge(
            payload: Omit<GenerateQuizFromKnowledgePayload, 'notions'> & { notions?: Notion[] },
        ) {
            this.busy = 'quiz';
            this.error = '';
            if (this.questions.length) this._pushHistory();
            this._startProgress('quiz');
            const base = [...this.questions];
            try {
                const result = await api.generateQuizFromKnowledge(
                    { notions: this.enabledNotions, ...payload },
                    (s) => {
                        this._onProgress(s);
                        this.questions = [...base, ...(s.items as unknown as QuizQuestion[])];
                    },
                );
                this.questions = [...base, ...result.questions];
                if (!this.quizTitle) this.quizTitle = result.title;
            } catch (err) {
                this.questions = base;
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
            }
        },

        async detectAcronyms() {
            if (!this.docId) return;
            this.busy = 'acronyms';
            this.error = '';
            try {
                const { acronyms } = await api.detectAcronyms(this.docId);
                this.acronyms = acronyms;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la détection.';
            } finally {
                this.busy = '';
            }
        },

        async editNotions(instruction: string) {
            if (!instruction.trim()) return;
            this.busy = 'notions';
            this.error = '';
            try {
                const { notions } = await api.editNotions(this.notions, instruction);
                this.notions = notions;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’édition.';
            } finally {
                this.busy = '';
            }
        },

        async mergeNotions() {
            this.busy = 'notions';
            this.error = '';
            try {
                const { notions } = await api.mergeNotions(this.notions);
                this.notions = notions;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la fusion.';
            } finally {
                this.busy = '';
            }
        },

        toggleAllNotions(enabled: boolean) {
            this.notions.forEach((n) => (n.enabled = enabled));
        },

        async verifyQuiz() {
            if (!this.docId || !this.questions.length) return;
            this.busy = 'verify';
            this.error = '';
            this._pushHistory();
            this._startProgress('verify');
            try {
                const { questions, results } = await api.verifyQuiz(
                    this.docId,
                    this.questions,
                    (s) => this._onProgress(s),
                );
                this.questions = questions;
                this.verifyResults = results;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la vérification.';
            } finally {
                this.busy = '';
                this._endProgress();
            }
        },

        updateQuestion(index: number, question: QuizQuestion) {
            if (index >= 0 && index < this.questions.length) {
                this._pushHistory();
                this.questions[index] = question;
            }
        },

        deleteQuestion(index: number) {
            this._pushHistory();
            this.questions.splice(index, 1);
        },

        /** Ajoute une question vierge à éditer manuellement. */
        addQuestion() {
            this._pushHistory();
            this.questions.push({
                question: '',
                choices: { A: '', B: '', C: '', D: '' },
                correct_answers: [],
                explanation: '',
                source_pages: [],
                difficulty_level: 'moyen',
                source_document: '',
                citation: '',
                related_notions: [],
            });
        },

        async improveQuestion(index: number, instruction: string) {
            const current = this.questions[index];
            if (!current || !instruction.trim()) return;
            this.error = '';
            this._pushHistory();
            try {
                this.questions[index] = await api.improveQuestion(current, instruction);
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’amélioration.';
            }
        },

        async generateExercises(config: {
            difficulty_counts: Record<string, number>;
            exercise_type: ExerciseType;
            persona: string;
            user_instructions: string;
            batch_mode: boolean;
            classify_instructions?: boolean;
            custom_exercise_prompts?: Record<string, string> | null;
        }) {
            if (!this.docId) return;
            this.busy = 'exercises';
            this.error = '';
            this._startProgress('exercises');
            // Accumulation : les nouveaux exercices s'ajoutent aux précédents.
            const base = [...this.exercises];
            try {
                const { exercises } = await api.generateExercises(
                    { doc_id: this.docId, notions: this.notions, ...config },
                    (s) => {
                        this._onProgress(s);
                        // Affichage incrémental : exercices existants + ceux reçus au fil de l'eau.
                        this.exercises = [...base, ...(s.items as unknown as Exercise[])];
                    },
                );
                this.exercises = [...base, ...exercises]; // liste finale (autoritaire)
            } catch (err) {
                this.exercises = base; // restaure en cas d'échec
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
            }
        },

        updateExercise(index: number, exercise: Exercise) {
            if (index >= 0 && index < this.exercises.length) {
                this._pushHistory();
                this.exercises[index] = exercise;
            }
        },

        deleteExercise(index: number) {
            this._pushHistory();
            this.exercises.splice(index, 1);
        },

        /** Ajoute un exercice vierge du type donné à éditer manuellement. */
        addExercise(type: ExerciseType) {
            this._pushHistory();
            this.exercises.push({
                statement: '',
                expected_answer: '',
                steps: [],
                correction: '',
                verified: false,
                verification_output: '',
                source_pages: [],
                source_document: '',
                citation: '',
                difficulty_level: 'moyen',
                related_notions: [],
                exercise_type: type,
                blanks: type === 'trou' ? [{ position: 1, answer: '', context: '' }] : [],
                sub_questions: type === 'cas_pratique' ? [{ question: '', answer: '' }] : [],
                pedagogical_comment: '',
            });
        },

        async improveExercise(index: number, instruction: string) {
            const current = this.exercises[index];
            if (!current || !instruction.trim()) return;
            this.error = '';
            this._pushHistory();
            try {
                this.exercises[index] = await api.improveExercise(current, instruction);
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’amélioration.';
            }
        },

        async createSession(title: string): Promise<string> {
            this.busy = 'session';
            this.error = '';
            try {
                const { session_code } = await api.createSession(
                    title,
                    this.questions,
                    this.enabledNotions,
                );
                return session_code;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la création de session.';
                return '';
            } finally {
                this.busy = '';
            }
        },

        async exportFile(format: 'html' | 'csv' | 'moodle', scope: 'quiz' | 'exercises' | 'combined') {
            this.error = '';
            try {
                await api.downloadExport({
                    format,
                    scope,
                    title: this.quizTitle || 'Quiz',
                    questions: this.questions,
                    exercises: this.exercises,
                    acronyms: this.acronyms,
                });
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’export.';
            }
        },

        async createWorkshop(title: string, ownerName: string): Promise<string> {
            this.busy = 'workshop';
            this.error = '';
            try {
                const ws = await api.createWorkshop({
                    title,
                    owner_name: ownerName,
                    questions: this.questions,
                    exercises: this.exercises,
                    notions: this.enabledNotions,
                });
                return ws.work_code;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la création de l’atelier.';
                return '';
            } finally {
                this.busy = '';
            }
        },
    },
});
