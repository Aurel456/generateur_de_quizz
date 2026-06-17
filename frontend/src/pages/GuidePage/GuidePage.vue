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
</style>
