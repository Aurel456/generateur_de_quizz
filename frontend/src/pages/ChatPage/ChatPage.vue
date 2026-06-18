<template>
    <h1>Mode libre</h1>
    <p class="fr-text--sm fr-mb-3w">
        Générez un quiz ou des exercices par conversation, sans document. Décrivez votre sujet
        à l'assistant.
    </p>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
    </div>

    <!-- Conversation -->
    <div class="fr-mb-2w chat-box">
        <div
            v-for="(m, i) in messages"
            :key="i"
            class="fr-p-2w chat-msg"
            :class="m.role === 'user' ? 'chat-user' : 'chat-assistant'"
        >
            <strong>{{ m.role === 'user' ? 'Vous' : 'Assistant' }} :</strong>
            <span style="white-space: pre-wrap">{{ m.content }}</span>
        </div>
    </div>

    <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-3w">
        <div class="fr-col">
            <label class="fr-label" for="chat-input">Votre message</label>
            <input id="chat-input" class="fr-input" v-model="input" :disabled="busy" @keyup.enter="send" />
        </div>
        <div class="fr-col-auto">
            <button class="fr-btn" :disabled="busy || !input.trim()" @click="send">
                {{ busy ? '…' : 'Envoyer' }}
            </button>
        </div>
    </div>

    <!-- Notions proposées : éditables / validables -->
    <div v-if="notions.length" class="fr-mb-3w">
        <h2 class="fr-h6">Notions identifiées ({{ enabledNotions.length }} actives)</h2>
        <div
            v-for="(n, i) in notions"
            :key="i"
            class="fr-grid-row fr-grid-row--gutters fr-grid-row--middle fr-mb-1v"
        >
            <div class="fr-col-auto">
                <div class="fr-checkbox-group fr-checkbox-group--sm">
                    <input :id="`cn-${i}`" type="checkbox" v-model="n.enabled" />
                    <label class="fr-label" :for="`cn-${i}`"><span class="fr-sr-only">Active</span></label>
                </div>
            </div>
            <div class="fr-col-4"><input class="fr-input" v-model="n.title" placeholder="Titre" /></div>
            <div class="fr-col"><input class="fr-input" v-model="n.description" placeholder="Description" /></div>
            <div class="fr-col-auto">
                <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="notions.splice(i, 1)">
                    🗑️
                </button>
            </div>
        </div>
    </div>

    <!-- Génération -->
    <div v-if="chatId" class="fr-p-3w card fr-mb-3w">
        <h2 class="fr-h6">Générer</h2>
        <p v-if="suggestedApplied" class="fr-text--sm fr-mb-1v">
            ✨ Configuration suggérée par l'assistant appliquée.
        </p>
        <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
            <div class="fr-col-4 fr-col-md-2" v-for="level in levels" :key="level.key">
                <label class="fr-label" :for="`c-${level.key}`">{{ level.label }}</label>
                <input :id="`c-${level.key}`" class="fr-input" type="number" min="0" v-model.number="counts[level.key]" />
            </div>
            <div class="fr-col-6 fr-col-md-2">
                <label class="fr-label" for="c-choices">Choix</label>
                <input id="c-choices" class="fr-input" type="number" min="2" max="6" v-model.number="config.num_choices" />
            </div>
            <div class="fr-col-6 fr-col-md-2">
                <label class="fr-label" for="c-correct">Bonnes rép.</label>
                <input id="c-correct" class="fr-input" type="number" min="1" :disabled="config.vrai_faux" v-model.number="config.num_correct" />
            </div>
        </div>
        <div class="fr-checkbox-group fr-mt-1w">
            <input id="c-vf" type="checkbox" v-model="config.vrai_faux" />
            <label class="fr-label" for="c-vf">Mode Vrai / Faux</label>
        </div>
        <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
            <button class="fr-btn" :disabled="generating || total === 0" @click="generate">
                {{ generating ? 'Génération…' : `Générer ${total} question(s)` }}
            </button>
            <button class="fr-btn fr-btn--secondary" :disabled="generatingEx || exTotal === 0" @click="generateExercises">
                {{ generatingEx ? 'Génération…' : `Générer ${exTotal} exercice(s)` }}
            </button>
        </div>
        <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
            <div class="fr-col-4 fr-col-md-2" v-for="level in levels" :key="`ex-${level.key}`">
                <label class="fr-label fr-text--sm" :for="`ec-${level.key}`">Exo {{ level.label }}</label>
                <input :id="`ec-${level.key}`" class="fr-input" type="number" min="0" v-model.number="exCounts[level.key]" />
            </div>
        </div>
    </div>

    <!-- Résultat questions -->
    <div v-if="questions.length" class="fr-mb-3w">
        <h2 class="fr-h6">{{ questions.length }} question(s) générée(s)</h2>
        <div v-for="(q, qi) in questions" :key="qi" class="fr-mb-2w fr-p-2w card">
            <p class="fr-text--bold fr-mb-1v">{{ qi + 1 }}. {{ q.question }}</p>
            <ul class="fr-mb-0">
                <li v-for="(text, label) in q.choices" :key="label" :class="{ correct: q.correct_answers.includes(label) }">
                    <strong>{{ label }}.</strong> {{ text }}
                </li>
            </ul>
        </div>

        <!-- Création de session depuis le mode libre -->
        <div class="fr-p-3w card">
            <h3 class="fr-h6">Partager en session</h3>
            <div class="fr-input-group">
                <label class="fr-label" for="chat-session-title">Titre de la session</label>
                <input id="chat-session-title" class="fr-input" v-model="sessionTitle" />
            </div>
            <button class="fr-btn fr-mt-1w" :disabled="creatingSession || !sessionTitle.trim()" @click="createSession">
                {{ creatingSession ? 'Création…' : 'Créer la session' }}
            </button>
            <div v-if="sessionCode" class="fr-alert fr-alert--success fr-mt-2w">
                <p>
                    Session créée — code <strong>{{ sessionCode }}</strong>.
                    <RouterLink :to="{ name: 'ParticipantPage', query: { code: sessionCode } }">
                        Page participant
                    </RouterLink>
                </p>
            </div>
        </div>
    </div>

    <!-- Résultat exercices -->
    <div v-if="exercises.length" class="fr-mb-3w">
        <h2 class="fr-h6">{{ exercises.length }} exercice(s) généré(s)</h2>
        <div v-for="(ex, ei) in exercises" :key="ei" class="fr-mb-2w fr-p-2w card">
            <p class="fr-text--bold fr-mb-1v">{{ ei + 1 }}. {{ ex.statement }}</p>
            <p v-if="ex.expected_answer" class="fr-mb-0 fr-text--sm">
                <strong>Réponse :</strong> {{ ex.expected_answer }}
            </p>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api, type Exercise, type Notion, type QuizQuestion } from '@/services/api';

