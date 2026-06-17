<template>
    <h1>Passer un quiz</h1>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
    </div>

    <!-- Accès : code + nom -->
    <section v-if="!session" class="fr-mb-4w">
        <div class="fr-input-group">
            <label class="fr-label" for="code">Code de session</label>
            <input id="code" class="fr-input" v-model="code" placeholder="Ex : K8S42X" />
        </div>
        <button class="fr-btn fr-mt-1w" :disabled="loading || !code.trim()" @click="loadSession">
            {{ loading ? 'Chargement…' : 'Accéder au quiz' }}
        </button>
    </section>

    <!-- Quiz -->
    <section v-else-if="!result">
        <h2 class="fr-h4">{{ session.title }}</h2>
        <div class="fr-input-group">
            <label class="fr-label" for="name">Votre nom</label>
            <input id="name" class="fr-input" v-model="participantName" />
        </div>

        <article
            v-for="(q, qi) in session.questions"
            :key="qi"
            class="fr-my-3w fr-p-3w question-card"
        >
            <p class="fr-text--bold">{{ qi + 1 }}. {{ q.question }}</p>
            <div
                v-for="(text, label) in q.choices"
                :key="label"
                class="fr-checkbox-group"
            >
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
        <div class="fr-callout">
            <p class="fr-callout__title">Score : {{ result.score }} / {{ result.total }}</p>
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

        <button class="fr-btn fr-btn--secondary" @click="restart">Recommencer</button>
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

async function loadSession() {
    loading.value = true;
    error.value = '';
    try {
        session.value = await api.getSession(code.value.trim().toUpperCase());
        answers.value = {};
        session.value.questions.forEach((_, i) => (answers.value[i] = []));
        if (!session.value.is_active) error.value = 'Cette session est fermée.';
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Session introuvable.';
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
        );
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la soumission.';
    } finally {
        loading.value = false;
    }
}

function restart() {
    result.value = null;
    session.value = null;
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
</style>
