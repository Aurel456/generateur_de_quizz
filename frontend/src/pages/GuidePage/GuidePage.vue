<template>
    <h1>Guide formateur</h1>

    <!-- Stats globales -->
    <h2 class="fr-h4">Statistiques globales</h2>
    <div class="fr-grid-row fr-grid-row--gutters fr-mb-4w">
        <div class="fr-col-6 fr-col-md-3" v-for="m in metrics" :key="m.label">
            <div class="fr-p-3w metric-tile">
                <p class="fr-display--xs fr-mb-0">{{ m.value }}</p>
                <p class="fr-text--sm fr-mb-0">{{ m.label }}</p>
            </div>
        </div>
    </div>

    <!-- Pipeline -->
    <h2 class="fr-h4">Le pipeline</h2>
    <pre class="fr-p-2w pipeline">
Document(s)
   └─► Notions fondamentales (détection, regroupement, activation)
          └─► Génération (Quiz QCM / Exercices) — niveaux, persona, consignes
                 └─► Édition (manuelle ou IA) + Vérification IA
                        └─► Session partagée  ──►  Participants  ──►  Analytics
                        └─► Atelier formateur (co-édition, publication)</pre>

    <!-- Points d'intervention -->
    <h2 class="fr-h4">Points d'intervention du formateur</h2>
    <ul class="fr-mb-4w">
        <li v-for="(p, i) in interventions" :key="i" class="fr-mb-1v">
            <strong>{{ p.step }}</strong> — {{ p.detail }}
        </li>
    </ul>

    <!-- Assistant formateur -->
    <h2 class="fr-h4">Assistant d'aide</h2>
    <p class="fr-text--sm">Posez une question sur l'utilisation de l'outil.</p>
    <div v-if="chat.length" class="fr-mb-2w chat-box">
        <div
            v-for="(m, i) in chat"
            :key="i"
            class="fr-p-2w chat-msg"
            :class="m.role === 'user' ? 'chat-user' : 'chat-assistant'"
        >
            <strong>{{ m.role === 'user' ? 'Vous' : 'Assistant' }} :</strong>
            <span style="white-space: pre-wrap">{{ m.content }}</span>
        </div>
    </div>
    <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-4w">
        <div class="fr-col">
            <label class="fr-label" for="assistant-input">Votre question</label>
            <input
                id="assistant-input"
                class="fr-input"
                v-model="assistantInput"
                :disabled="asking"
                placeholder="Ex : comment créer une session pool ?"
                @keyup.enter="askAssistant"
            />
        </div>
        <div class="fr-col-auto">
            <button class="fr-btn" :disabled="asking || !assistantInput.trim()" @click="askAssistant">
                {{ asking ? '…' : 'Demander' }}
            </button>
        </div>
    </div>
    <div v-if="assistantError" class="fr-alert fr-alert--warning fr-mb-3w" role="alert">
        <p class="fr-mb-0">{{ assistantError }}</p>
    </div>

    <!-- FAQ -->
    <h2 class="fr-h4">FAQ</h2>
    <div class="fr-accordions-group">
        <section class="fr-accordion" v-for="(item, i) in faq" :key="i">
            <h3 class="fr-accordion__title">
                <button class="fr-accordion__btn" :aria-expanded="open === i" :aria-controls="`faq-${i}`" @click="toggle(i)">
                    {{ item.q }}
                </button>
            </h3>
            <div :id="`faq-${i}`" class="fr-collapse" :class="{ 'fr-collapse--expanded': open === i }">
                <p class="fr-p-2w fr-mb-0">{{ item.a }}</p>
            </div>
        </section>
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, type GlobalStats } from '@/services/api';

defineOptions({ name: 'GuidePage' });

const stats = ref<GlobalStats>({
    total_questions: 0,
    total_documents: 0,
    total_tokens: 0,
    total_sessions: 0,
});
const open = ref<number | null>(0);

const interventions = [
    { step: '1. Documents', detail: 'choisir des sources lisibles ; activer Vision pour les PDF riches en schémas, One-shot pour une vue d’ensemble.' },
    { step: '2. Notions', detail: 'valider/compléter les notions détectées, regrouper par thématique, désactiver le hors-sujet avant de générer.' },
    { step: '3. Configuration', detail: 'doser les niveaux, ajuster les prompts par niveau, préciser une consigne libre (style et/ou périmètre).' },
    { step: '4. Relecture', detail: 'éditer manuellement ou via l’IA, lancer la vérification IA, annuler si besoin (historique).' },
    { step: '5. Diffusion', detail: 'créer une session (ou pool), suivre les analytics, fermer la session, ou co-éditer via un atelier.' },
];

const chat = ref<{ role: 'user' | 'assistant'; content: string }[]>([]);
const assistantInput = ref('');
const asking = ref(false);
const assistantError = ref('');

async function askAssistant() {
    const text = assistantInput.value.trim();
    if (!text) return;
    chat.value.push({ role: 'user', content: text });
    assistantInput.value = '';
    asking.value = true;
    assistantError.value = '';
    try {
        const { reply } = await api.assistantChat(chat.value.map((m) => ({ role: m.role, content: m.content })));
        chat.value.push({ role: 'assistant', content: reply });
    } catch (err) {
        assistantError.value = err instanceof Error ? err.message : 'Assistant indisponible.';
    } finally {
        asking.value = false;
    }
}

const metrics = computed(() => [
    { label: 'Questions générées', value: stats.value.total_questions },
    { label: 'Documents traités', value: stats.value.total_documents },
    { label: 'Tokens consommés', value: stats.value.total_tokens },
    { label: 'Sessions créées', value: stats.value.total_sessions },
]);

const faq = [
    {
        q: 'Les questions sont-elles fiables ?',
        a: 'Tout contenu généré doit être relu par un formateur. La vérification IA aide à repérer les questions auxquelles le LLM ne sait pas répondre depuis le document.',
    },
    {
        q: 'Comment éviter les doublons ?',
        a: 'La génération multi-niveaux passe les questions déjà produites en contexte pour ne pas les dupliquer.',
    },
    {
        q: 'Les bonnes réponses sont-elles visibles des participants ?',
        a: 'Non : le scoring est effectué côté serveur, les bonnes réponses ne sont jamais envoyées au navigateur avant soumission.',
    },
    {
        q: 'Le mode Vision, c’est quoi ?',
        a: 'Il analyse les pages PDF en images (schémas, formules) via un modèle vision. À activer à l’upload si un modèle vision est configuré.',
    },
];

function toggle(i: number) {
    open.value = open.value === i ? null : i;
}

onMounted(async () => {
    try {
        stats.value = await api.getGlobalStats();
    } catch {
        /* stats indisponibles : on garde les zéros */
    }
});
</script>

<style scoped>
.metric-tile {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    text-align: center;
    background: var(--background-alt-grey);
}
.pipeline {
    background: var(--background-alt-grey);
    border-radius: 0.5rem;
    overflow-x: auto;
    font-size: 0.85rem;
}
.chat-box {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    max-height: 20rem;
    overflow-y: auto;
}
.chat-msg + .chat-msg {
    border-top: 1px solid var(--border-default-grey);
}
.chat-user {
    background: var(--background-alt-blue-france);
}
</style>