defineOptions({ name: 'ChatPage' });

const levels = [
    { key: 'facile', label: '🟢 Facile' },
    { key: 'moyen', label: '🟡 Moyen' },
    { key: 'difficile', label: '🔴 Difficile' },
] as const;

const chatId = ref('');
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([]);
const notions = ref<Notion[]>([]);
const input = ref('');
const busy = ref(false);
const generating = ref(false);
const generatingEx = ref(false);
const creatingSession = ref(false);
const error = ref('');
const counts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });
const exCounts = reactive<Record<string, number>>({ facile: 0, moyen: 0, difficile: 0 });
const config = reactive({ num_choices: 4, num_correct: 1, vrai_faux: false });
const questions = ref<QuizQuestion[]>([]);
const exercises = ref<Exercise[]>([]);
const suggestedApplied = ref(false);
const sessionTitle = ref('');
const sessionCode = ref('');

const total = computed(() => Object.values(counts).reduce((s, n) => s + (Number(n) || 0), 0));
const exTotal = computed(() => Object.values(exCounts).reduce((s, n) => s + (Number(n) || 0), 0));
const enabledNotions = computed(() => notions.value.filter((n) => n.enabled));

/** Applique la configuration suggérée par l'assistant (best-effort). */
function applySuggested(cfg: Record<string, unknown> | null) {
    if (!cfg) return;
    const dc = cfg.difficulty_counts as Record<string, number> | undefined;
    if (dc && typeof dc === 'object') {
        for (const key of ['facile', 'moyen', 'difficile']) {
            if (typeof dc[key] === 'number') counts[key] = dc[key];
        }
    }
    if (typeof cfg.num_choices === 'number') config.num_choices = cfg.num_choices;
    if (typeof cfg.num_correct === 'number') config.num_correct = cfg.num_correct;
    if (typeof cfg.vrai_faux === 'boolean') config.vrai_faux = cfg.vrai_faux;
    suggestedApplied.value = true;
}

async function send() {
    const text = input.value.trim();
    if (!text) return;
    messages.value.push({ role: 'user', content: text });
    input.value = '';
    busy.value = true;
    error.value = '';
    try {
        const res = await api.chatMessage(chatId.value, text);
        messages.value.push({ role: 'assistant', content: res.message });
        notions.value = res.notions;
        applySuggested(res.suggested_config);
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Erreur de conversation.';
    } finally {
        busy.value = false;
    }
}

async function generate() {
    generating.value = true;
    error.value = '';
    try {
        const res = await api.chatGenerateQuiz(chatId.value, {
            difficulty_counts: { ...counts },
            num_choices: config.num_choices,
            num_correct: config.num_correct,
            vrai_faux: config.vrai_faux,
            notions: notions.value,
        });
        questions.value = res.questions;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la génération.';
    } finally {
        generating.value = false;
    }
}

async function generateExercises() {
    generatingEx.value = true;
    error.value = '';
    try {
        const res = await api.chatGenerateExercises(chatId.value, {
            difficulty_counts: { ...exCounts },
            notions: notions.value,
        });
        exercises.value = res.exercises;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la génération des exercices.';
    } finally {
        generatingEx.value = false;
    }
}

async function createSession() {
    creatingSession.value = true;
    error.value = '';
    try {
        const res = await api.createSession(sessionTitle.value, questions.value, enabledNotions.value);
        sessionCode.value = res.session_code;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la création de session.';
    } finally {
        creatingSession.value = false;
    }
}

onMounted(async () => {
    busy.value = true;
    try {
        const res = await api.chatStart();
        chatId.value = res.chat_id;
        messages.value.push({ role: 'assistant', content: res.message });
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Impossible de démarrer la conversation.';
    } finally {
        busy.value = false;
    }
});
</script>

<style scoped>
.chat-box {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    max-height: 24rem;
    overflow-y: auto;
}
.chat-msg + .chat-msg {
    border-top: 1px solid var(--border-default-grey);
}
.chat-user {
    background: var(--background-alt-blue-france);
}
.card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
}
.correct {
    color: var(--text-default-success);
    font-weight: 700;
}
</style>
