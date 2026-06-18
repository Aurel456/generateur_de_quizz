<template>
    <h1>Passer un quiz</h1>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
    </div>

    <!-- Accès : code -->
    <section v-if="!session" class="fr-mb-4w">
        <div class="fr-input-group">
            <label class="fr-label" for="code">Code de session</label>
            <input id="code" class="fr-input" v-model="code" placeholder="Ex : K8S42X" />
        </div>
        <button class="fr-btn fr-mt-1w" :disabled="loading || !code.trim()" @click="loadSession">
            {{ loading ? 'Chargement…' : 'Accéder au quiz' }}
        </button>
    </section>

    <!-- Pool : saisie du nom avant de tirer un sous-ensemble -->
    <section v-else-if="needsStart && !result">
        <h2 class="fr-h4">{{ session.title }}</h2>
        <div class="fr-alert fr-alert--info fr-mb-2w">
            <p class="fr-mb-0">
                Quiz en mode <strong>pool</strong> : vous recevrez un sous-ensemble de questions
                tiré au sort. Vous pourrez réessayer avec de nouvelles questions.
            </p>
        </div>
        <div class="fr-input-group">
            <label class="fr-label" for="name-pool">Votre nom</label>
            <input id="name-pool" class="fr-input" v-model="participantName" />
        </div>
        <button
            class="fr-btn fr-mt-1w"
            :disabled="loading || !participantName.trim()"
            @click="startPool"
        >
            {{ loading ? 'Préparation…' : 'Commencer le quiz' }}
        </button>
    </section>

    <!-- Quiz -->
    <section v-else-if="!result">
        <h2 class="fr-h4">{{ session.title }}</h2>
        <div v-if="!isPool" class="fr-input-group">
            <label class="fr-label" for="name">Votre nom</label>
            <input id="name" class="fr-input" v-model="participantName" />
        </div>
        <p v-else class="fr-text--sm">Participant : <strong>{{ participantName }}</strong></p>

        <article
            v-for="(q, qi) in session.questions"
            :key="qi"
            class="fr-my-3w fr-p-3w question-card"
        >
            <p class="fr-text--bold">{{ qi + 1 }}. {{ q.question }}</p>
            <div v-for="(text, label) in q.choices" :key="label" class="fr-checkbox-group">
                <input
                    :id="`q${qi}-${label}`"
                    type="checkbox"
                    :value="label"
                    v-model="answers[qi]"
                />
                <label class="fr-label" :for="`q${qi}-${label}`">
                    <strong>{{ label }}.</strong> {{ text }}
                </label>
            </div>
        </article>

        <p v-if="missing.length" class="fr-text--sm">
            Questions non répondues : {{ missing.join(', ') }}
        </p>
        <button
            class="fr-btn"
            :disabled="loading || missing.length > 0 || !participantName.trim()"
            @click="submit"
        >
            {{ loading ? 'Envoi…' : 'Soumettre mes réponses' }}
        </button>
    </section>

    <!-- Résultats -->
    <section v-else>
        <h2 class="fr-h4">Résultat</h2>
        <div class="fr-callout" :class="passClass">
            <p class="fr-callout__title">Score : {{ result.score }} / {{ result.total }}</p>
            <p v-if="isPool" class="fr-mb-0">
                {{ scorePercent }} % —
                <strong>{{ passed ? '✓ Seuil atteint' : '✗ Seuil non atteint' }}</strong>
                (seuil : {{ Math.round(passThreshold * 100) }} %)
            </p>
        </div>

        <article
            v-for="(q, qi) in session!.questions"
            :key="qi"
            class="fr-my-3w fr-p-3w question-card"
            :class="correctionFor(qi)?.is_correct ? 'is-correct' : 'is-wrong'"
        >
            <p class="fr-text--bold">
                {{ qi + 1 }}. {{ q.question }}
                <span v-if="correctionFor(qi)?.is_correct"> ✓</span>
                <span v-else> ✗</span>
            </p>
            <ul class="fr-mb-1v">
                <li
                    v-for="(text, label) in q.choices"
                    :key="label"
                    :class="{ 'answer-correct': correctionFor(qi)?.correct_answers.includes(label) }"
                >
                    <strong>{{ label }}.</strong> {{ text }}
                    <span v-if="correctionFor(qi)?.correct_answers.includes(label)"> ✓</span>
                </li>
            </ul>
            <p v-if="correctionFor(qi)?.explanation" class="fr-text--sm fr-mb-0">
                <em>{{ correctionFor(qi)?.explanation }}</em>
            </p>
        </article>

        <button v-if="isPool" class="fr-btn fr-mr-1w" :disabled="loading" @click="retryPool">
            🔄 Réessayer (nouvelles questions)
        </button>
        <button class="fr-btn fr-btn--secondary" @click="restart">Quitter</button>
    </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api, type Correction, type ParticipantSession } from '@/services/api';

