import { defineStore } from 'pinia';
import {
    api,
    followJob,
    type Acronym,
    type DetectNotionsResult,
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
import { loadState, saveState } from '@/services/persist';

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
    lastItemLabel: string; // aperçu du dernier item généré (style Streamlit)
}

const EMPTY_PROGRESS: Progress = {
    active: false,
    kind: '',
    current: 0,
    total: 0,
    message: '',
    itemCount: 0,
    lastItemLabel: '',
};

/** Clé de persistance de l'état de travail (cf. services/persist.ts). */
const STORAGE_KEY = 'quizz.generation.v1';

/**
 * Écritures regroupées : pendant une génération l'état change à chaque question
 * reçue, il serait inutile de sérialiser le quiz complet à chaque fois.
 */
const PERSIST_DEBOUNCE_MS = 400;

/** Tâche en cours au moment d'un rechargement : on s'y rebranche au retour. */
interface ActiveJob {
    kind: Busy;
    jobId: string;
}

let persistTimer: ReturnType<typeof setTimeout> | null = null;
/** La restauration n'a lieu qu'une fois par chargement de page. */
let restored = false;

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
    notice: string;
    progress: Progress;
    promptDefaults: PromptDefaults | null;
    history: Snapshot[];
    activeJob: ActiveJob | null;
}

/** Champs sauvegardés dans le navigateur (l'état volatil en est exclu). */
type PersistedState = Pick<
    GenerationState,
    | 'upload'
    | 'notions'
    | 'acronyms'
    | 'questions'
    | 'exercises'
    | 'verifyResults'
    | 'quizTitle'
    | 'activeJob'
