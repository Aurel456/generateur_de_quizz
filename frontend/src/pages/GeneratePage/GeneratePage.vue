<template>
    <h1>Générer un quiz</h1>

    <div v-if="store.error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ store.error }}</p>
    </div>

    <!-- Étape 1 : Document -->
    <section class="fr-mb-4w">
        <h2 class="fr-h4">1. Document(s) source</h2>
        <div class="fr-upload-group">
            <label class="fr-label" for="files">
                Fichiers
                <span class="fr-hint-text">PDF, DOCX, PPTX, ODT, TXT — plusieurs possibles.</span>
            </label>
            <input
                id="files"
                class="fr-upload"
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.odt,.odp,.ods,.txt"
                :disabled="store.busy === 'upload'"
                @change="onFilesChange"
            />
        </div>
        <div class="fr-checkbox-group fr-mt-1w">
            <input id="vision" type="checkbox" v-model="visionMode" :disabled="store.busy === 'upload'" />
            <label class="fr-label" for="vision">
                Mode Vision (PDF → images)
                <span class="fr-hint-text">Analyse les pages PDF en images (schémas, formules). Nécessite un modèle vision configuré.</span>
            </label>
        </div>
        <button
            class="fr-btn fr-mt-2w"
            :disabled="!selectedFiles.length || store.busy === 'upload'"
            @click="upload"
        >
            {{ store.busy === 'upload' ? 'Analyse…' : 'Analyser les documents' }}
        </button>

        <div v-if="store.upload" class="fr-mt-2w fr-text--sm">
            <p class="fr-mb-1v">
                <strong>{{ store.upload.num_chunks }}</strong> blocs •
                <strong>{{ store.upload.total_tokens }}</strong> tokens •
                {{ store.upload.documents.length }} document(s)
            </p>
            <ul class="fr-mb-0">
                <li v-for="doc in store.upload.documents" :key="doc.name">
                    {{ doc.name }} — {{ doc.total_tokens }} tokens
                </li>
            </ul>
        </div>
    </section>

    <!-- Étape 2 : Notions -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">2. Notions fondamentales</h2>
        <button
            class="fr-btn fr-btn--secondary"
            :disabled="store.busy === 'notions'"
            @click="store.detectNotions()"
        >
            {{ store.busy === 'notions' ? 'Détection…' : 'Détecter les notions' }}
        </button>
        <GenerationProgress kind="notions" />

        <div v-if="store.notions.length" class="fr-mt-2w">
            <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
                <p class="fr-col fr-text--sm fr-mb-0">
                    {{ store.enabledNotions.length }} / {{ store.notions.length }} notions activées
                </p>
                <div class="fr-col-auto">
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.toggleAllNotions(true)"
                    >
                        ✓ Tout cocher
                    </button>
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.toggleAllNotions(false)"
                    >
                        ✗ Tout décocher
                    </button>
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.mergeNotions()"
                    >
                        🔗 Regrouper
                    </button>
                </div>
            </div>
            <div class="fr-fieldset__content">
                <div
                    v-for="(notion, i) in store.notions"
                    :key="i"
                    class="fr-checkbox-group fr-checkbox-group--sm"
                >
                    <input :id="`notion-${i}`" type="checkbox" v-model="notion.enabled" />
                    <label class="fr-label" :for="`notion-${i}`">
                        <strong>{{ notion.title }}</strong>
                        <span v-if="notion.category" class="fr-badge fr-badge--sm fr-ml-1v">
                            {{ notion.category }}
                        </span>
                        <span class="fr-hint-text">{{ notion.description }}</span>
                    </label>
                </div>
            </div>

            <div class="fr-input-group fr-mt-2w">
                <label class="fr-label fr-text--sm" for="notion-edit">💬 Modifier les notions avec l'IA</label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input
                            id="notion-edit"
                            class="fr-input"
                            v-model="notionInstruction"
                            placeholder="Ex : ajoute une notion sur les dérivées partielles"
                            :disabled="store.busy === 'notions'"
                            @keyup.enter="editNotions"
                        />
                    </div>
                    <div class="fr-col-auto">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="store.busy === 'notions' || !notionInstruction.trim()"
                            @click="editNotions"
                        >
                            Appliquer
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Étape 2 bis : Acronymes -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">2 bis. Acronymes</h2>
        <button
            class="fr-btn fr-btn--secondary"
            :disabled="store.busy === 'acronyms'"
            @click="store.detectAcronyms()"
        >
            {{ store.busy === 'acronyms' ? 'Détection…' : 'Détecter les acronymes' }}
        </button>
        <ul v-if="store.acronyms.length" class="fr-mt-2w fr-text--sm">
            <li v-for="(a, i) in store.acronyms" :key="i">
                <strong>{{ a.acronym }}</strong> — {{ a.definition }}
            </li>
        </ul>
    </section>

    <!-- Étape 3 : Configuration -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">3. Configuration</h2>
        <div class="fr-grid-row fr-grid-row--gutters">
            <div class="fr-col-6 fr-col-md-3" v-for="level in levels" :key="level.key">
                <label class="fr-label" :for="`count-${level.key}`">{{ level.label }}</label>
                <input
                    :id="`count-${level.key}`"
                    class="fr-input"
                    type="number"
                    min="0"
                    max="50"
                    v-model.number="counts[level.key]"
                />
            </div>
        </div>

        <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
            <div class="fr-col-6 fr-col-md-3">
                <label class="fr-label" for="num-choices">Choix par question</label>
                <input
                    id="num-choices"
                    class="fr-input"
                    type="number"
                    min="2"
                    max="6"
                    v-model.number="config.num_choices"
                />
            </div>
            <div class="fr-col-6 fr-col-md-3">
                <label class="fr-label" for="num-correct">Bonnes réponses</label>
                <input
                    id="num-correct"
                    class="fr-input"
                    type="number"
                    min="1"
                    :max="config.num_choices - 1"
                    :disabled="config.variable_correct || config.vrai_faux"
                    v-model.number="config.num_correct"
                />
            </div>
        </div>

        <div class="fr-mt-2w">
            <div class="fr-checkbox-group">
                <input id="variable" type="checkbox" v-model="config.variable_correct" />
                <label class="fr-label" for="variable">Nombre de bonnes réponses variable</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="vraifaux" type="checkbox" v-model="config.vrai_faux" />
                <label class="fr-label" for="vraifaux">Mode Vrai / Faux</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="humor" type="checkbox" v-model="config.humor" />
                <label class="fr-label" for="humor">Touche d'humour</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="batch" type="checkbox" v-model="config.batch_mode" />
                <label class="fr-label" for="batch">
                    Traitement par lots (Batch API)
                    <span class="fr-hint-text">Plus rapide si le serveur supporte /v1/batches.</span>
                </label>
            </div>
        </div>

        <div class="fr-input-group fr-mt-2w">
            <label class="fr-label" for="persona">
                Persona expert <span class="fr-hint-text">(optionnel)</span>
            </label>
            <input
                id="persona"
                class="fr-input"
                v-model="config.persona"
                placeholder="Ex : Tu es un expert en droit fiscal."
            />
        </div>
        <div class="fr-input-group">
            <label class="fr-label" for="instructions">
                Consignes libres <span class="fr-hint-text">(optionnel)</span>
            </label>
            <textarea id="instructions" class="fr-input" rows="3" v-model="config.user_instructions" />
        </div>

        <button
            class="fr-btn fr-mt-2w"
            :disabled="store.busy === 'quiz' || totalQuestions === 0"
            @click="generate"
        >
            {{ store.busy === 'quiz' ? 'Génération en cours…' : `Générer ${totalQuestions} question(s)` }}
        </button>
        <GenerationProgress kind="quiz" />
        <p v-if="store.busy === 'quiz' && !store.progress.total" class="fr-text--sm fr-mt-1v">
            La génération peut prendre plusieurs minutes selon le volume.
        </p>
    </section>

    <!-- Étape 4 : Résultats -->
    <section v-if="store.questions.length" class="fr-mb-4w">
        <h2 class="fr-h4">4. Quiz généré ({{ store.questions.length }} questions)</h2>

        <div class="fr-grid-row fr-grid-row--middle fr-mb-2w">
            <div class="fr-col">
                <button
                    class="fr-btn fr-btn--secondary"
                    :disabled="store.busy === 'verify'"
                    @click="store.verifyQuiz()"
                >
                    {{ store.busy === 'verify' ? 'Vérification…' : '🔍 Vérifier les réponses (IA)' }}
                </button>
            </div>
        </div>
        <GenerationProgress kind="verify" />
        <div v-if="store.verifyResults.length" class="fr-alert fr-alert--info fr-mb-2w">
            <p class="fr-mb-0">
                Vérification : {{ verifySummary.verified }} validée(s),
                {{ verifySummary.reformulated }} reformulée(s),
                {{ verifySummary.deleted }} supprimée(s).
            </p>
        </div>

        <QuestionCard
            v-for="(q, qi) in store.questions"
            :key="qi"
            :question="q"
            :index="qi"
        />

        <!-- Exports -->
        <div class="fr-p-3w session-box fr-mb-3w">
            <h3 class="fr-h6">Exporter</h3>
            <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('html', 'quiz')">
                    Quiz HTML
                </button>
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('csv', 'quiz')">
                    Quiz CSV
                </button>
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('moodle', 'quiz')">
                    Quiz Moodle XML
                </button>
                <button
                    v-if="store.exercises.length"
                    class="fr-btn fr-btn--tertiary"
                    @click="store.exportFile('html', 'combined')"
                >
                    Quiz + Exercices HTML
                </button>
            </div>
        </div>

        <!-- Création de session partagée -->
        <div class="fr-p-3w session-box">
            <h3 class="fr-h6">Partager en session</h3>
            <div class="fr-input-group">
                <label class="fr-label" for="session-title">Titre de la session</label>
                <input id="session-title" class="fr-input" v-model="sessionTitle" />
            </div>
            <button
                class="fr-btn fr-mt-1w"
                :disabled="store.busy === 'session' || !sessionTitle.trim()"
                @click="createSession"
            >
                {{ store.busy === 'session' ? 'Création…' : 'Créer la session' }}
            </button>

            <div v-if="sessionCode" class="fr-alert fr-alert--success fr-mt-2w">
                <p>
                    Session créée — code <strong>{{ sessionCode }}</strong>.
                    <RouterLink :to="{ name: 'ParticipantPage', query: { code: sessionCode } }">
                        Page participant
                    </RouterLink>
                    ·
                    <RouterLink :to="{ name: 'AnalyticsPage', query: { code: sessionCode } }">
                        Analytics
                    </RouterLink>
                </p>
            </div>

            <hr class="fr-mt-2w fr-mb-2w" />
            <h3 class="fr-h6">Ou exporter vers un atelier formateur</h3>
            <button
                class="fr-btn fr-btn--secondary"
                :disabled="store.busy === 'workshop' || !sessionTitle.trim()"
                @click="createWorkshop"
            >
                {{ store.busy === 'workshop' ? 'Création…' : 'Créer un atelier' }}
            </button>
            <div v-if="workshopCode" class="fr-alert fr-alert--success fr-mt-2w">
                <p>
                    Atelier créé — code <strong>{{ workshopCode }}</strong>.
                    <RouterLink :to="{ name: 'WorkshopPage', query: { code: workshopCode } }">
                        Ouvrir l'atelier
                    </RouterLink>
                </p>
            </div>
        </div>
    </section>

    <!-- Étape 5 : Exercices -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">5. Exercices</h2>
        <div class="fr-grid-row fr-grid-row--gutters">
            <div class="fr-col-12 fr-col-md-4">
                <label class="fr-label" for="ex-type">Type</label>
                <select id="ex-type" class="fr-select" v-model="exConfig.exercise_type">
                    <option value="calcul">Calcul numérique</option>
                    <option value="trou">Texte à trou</option>
                    <option value="cas_pratique">Cas pratique</option>
                </select>
            </div>
            <div class="fr-col-4 fr-col-md-2" v-for="level in levels" :key="`ex-${level.key}`">
                <label class="fr-label" :for="`ex-count-${level.key}`">{{ level.label }}</label>
                <input
                    :id="`ex-count-${level.key}`"
                    class="fr-input"
                    type="number"
                    min="0"
                    max="20"
                    v-model.number="exCounts[level.key]"
                />
            </div>
        </div>

        <div class="fr-input-group fr-mt-2w">
            <label class="fr-label" for="ex-persona">
                Persona expert <span class="fr-hint-text">(optionnel)</span>
            </label>
            <input id="ex-persona" class="fr-input" v-model="exConfig.persona" />
        </div>
        <div class="fr-input-group">
            <label class="fr-label" for="ex-instructions">
                Consignes libres <span class="fr-hint-text">(optionnel)</span>
            </label>
            <textarea
                id="ex-instructions"
                class="fr-input"
                rows="2"
                v-model="exConfig.user_instructions"
            />
        </div>
        <div class="fr-checkbox-group">
            <input id="ex-batch" type="checkbox" v-model="exConfig.batch_mode" />
            <label class="fr-label" for="ex-batch">Traitement par lots (Batch API)</label>
        </div>

        <button
            class="fr-btn fr-mt-1w"
            :disabled="store.busy === 'exercises' || totalExercises === 0"
            @click="generateExercises"
        >
            {{ store.busy === 'exercises' ? 'Génération…' : `Générer ${totalExercises} exercice(s)` }}
        </button>
        <GenerationProgress kind="exercises" />
        <p v-if="exConfig.exercise_type === 'calcul'" class="fr-text--sm fr-mt-1v">
            ⚠️ Les exercices de calcul sont auto-vérifiés par exécution Python côté serveur
            (sandbox).
        </p>

        <div v-if="store.exercises.length" class="fr-mt-3w">
            <h3 class="fr-h6">{{ store.exercises.length }} exercice(s)</h3>
            <ExerciseCard
                v-for="(ex, ei) in store.exercises"
                :key="ei"
                :exercise="ex"
                :index="ei"
            />
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import type { ExerciseType } from '@/services/api';
import { useGenerationStore } from '@/stores/generationStore';
import QuestionCard from '@/components/QuestionCard.vue';
import ExerciseCard from '@/components/ExerciseCard.vue';
import GenerationProgress from '@/components/GenerationProgress.vue';

