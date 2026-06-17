<template>
    <h1>Mode libre</h1>
    <p class="fr-text--sm fr-mb-3w">
        Générez un quiz par conversation, sans document. Décrivez votre sujet à l'assistant.
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
            <input
                id="chat-input"
                class="fr-input"
                v-model="input"
                :disabled="busy"
                @keyup.enter="send"
            />
        </div>
        <div class="fr-col-auto">
            <button class="fr-btn" :disabled="busy || !input.trim()" @click="send">
                {{ busy ? '…' : 'Envoyer' }}
            </button>
        </div>
    </div>

    <!-- Notions proposées -->
    <div v-if="notions.length" class="fr-mb-3w">
        <h2 class="fr-h6">Notions identifiées</h2>
        <ul class="fr-text--sm">
            <li v-for="(n, i) in notions" :key="i"><strong>{{ n.title }}</strong> — {{ n.description }}</li>
        </ul>
    </div>

    <!-- Génération -->
    <div v-if="chatId" class="fr-p-3w card fr-mb-3w">
        <h2 class="fr-h6">Générer le quiz</h2>
        <div class="fr-grid-row fr-grid-row--gutters">
            <div class="fr-col-4 fr-col-md-2" v-for="level in levels" :key="level.key">
                <label class="fr-label" :for="`c-${level.key}`">{{ level.label }}</label>
                <input :id="`c-${level.key}`" class="fr-input" type="number" min="0" v-model.number="counts[level.key]" />
            </div>
        </div>
        <button class="fr-btn fr-mt-2w" :disabled="generating || total === 0" @click="generate">
            {{ generating ? 'Génération…' : `Générer ${total} question(s)` }}
        </button>
    </div>

    <!-- Résultat -->
    <div v-if="questions.length">
        <h2 class="fr-h6">{{ questions.length }} questions générées</h2>
        <div v-for="(q, qi) in questions" :key="qi" class="fr-mb-2w fr-p-2w card">
            <p class="fr-text--bold fr-mb-1v">{{ qi + 1 }}. {{ q.question }}</p>
            <ul class="fr-mb-0">
                <li v-for="(text, label) in q.choices" :key="label" :class="{ correct: q.correct_answers.includes(label) }">
                    <strong>{{ label }}.</strong> {{ text }}
                </li>
            </ul>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { api, type Notion, type QuizQuestion } from '@/services/api';

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
const error = ref('');
const counts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });
const questions = ref<QuizQuestion[]>([]);

const total = computed(() => Object.values(counts).reduce((s, n) => s + (Number(n) || 0), 0));

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
            num_choices: 4,
            num_correct: 1,
        });
        questions.value = res.questions;
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de la génération.';
    } finally {
        generating.value = false;
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
