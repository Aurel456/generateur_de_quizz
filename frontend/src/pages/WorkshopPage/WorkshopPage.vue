<template>
    <h1>Atelier formateur</h1>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
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
        <h2 class="fr-h4">{{ workshop.title }} — {{ workshop.work_code }}</h2>
        <p class="fr-text--sm">
            {{ workshop.questions.length }} question(s) · {{ workshop.exercises.length }} exercice(s)
            · {{ workshop.notions.length }} notion(s) · statut : {{ workshop.status }}
            <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="load">🔃 Rafraîchir</button>
        </p>

        <div v-for="(q, qi) in workshop.questions" :key="qi" class="fr-mb-2w fr-p-2w card">
            <p class="fr-text--bold fr-mb-1v">{{ qi + 1 }}. {{ q.question }}</p>
            <ul class="fr-mb-0">
                <li
                    v-for="(text, label) in q.choices"
                    :key="label"
                    :class="{ correct: q.correct_answers.includes(label) }"
                >
                    <strong>{{ label }}.</strong> {{ text }}
                </li>
            </ul>
        </div>

        <!-- Publication -->
        <div class="fr-p-3w card fr-mt-3w">
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
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api, type Workshop, type WorkshopSummary } from '@/services/api';

defineOptions({ name: 'WorkshopPage' });

const route = useRoute();
const code = ref('');
const workshop = ref<Workshop | null>(null);
const summaries = ref<WorkshopSummary[]>([]);
const loading = ref(false);
const publishing = ref(false);
const error = ref('');

const publishTitle = ref('');
const poolMode = ref(false);
const subsetSize = ref(20);
const publishedCode = ref('');

async function load() {
    if (!code.value.trim()) return;
    loading.value = true;
    error.value = '';
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
</style>
