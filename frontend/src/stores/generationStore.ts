import { defineStore } from 'pinia';
import {
    api,
    type Acronym,
    type Exercise,
    type ExerciseType,
    type Notion,
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
    }),
    getters: {
        docId: (state) => state.upload?.doc_id ?? '',
        enabledNotions: (state) => state.notions.filter((n) => n.enabled),
    },
    actions: {
        reset() {
            this.$reset();
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
            try {
                const { notions } = await api.detectNotions(this.docId);
                this.notions = notions;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la détection.';
            } finally {
                this.busy = '';
            }
        },

        async generateQuiz(config: {
            difficulty_counts: Record<string, number>;
            num_choices: number;
            num_correct: number;
            variable_correct: boolean;
            vrai_faux: boolean;
            humor: boolean;
            batch_mode: boolean;
            persona: string;
            user_instructions: string;
        }) {
            if (!this.docId) return;
            this.busy = 'quiz';
            this.error = '';
            try {
                const result = await api.generateQuiz({
                    doc_id: this.docId,
                    notions: this.notions,
                    ...config,
                });
                this.questions = result.questions;
                this.quizTitle = result.title;
                this.verifyResults = [];
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
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
            try {
                const { questions, results } = await api.verifyQuiz(this.docId, this.questions);
                this.questions = questions;
                this.verifyResults = results;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la vérification.';
            } finally {
                this.busy = '';
            }
        },

        updateQuestion(index: number, question: QuizQuestion) {
            if (index >= 0 && index < this.questions.length) {
                this.questions[index] = question;
            }
        },

        deleteQuestion(index: number) {
            this.questions.splice(index, 1);
        },

        async improveQuestion(index: number, instruction: string) {
            const current = this.questions[index];
            if (!current || !instruction.trim()) return;
            this.error = '';
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
        }) {
            if (!this.docId) return;
            this.busy = 'exercises';
            this.error = '';
            try {
                const { exercises } = await api.generateExercises({
                    doc_id: this.docId,
                    notions: this.notions,
                    ...config,
                });
                // Accumulation : les nouveaux exercices s'ajoutent aux précédents.
                this.exercises.push(...exercises);
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
            }
        },

        updateExercise(index: number, exercise: Exercise) {
            if (index >= 0 && index < this.exercises.length) {
                this.exercises[index] = exercise;
            }
        },

        deleteExercise(index: number) {
            this.exercises.splice(index, 1);
        },

        async improveExercise(index: number, instruction: string) {
            const current = this.exercises[index];
            if (!current || !instruction.trim()) return;
            this.error = '';
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