>;

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
        notice: '',
        progress: { ...EMPTY_PROGRESS },
        promptDefaults: null,
        history: [],
        activeJob: null,
    }),
    getters: {
        docId: (state) => state.upload?.doc_id ?? '',
        enabledNotions: (state) => state.notions.filter((n) => n.enabled),
        enabledAcronyms: (state) => state.acronyms.filter((a) => a.enabled),
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
        /**
         * Notions regroupées par thématique. Chaque entrée porte l'index d'origine :
         * l'affichage groupé reste ainsi adressable sans recherche par identité
         * (fragile dès qu'une notion est éditée ou remplacée par l'IA).
         */
        notionsByCategory: (state): [string, { notion: Notion; index: number }[]][] => {
            const groups = new Map<string, { notion: Notion; index: number }[]>();
            state.notions.forEach((notion, index) => {
                const key = notion.category?.trim() || 'Sans catégorie';
                const group = groups.get(key) ?? [];
                group.push({ notion, index });
                groups.set(key, group);
            });
            // Catégories par ordre alphabétique, « Sans catégorie » en dernier.
            return [...groups.entries()].sort(([a], [b]) => {
                if (a === 'Sans catégorie') return 1;
                if (b === 'Sans catégorie') return -1;
                return a.localeCompare(b, 'fr');
            });
        },
        /** Catégories existantes, pour proposer des valeurs cohérentes à l'édition. */
        notionCategories: (state): string[] => {
            const seen = new Set<string>();
            for (const n of state.notions) {
                const key = n.category?.trim();
                if (key) seen.add(key);
            }
            return [...seen].sort((a, b) => a.localeCompare(b, 'fr'));
        },
    },
    actions: {
        reset() {
            this.$reset();
        },

        // ── Persistance locale (survie au rechargement de page) ──────────────
        /** Écrit l'état de travail dans le navigateur (regroupé, cf. PERSIST_DEBOUNCE_MS). */
        persist(immediate = false) {
            if (persistTimer !== null) clearTimeout(persistTimer);
            const write = () => {
                persistTimer = null;
                const {
                    upload,
                    notions,
                    acronyms,
                    questions,
                    exercises,
                    verifyResults,
                    quizTitle,
                    activeJob,
                } = this;
                saveState<PersistedState>(STORAGE_KEY, {
                    upload,
                    notions,
                    acronyms,
                    questions,
                    exercises,
                    verifyResults,
                    quizTitle,
                    activeJob,
                });
            };
            if (immediate) write();
            else persistTimer = setTimeout(write, PERSIST_DEBOUNCE_MS);
        },

        /**
         * Restaure l'état sauvegardé, branche la sauvegarde automatique, puis — si une
         * génération était en cours — se rebranche dessus (le job continue de tourner
         * côté serveur pendant le rechargement).
         */
        restore() {
            if (restored) return;
            restored = true;

            const saved = loadState<PersistedState>(STORAGE_KEY);
            if (saved) {
                this.upload = saved.upload ?? null;
                this.notions = saved.notions ?? [];
                this.acronyms = saved.acronyms ?? [];
                this.questions = saved.questions ?? [];
                this.exercises = saved.exercises ?? [];
                this.verifyResults = saved.verifyResults ?? [];
                this.quizTitle = saved.quizTitle ?? '';
                this.activeJob = saved.activeJob ?? null;
            }

            // Toute mutation ultérieure est sauvegardée automatiquement.
            this.$subscribe(() => this.persist(), { detached: true });
            // Le rechargement ne doit pas perdre une écriture encore en attente.
            window.addEventListener('pagehide', () => this.persist(true));

            // Sans `await` : une génération peut durer plusieurs minutes et ne doit pas
            // retarder le reste de l'initialisation de la page.
            if (this.activeJob) void this.resumeJob();
        },

        /** Mémorise la tâche en cours pour pouvoir la reprendre après rechargement. */
        _trackJob(kind: Busy, jobId: string) {
            this.activeJob = { kind, jobId };
            this.persist(true);
        },

        _untrackJob() {
            this.activeJob = null;
        },

        /** Reprend le suivi d'une génération lancée avant le rechargement. */
        async resumeJob() {
            const job = this.activeJob;
            if (!job) return;
            this.busy = job.kind;
            this.error = '';
            this._startProgress(job.kind);
            const base = job.kind === 'exercises' ? [...this.exercises] : [];
            try {
                const result = await followJob<Record<string, unknown>>(job.jobId, (s) => {
                    this._onProgress(s);
                    // Le mode batch ne diffuse pas d'items : ne rien écraser tant que la
                    // tâche n'a rien produit, l'état restauré reste affiché.
                    if (!s.items?.length) return;
                    if (job.kind === 'quiz') this.questions = s.items as unknown as QuizQuestion[];
                    if (job.kind === 'notions') this.notions = s.items as unknown as Notion[];
                    if (job.kind === 'exercises')
                        this.exercises = [...base, ...(s.items as unknown as Exercise[])];
                });
                this._applyJobResult(job.kind, result, base);
                this.notice = 'Génération reprise après rechargement de la page.';
            } catch (err) {
                // Un job inconnu (redémarrage du serveur) n'est pas une erreur bloquante :
                // l'état restauré reste exploitable.
                this.notice =
                    'La génération lancée avant le rechargement n’a pas pu être reprise ' +
                    `(${err instanceof Error ? err.message : 'tâche expirée'}).`;
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
            }
        },

        /** Applique le résultat final d'un job repris, selon sa nature. */
        _applyJobResult(kind: Busy, result: Record<string, unknown>, base: Exercise[]) {
            if (kind === 'quiz') {
                const quiz = result as unknown as { title: string; questions: QuizQuestion[] };
                if (quiz.questions) this.questions = quiz.questions;
                if (quiz.title) this.quizTitle = quiz.title;
            } else if (kind === 'notions') {
                this._applyDetection(result as unknown as DetectNotionsResult);
            } else if (kind === 'exercises') {
                const { exercises } = result as unknown as { exercises: Exercise[] };
                if (exercises) this.exercises = [...base, ...exercises];
            } else if (kind === 'verify') {
                const verified = result as unknown as {
                    questions: QuizQuestion[];
                    results: VerificationResult[];
                };
                if (verified.questions) this.questions = verified.questions;
                if (verified.results) this.verifyResults = verified.results;
            }
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
            const items = status.items ?? [];
            const last = items.length ? (items[items.length - 1] as Record<string, unknown>) : null;
            const label = last
                ? String(last.question ?? last.statement ?? last.title ?? '')
                : '';
            this.progress = {
                active: true,
                kind: status.kind || this.progress.kind,
                current: status.current,
                total: status.total,
                message: status.message,
                itemCount: items.length,
                lastItemLabel: label,
            };
        },

        async uploadDocuments(files: File[]) {
            this.busy = 'upload';
            this.error = '';
            this.notice = '';
            try {
                this.upload = await api.uploadDocuments(files);
                this.notions = [];
                // Sigles déjà reconnus par le référentiel dès l'analyse (sans LLM).
                this.acronyms = this.upload.acronyms ?? [];
                this.questions = [];
                this.exercises = [];
                this.verifyResults = [];
                this.history = [];
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’upload.';
            } finally {
                this.busy = '';
            }
        },

        /** Fusionne le résultat d'une détection : notions + sigles inconnus. */
        _applyDetection(result: DetectNotionsResult) {
            this.notions = result.notions ?? [];
            // Les sigles trouvés par le LLM complètent ceux du référentiel.
            const known = new Set(this.acronyms.map((a) => a.acronym));
            for (const acronym of result.acronyms ?? []) {
                if (!known.has(acronym.acronym)) {
                    known.add(acronym.acronym);
                    this.acronyms.push(acronym);
                }
            }
            if (result.failed_chunks) {
                this.notice =
                    `⚠️ ${result.failed_chunks} bloc(s) sur ${result.total_chunks} n’ont pas pu être ` +
                    'analysés (réponse du modèle illisible) : la liste peut être incomplète.';
            }
        },

        async detectNotions() {
            if (!this.docId) return;
            this.busy = 'notions';
            this.error = '';
            this.notice = '';
            this.notions = [];
            this._startProgress('notions');
            try {
                const result = await api.detectNotions(
                    this.docId,
                    this.acronyms.map((a) => a.acronym),
                    (s) => {
                        this._onProgress(s);
                        // Affichage au fil de l'eau : chaque notion apparaît dès sa détection.
                        this.notions = s.items as unknown as Notion[];
                    },
                    (jobId) => this._trackJob('notions', jobId),
                );
                this._applyDetection(result); // liste finale (autoritaire)
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la détection.';
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
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
            enable_thinking?: boolean;
            notion_mixing?: boolean;
        }) {
            if (!this.docId) return;
            this.busy = 'quiz';
            this.error = '';
            this.notice = '';
            this.questions = [];
            this.verifyResults = [];
            this._startProgress('quiz');
            try {
                const result = await api.generateQuiz(
                    {
                        doc_id: this.docId,
                        notions: this.notions,
                        acronyms: this.enabledAcronyms,
                        ...config,
                    },
                    (s) => {
                        this._onProgress(s);
                        // Affichage incrémental : les questions s'affichent au fil de l'eau.
                        this.questions = s.items as unknown as QuizQuestion[];
                    },
                    (jobId) => this._trackJob('quiz', jobId),
                );
                this.questions = result.questions; // liste finale (autoritaire)
                this.quizTitle = result.title;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
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
                    (jobId) => this._trackJob('quiz', jobId),
                );
                this.questions = [...base, ...result.questions];
                if (!this.quizTitle) this.quizTitle = result.title;
            } catch (err) {
                this.questions = base;
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
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

        /** Ajoute un acronyme vierge à éditer manuellement. */
        addAcronym() {
            this.acronyms.push({
                acronym: '',
                definition: '',
                all_definitions: [],
                source_document: '',
                source_pages: [],
                enabled: true,
                from_reference: false,
            });
        },

        deleteAcronym(index: number) {
            this.acronyms.splice(index, 1);
        },

        async editAcronyms(instruction: string) {
            if (!instruction.trim()) return;
            this.busy = 'acronyms';
            this.error = '';
            try {
                const { acronyms } = await api.editAcronyms(this.acronyms, instruction);
                this.acronyms = acronyms;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de l’édition.';
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

        /** Remplace une notion après édition manuelle (le brouillon est validé). */
        updateNotion(index: number, notion: Notion) {
            if (index >= 0 && index < this.notions.length) {
                this.notions[index] = notion;
            }
        },

        /** Ajoute une notion vierge à éditer manuellement. */
        addNotion() {
            this.notions.push({
                title: '',
                description: '',
                source_document: '',
                source_pages: [],
                enabled: true,
                category: '',
                question_count: 0,
            });
        },

        deleteNotion(index: number) {
            if (index >= 0 && index < this.notions.length) {
                this.notions.splice(index, 1);
            }
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
                    (jobId) => this._trackJob('verify', jobId),
                );
                this.questions = questions;
                this.verifyResults = results;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la vérification.';
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
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
            enable_thinking?: boolean;
            notion_mixing?: boolean;
        }) {
            if (!this.docId) return;
            this.busy = 'exercises';
            this.error = '';
            this.notice = '';
            this._startProgress('exercises');
            // Accumulation : les nouveaux exercices s'ajoutent aux précédents.
            const base = [...this.exercises];
            try {
                const { exercises } = await api.generateExercises(
                    {
                        doc_id: this.docId,
                        notions: this.notions,
                        acronyms: this.enabledAcronyms,
                        ...config,
                    },
                    (s) => {
                        this._onProgress(s);
                        // Affichage incrémental : exercices existants + ceux reçus au fil de l'eau.
                        this.exercises = [...base, ...(s.items as unknown as Exercise[])];
                    },
                    (jobId) => this._trackJob('exercises', jobId),
                );
                this.exercises = [...base, ...exercises]; // liste finale (autoritaire)
            } catch (err) {
                this.exercises = base; // restaure en cas d'échec
                this.error = err instanceof Error ? err.message : 'Échec de la génération.';
            } finally {
                this.busy = '';
                this._endProgress();
                this._untrackJob();
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
                    this.exercises,
                    this.enabledAcronyms,
                );
                return session_code;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la création de session.';
                return '';
            } finally {
                this.busy = '';
            }
        },

        /** Crée une session « pool » : sous-ensemble aléatoire par participant. */
        async createPoolSession(
            title: string,
            subsetSize: number,
            passThreshold: number,
        ): Promise<string> {
            this.busy = 'session';
            this.error = '';
            try {
                const { session_code } = await api.createPoolSession({
                    title,
                    questions: this.questions,
                    notions: this.enabledNotions,
                    subset_size: subsetSize,
                    pass_threshold: passThreshold,
                    acronyms: this.enabledAcronyms,
                });
                return session_code;
            } catch (err) {
                this.error = err instanceof Error ? err.message : 'Échec de la création de session pool.';
                return '';
            } finally {
                this.busy = '';
            }
        },

        async exportFile(format: 'html' | 'csv' | 'moodle' | 'scenari', scope: 'quiz' | 'exercises' | 'combined') {
            this.error = '';
            try {
                await api.downloadExport({
                    format,
                    scope,
                    title: this.quizTitle || 'Quiz',
                    questions: this.questions,
                    exercises: this.exercises,
                    // Glossaire des exports : seuls les sigles cochés.
                    acronyms: this.enabledAcronyms,
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
                    acronyms: this.acronyms,
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
