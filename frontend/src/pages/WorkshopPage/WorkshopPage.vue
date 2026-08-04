<template>
    <h1>Atelier formateur</h1>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
    </div>
    <div v-if="notice" class="fr-alert fr-alert--success fr-mb-3w" role="status">
        <p class="fr-mb-0">{{ notice }}</p>
    </div>

    <!-- Accès -->
    <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-2w">
        <div class="fr-col">
            <label class="fr-label" for="ws-code">Code de l'atelier</label>
            <input id="ws-code" class="fr-input" v-model="code" placeholder="Ex : K8S42X" />
        </div>
        <div class="fr-col-auto">
            <button class="fr-btn" :disabled="loading || !code.trim()" @click="load">
                {{ loading ? 'Chargement…' : 'Ouvrir' }}
            </button>
        </div>
    </div>

    <div v-if="summaries.length" class="fr-mb-3w">
        <label class="fr-label" for="ws-select">Ateliers existants</label>
        <select id="ws-select" class="fr-select" @change="onSelect">
            <option value="">— Sélectionner —</option>
            <option v-for="s in summaries" :key="s.work_code" :value="s.work_code">
                {{ s.title }} ({{ s.work_code }}) — {{ s.status }}
            </option>
        </select>
    </div>

    <template v-if="workshop">
        <div class="fr-grid-row fr-grid-row--middle fr-mb-1w">
            <h2 class="fr-col fr-h4 fr-mb-0">{{ workshop.title }} — {{ workshop.work_code }}</h2>
            <div class="fr-col-auto">
                <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="load">🔃 Rafraîchir</button>
                <button class="fr-btn fr-btn--sm fr-ml-1w" :disabled="saving" @click="save">
                    {{ saving ? 'Enregistrement…' : '💾 Enregistrer' }}
                </button>
            </div>
        </div>
        <p class="fr-text--sm">
            {{ workshop.questions.length }} question(s) · {{ workshop.exercises.length }} exercice(s)
            · {{ workshop.notions.length }} notion(s) · statut : {{ workshop.status }}
        </p>

        <DsfrTabs v-model="tab" :tabs="tabs" tabs-label="Sections de l'atelier">
        <template #questions>
            <p v-if="!workshop.questions.length" class="fr-text--sm">Aucune question.</p>
            <div v-for="(q, qi) in workshop.questions" :key="qi" class="fr-mb-2w fr-p-2w card">
                <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
                    <span class="fr-col fr-text--bold">Question {{ qi + 1 }}</span>
                    <span class="fr-col-auto">
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" :disabled="qi === 0" @click="move(workshop.questions, qi, -1)">⬆️</button>
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" :disabled="qi === workshop.questions.length - 1" @click="move(workshop.questions, qi, 1)">⬇️</button>
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="workshop.questions.splice(qi, 1)">🗑️</button>
                    </span>
                </div>
                <textarea class="fr-input fr-mb-1v" rows="2" v-model="q.question" />
                <div v-for="(text, label) in q.choices" :key="label" class="fr-grid-row fr-grid-row--middle fr-mb-1v">
                    <span class="fr-col-auto fr-mr-1v" :class="{ correct: q.correct_answers.includes(label) }">
                        <strong>{{ label }}{{ q.correct_answers.includes(label) ? ' ✓' : '' }}</strong>
                    </span>
                    <span class="fr-col"><input class="fr-input" v-model="q.choices[label]" /></span>
                </div>
            </div>
        </template>

        <template #exercises>
            <p v-if="!workshop.exercises.length" class="fr-text--sm">Aucun exercice.</p>
            <div v-for="(ex, ei) in workshop.exercises" :key="ei" class="fr-mb-2w fr-p-2w card">
                <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
                    <span class="fr-col fr-text--bold">Exercice {{ ei + 1 }} ({{ ex.exercise_type }})</span>
                    <span class="fr-col-auto">
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" :disabled="ei === 0" @click="move(workshop.exercises, ei, -1)">⬆️</button>
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" :disabled="ei === workshop.exercises.length - 1" @click="move(workshop.exercises, ei, 1)">⬇️</button>
                        <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="workshop.exercises.splice(ei, 1)">🗑️</button>
                    </span>
                </div>
                <textarea class="fr-input fr-mb-1v" rows="2" v-model="ex.statement" />
                <input v-if="ex.expected_answer !== undefined" class="fr-input" v-model="ex.expected_answer" placeholder="Réponse attendue" />
            </div>
        </template>

        <template #notions>
            <p v-if="!workshop.notions.length" class="fr-text--sm">Aucune notion.</p>
            <div v-for="(n, ni) in workshop.notions" :key="ni" class="fr-grid-row fr-grid-row--gutters fr-grid-row--middle fr-mb-1v">
                <div class="fr-col-4"><input class="fr-input" v-model="n.title" placeholder="Titre" /></div>
                <div class="fr-col"><input class="fr-input" v-model="n.description" placeholder="Description" /></div>
                <div class="fr-col-auto">
                    <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" :disabled="ni === 0" @click="move(workshop.notions, ni, -1)">⬆️</button>
                    <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="workshop.notions.splice(ni, 1)">🗑️</button>
                </div>
            </div>
            <div class="fr-input-group fr-mt-2w">
                <label class="fr-label fr-text--sm" for="ws-notion-edit">💬 Modifier les notions avec l'IA</label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input id="ws-notion-edit" class="fr-input" v-model="notionInstr" :disabled="busyNotions" @keyup.enter="editWorkshopNotions" />
                    </div>
                    <div class="fr-col-auto">
                        <button class="fr-btn fr-btn--secondary" :disabled="busyNotions || !notionInstr.trim()" @click="editWorkshopNotions">
                            {{ busyNotions ? '…' : 'Appliquer' }}
                        </button>
                    </div>
                </div>
            </div>
        </template>

        <template #tools>
            <!-- Fusion d'un autre atelier -->
            <div class="fr-p-3w card fr-mb-3w">
                <h3 class="fr-h6">Fusionner un autre atelier</h3>
                <p class="fr-text--sm">
                    Ajoute les questions, exercices et notions d'un autre atelier à celui-ci
                    (n'oubliez pas d'enregistrer ensuite).
                </p>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <label class="fr-label fr-text--sm" for="merge-code">Code de l'atelier à fusionner</label>
                        <input id="merge-code" class="fr-input" v-model="mergeCode" />
                    </div>
                    <div class="fr-col-auto">
                        <button class="fr-btn fr-btn--secondary" :disabled="merging || !mergeCode.trim()" @click="mergeWorkshop">
                            {{ merging ? 'Fusion…' : 'Fusionner' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- Publication -->
            <div class="fr-p-3w card">
                <h3 class="fr-h6">Publier en session étudiante</h3>
                <div class="fr-input-group">
                    <label class="fr-label" for="pub-title">Titre de la session</label>
                    <input id="pub-title" class="fr-input" v-model="publishTitle" />
                </div>
                <div class="fr-checkbox-group">
                    <input id="pool" type="checkbox" v-model="poolMode" />
                    <label class="fr-label" for="pool">Mode pool (sous-ensemble par participant)</label>
                </div>
                <div v-if="poolMode" class="fr-input-group">
                    <label class="fr-label" for="subset">Questions par participant</label>
                    <input id="subset" class="fr-input" type="number" min="1" v-model.number="subsetSize" />
                </div>
                <button class="fr-btn fr-mt-1w" :disabled="publishing" @click="publish">
                    {{ publishing ? 'Publication…' : 'Publier' }}
                </button>
                <div v-if="publishedCode" class="fr-alert fr-alert--success fr-mt-2w">
                    <p>
                        Session publiée — code <strong>{{ publishedCode }}</strong>.
                        <RouterLink :to="{ name: 'ParticipantPage', query: { code: publishedCode } }">
                            Page participant
                        </RouterLink>
                    </p>
                </div>
            </div>
        </template>
        </DsfrTabs>
    </template>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api, type Workshop, type WorkshopSummary } from '@/services/api';
import DsfrTabs from '@/components/DsfrTabs.vue';
import type { TabDefinition } from '@/components/dsfrTabs';

defineOptions({ name: 'WorkshopPage' });

const route = useRoute();
const code = ref('');
const workshop = ref<Workshop | null>(null);
const summaries = ref<WorkshopSummary[]>([]);
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const merging = ref(false);
const busyNotions = ref(false);
const error = ref('');
const notice = ref('');
const tab = ref('questions');

const tabs = computed<TabDefinition[]>(() => [
    { key: 'questions', label: 'Questions', badge: workshop.value?.questions.length || undefined },
    { key: 'exercises', label: 'Exercices', badge: workshop.value?.exercises.length || undefined },
    { key: 'notions', label: 'Notions', badge: workshop.value?.notions.length || undefined },
    { key: 'tools', label: 'Outils' },
]);

const publishTitle = ref('');
const poolMode = ref(false);
const subsetSize = ref(20);
const publishedCode = ref('');
const mergeCode = ref('');
const notionInstr = ref('');

/** Échange deux éléments d'un tableau (réordonnancement ⬆️/⬇️). */
function move<T>(arr: T[], i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
}

async function load() {
    if (!code.value.trim()) return;
    loading.value = true;
    error.value = '';
    notice.value = '';
    publishedCode.value = '';
    try {
        workshop.value = await api.getWorkshop(code.value.trim().toUpperCase());
        publishTitle.value = workshop.value.title;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Atelier introuvable.';
        workshop.value = null;
    } finally {
        loading.value = false;
    }
}

function onSelect(event: Event) {
    const value = (event.target as HTMLSelectElement).value;
    if (value) {
        code.value = value;
        load();
    }
}

async function save() {
    if (!workshop.value) return;
    saving.value = true;
    error.value = '';
    notice.value = '';
    try {
        workshop.value = await api.updateWorkshop(workshop.value.work_code, {
            editor_name: '',
            questions: workshop.value.questions,
            exercises: workshop.value.exercises,
            notions: workshop.value.notions,
        });
        notice.value = 'Atelier enregistré.';
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de l’enregistrement.';
    } finally {
        saving.value = false;
    }
}

async function editWorkshopNotions() {
    if (!workshop.value || !notionInstr.value.trim()) return;
    busyNotions.value = true;
    error.value = '';
    try {
        const { notions } = await api.editNotions(workshop.value.notions, notionInstr.value);
        workshop.value.notions = notions;
        notionInstr.value = '';
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de l’édition des notions.';
    } finally {
        busyNotions.value = false;
    }
}

async function mergeWorkshop() {
    if (!workshop.value || !mergeCode.value.trim()) return;
    merging.value = true;
    error.value = '';
    notice.value = '';
    try {
        const other = await api.getWorkshop(mergeCode.value.trim().toUpperCase());
        if (other.work_code === workshop.value.work_code) {
            error.value = 'Impossible de fusionner un atelier avec lui-même.';
            return;
        }
        workshop.value.questions.push(...other.questions);
        workshop.value.exercises.push(...other.exercises);
        const titles = new Set(workshop.value.notions.map((n) => n.title));
        for (const n of other.notions) if (!titles.has(n.title)) workshop.value.notions.push(n);
        notice.value = `Atelier ${other.work_code} fusionné. Pensez à enregistrer.`;
        mergeCode.value = '';
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Atelier à fusionner introuvable.';
    } finally {
        merging.value = false;
    }
}

async function publish() {
    if (!workshop.value) return;
    publishing.value = true;
    error.value = '';
    try {
        const res = await api.publishWorkshop(workshop.value.work_code, {
            session_title: publishTitle.value,
            pool_mode: poolMode.value,
            subset_size: poolMode.value ? subsetSize.value : null,
        });
        publishedCode.value = res.session_code;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la publication.';
    } finally {
        publishing.value = false;
    }
}

onMounted(async () => {
    try {
        summaries.value = await api.listWorkshops();
    } catch {
        /* liste indisponible : on continue avec la saisie manuelle */
    }
    const queryCode = route.query.code;
    if (typeof queryCode === 'string' && queryCode) {
        code.value = queryCode;
        load();
    }
});
</script>

<style scoped>
.card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
}
.correct {
    color: var(--text-default-success);
    font-weight: 700;
}
.fr-tag.active {
    background: var(--background-action-high-blue-france);
    color: var(--text-inverted-blue-france);
}
</style>
