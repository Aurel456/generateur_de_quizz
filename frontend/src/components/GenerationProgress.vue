<template>
    <div v-if="visible" class="fr-mt-2w" role="status" aria-live="polite">
        <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
            <p class="fr-col fr-text--sm fr-mb-0">
                <span aria-hidden="true" class="fr-mr-1v">⏳</span>{{ label }}
                <template v-if="store.progress.total > 0">
                    — {{ store.progress.current }}/{{ store.progress.total }}
                </template>
            </p>
            <p v-if="store.progress.total > 0" class="fr-col-auto fr-text--sm fr-mb-0">
                <strong>{{ store.progressPercent }} %</strong>
            </p>
        </div>

        <div
            class="gen-progress"
            role="progressbar"
            :aria-valuenow="store.progress.total > 0 ? store.progressPercent : undefined"
            aria-valuemin="0"
            aria-valuemax="100"
        >
            <div
                class="gen-progress__bar"
                :class="{ 'gen-progress__bar--indeterminate': store.progress.total === 0 }"
                :style="store.progress.total > 0 ? { width: `${store.progressPercent}%` } : undefined"
            ></div>
        </div>

        <p v-if="store.progress.message" class="fr-text--sm fr-mt-1v fr-mb-0">
            {{ store.progress.message }}
        </p>
        <p v-else-if="store.progress.itemCount > 0" class="fr-text--sm fr-mt-1v fr-mb-0">
            {{ store.progress.itemCount }} élément(s) généré(s)…
        </p>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useGenerationStore } from '@/stores/generationStore';

defineOptions({ name: 'GenerationProgress' });

// `kind` optionnel : si fourni, n'affiche la barre que pour cette opération
// (permet de placer une instance contextuelle sous chaque bouton).
const props = defineProps<{ kind?: string }>();

const store = useGenerationStore();

const visible = computed(
    () => store.progress.active && (!props.kind || store.progress.kind === props.kind),
);

const LABELS: Record<string, string> = {
    quiz: 'Génération du quiz…',
    exercises: 'Génération des exercices…',
    notions: 'Détection des notions…',
    verify: 'Vérification des questions…',
};

const label = computed(() => LABELS[store.progress.kind] ?? 'Traitement en cours…');
</script>

<style scoped>
.gen-progress {
    width: 100%;
    height: 0.75rem;
    background: var(--background-contrast-grey);
    border-radius: 0.375rem;
    overflow: hidden;
}

.gen-progress__bar {
    height: 100%;
    background: var(--background-action-high-blue-france);
    border-radius: 0.375rem;
    transition: width 0.3s ease;
}

/* Mode indéterminé : tant que le total n'est pas connu, animation de va-et-vient. */
.gen-progress__bar--indeterminate {
    width: 35%;
    animation: gen-progress-slide 1.2s ease-in-out infinite;
}

@keyframes gen-progress-slide {
    0% {
        margin-left: -35%;
    }
    100% {
        margin-left: 100%;
    }
}

@media (prefers-reduced-motion: reduce) {
    .gen-progress__bar--indeterminate {
        animation: none;
        width: 100%;
        opacity: 0.5;
    }
    .gen-progress__bar {
        transition: none;
    }
}
</style>