defineOptions({ name: 'GeneratePage' });

const store = useGenerationStore();

const levels = [
    { key: 'facile', label: '🟢 Facile' },
    { key: 'moyen', label: '🟡 Moyen' },
    { key: 'difficile', label: '🔴 Difficile' },
] as const;

const selectedFiles = ref<File[]>([]);
const visionMode = ref(false);
const notionInstruction = ref('');
const counts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });
const config = reactive({
    num_choices: 4,
    num_correct: 1,
    variable_correct: false,
    vrai_faux: false,
    humor: false,
    batch_mode: false,
    persona: '',
    user_instructions: '',
});
const sessionTitle = ref('');
const sessionCode = ref('');
const workshopCode = ref('');

const exCounts = reactive<Record<string, number>>({ facile: 0, moyen: 2, difficile: 0 });
const exConfig = reactive({
    exercise_type: 'calcul' as ExerciseType,
    persona: '',
    user_instructions: '',
    batch_mode: false,
});

const totalQuestions = computed(() =>
    Object.values(counts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

const totalExercises = computed(() =>
    Object.values(exCounts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

const verifySummary = computed(() => ({
    verified: store.verifyResults.filter((r) => r.status === 'verified').length,
    reformulated: store.verifyResults.filter((r) => r.status === 'reformulated').length,
    deleted: store.verifyResults.filter((r) => r.status === 'deleted').length,
}));

function onFilesChange(event: Event) {
    const input = event.target as HTMLInputElement;
    selectedFiles.value = input.files ? Array.from(input.files) : [];
}

function upload() {
    store.uploadDocuments(selectedFiles.value, visionMode.value);
}

function generate() {
    sessionCode.value = '';
    store.generateQuiz({ difficulty_counts: { ...counts }, ...config });
}

function generateExercises() {
    store.generateExercises({ difficulty_counts: { ...exCounts }, ...exConfig });
}

function editNotions() {
    store.editNotions(notionInstruction.value);
    notionInstruction.value = '';
}

async function createSession() {
    sessionCode.value = await store.createSession(sessionTitle.value);
}

async function createWorkshop() {
    workshopCode.value = await store.createWorkshop(sessionTitle.value, '');
}
</script>

<style scoped>
.session-box {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    background: var(--background-alt-grey);
}
</style>