defineOptions({ name: 'ParticipantPage' });

const route = useRoute();
const code = ref('');
const participantName = ref('');
const session = ref<ParticipantSession | null>(null);
const answers = ref<Record<number, string[]>>({});
const result = ref<{ score: number; total: number; corrections: Correction[] } | null>(null);
const loading = ref(false);
const error = ref('');

// État pool.
const started = ref(false);
const poolIndices = ref<number[]>([]);
const passThreshold = ref(0.7);

const isPool = computed(() => session.value?.is_pool ?? false);
const needsStart = computed(() => isPool.value && !started.value);
const scorePercent = computed(() =>
    result.value && result.value.total > 0
        ? Math.round((result.value.score / result.value.total) * 100)
        : 0,
);
const passed = computed(() => scorePercent.value / 100 >= passThreshold.value);
const passClass = computed(() =>
    isPool.value ? (passed.value ? 'pool-pass' : 'pool-fail') : '',
);

const missing = computed(() => {
    if (!session.value) return [];
    return session.value.questions
        .map((_, i) => i)
        .filter((i) => !(answers.value[i] && answers.value[i].length > 0))
        .map((i) => i + 1);
});

function correctionFor(index: number): Correction | undefined {
    return result.value?.corrections.find((c) => c.index === index);
}

function resetAnswers() {
    answers.value = {};
    session.value?.questions.forEach((_, i) => (answers.value[i] = []));
}

async function loadSession() {
    loading.value = true;
    error.value = '';
    try {
        session.value = await api.getSession(code.value.trim().toUpperCase());
        started.value = false;
        resetAnswers();
        if (!session.value.is_active) error.value = 'Cette session est fermée.';
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Session introuvable.';
    } finally {
        loading.value = false;
    }
}

async function startPool() {
    if (!session.value || !participantName.value.trim()) return;
    loading.value = true;
    error.value = '';
    try {
        const subset = await api.getPoolSubset(session.value.session_code, participantName.value.trim());
        session.value.questions = subset.questions;
        poolIndices.value = subset.pool_indices;
        passThreshold.value = subset.pass_threshold;
        started.value = true;
        result.value = null;
        resetAnswers();
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Impossible de charger le sous-ensemble.';
    } finally {
        loading.value = false;
    }
}

async function submit() {
    if (!session.value) return;
    loading.value = true;
    error.value = '';
    try {
        const payload: Record<string, string[]> = {};
        Object.entries(answers.value).forEach(([i, labels]) => (payload[i] = labels));
        result.value = await api.submitAnswers(
            session.value.session_code,
            participantName.value.trim(),
            payload,
            isPool.value ? poolIndices.value : undefined,
        );
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la soumission.';
    } finally {
        loading.value = false;
    }
}

function retryPool() {
    startPool();
}

function restart() {
    result.value = null;
    session.value = null;
    started.value = false;
    answers.value = {};
}

onMounted(() => {
    const queryCode = route.query.code;
    if (typeof queryCode === 'string' && queryCode) {
        code.value = queryCode;
        loadSession();
    }
});
</script>

<style scoped>
.question-card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
}
.question-card.is-correct {
    border-left: 4px solid var(--border-plain-success);
}
.question-card.is-wrong {
    border-left: 4px solid var(--border-plain-error);
}
.answer-correct {
    color: var(--text-default-success);
    font-weight: 700;
}
.pool-pass {
    border-left: 4px solid var(--border-plain-success);
}
.pool-fail {
    border-left: 4px solid var(--border-plain-error);
}
</style>
