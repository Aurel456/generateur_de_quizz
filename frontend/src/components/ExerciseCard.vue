<template>
    <article class="fr-mb-3w fr-p-3w exercise-card">
        <!-- En-tête -->
        <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
            <div class="fr-col">
                <span class="fr-badge fr-badge--sm fr-badge--purple-glycine">{{ typeLabel }}</span>
                <span class="fr-badge fr-badge--sm fr-ml-1v" :class="badgeClass">
                    {{ exercise.difficulty_level || 'n/a' }}
                </span>
                <span
                    v-if="exercise.exercise_type === 'calcul'"
                    class="fr-badge fr-badge--sm fr-ml-1v"
                    :class="exercise.verified ? 'fr-badge--success' : 'fr-badge--warning'"
                >
                    {{ exercise.verified ? '✓ Vérifié' : 'Non vérifié' }}
                </span>
            </div>
            <div class="fr-col-auto" v-if="!editing">
                <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="startEdit">
                    ✏️ Éditer
                </button>
                <button
                    class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                    @click="store.deleteExercise(index)"
                >
                    🗑️ Supprimer
                </button>
            </div>
        </div>

        <!-- Lecture -->
        <template v-if="!editing">
            <p class="fr-text--bold">{{ index + 1 }}. {{ exercise.statement }}</p>

            <!-- Calcul -->
            <template v-if="exercise.exercise_type === 'calcul'">
                <p v-if="exercise.expected_answer" class="fr-mb-1v">
                    <strong>Réponse attendue :</strong> {{ exercise.expected_answer }}
                </p>
                <ol v-if="exercise.steps.length" class="fr-mb-1v">
                    <li v-for="(step, si) in exercise.steps" :key="si">{{ step }}</li>
                </ol>
                <p v-if="exercise.verification_output" class="fr-text--sm verif-output">
                    {{ exercise.verification_output }}
                </p>
            </template>

            <!-- Trou -->
            <ul v-else-if="exercise.exercise_type === 'trou'" class="fr-mb-1v">
                <li v-for="(blank, bi) in exercise.blanks" :key="bi">
                    Blanc {{ blank.position ?? bi + 1 }} :
                    <strong>{{ blank.answer }}</strong>
                    <span v-if="blank.context" class="fr-hint-text"> — {{ blank.context }}</span>
                </li>
            </ul>

            <!-- Cas pratique -->
            <div v-else-if="exercise.exercise_type === 'cas_pratique'">
                <div v-for="(sq, qi) in exercise.sub_questions" :key="qi" class="fr-mb-1v">
                    <p class="fr-mb-0"><strong>Q{{ qi + 1 }}.</strong> {{ sq.question }}</p>
                    <p class="fr-mb-0 fr-text--sm"><em>{{ sq.answer }}</em></p>
                </div>
            </div>

            <p v-if="exercise.correction" class="fr-text--sm fr-mb-1v">
                <strong>Correction :</strong> {{ exercise.correction }}
            </p>
            <p v-if="exercise.pedagogical_comment" class="fr-text--sm fr-mb-1v pedago">
                🎓 {{ exercise.pedagogical_comment }}
            </p>

            <!-- Amélioration IA -->
            <div class="fr-input-group fr-mt-1w">
                <label class="fr-label fr-text--sm" :for="`improve-ex-${index}`">
                    🤖 Améliorer par IA
                </label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input
                            :id="`improve-ex-${index}`"
                            class="fr-input"
                            v-model="instruction"
                            placeholder="Ex : simplifie l'énoncé, ajoute une sous-question…"
                            :disabled="improving"
                            @keyup.enter="improve"
                        />
                    </div>
                    <div class="fr-col-auto">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="improving || !instruction.trim()"
                            @click="improve"
                        >
                            {{ improving ? '…' : 'Appliquer' }}
                        </button>
                    </div>
                </div>
            </div>
        </template>

        <!-- Édition manuelle (champs communs ; le structurel passe par l'IA) -->
        <template v-else>
            <div class="fr-input-group">
                <label class="fr-label" :for="`ex-st-${index}`">Énoncé</label>
                <textarea :id="`ex-st-${index}`" class="fr-input" rows="3" v-model="draft.statement" />
            </div>
            <div class="fr-input-group" v-if="exercise.exercise_type === 'calcul'">
                <label class="fr-label" :for="`ex-ans-${index}`">Réponse attendue</label>
                <input :id="`ex-ans-${index}`" class="fr-input" v-model="draft.expected_answer" />
            </div>
            <div class="fr-input-group">
                <label class="fr-label" :for="`ex-cor-${index}`">Correction</label>
                <textarea :id="`ex-cor-${index}`" class="fr-input" rows="2" v-model="draft.correction" />
            </div>
            <div class="fr-input-group">
                <label class="fr-label" :for="`ex-ped-${index}`">Commentaire pédagogique</label>
                <textarea
                    :id="`ex-ped-${index}`"
                    class="fr-input"
                    rows="2"
                    v-model="draft.pedagogical_comment"
                />
            </div>
            <button class="fr-btn fr-btn--sm fr-mr-1v" @click="save">Enregistrer</button>
            <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="editing = false">
                Annuler
            </button>
        </template>
    </article>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import type { Exercise } from '@/services/api';
import { useGenerationStore } from '@/stores/generationStore';

const props = defineProps<{ exercise: Exercise; index: number }>();

const store = useGenerationStore();
const editing = ref(false);
const improving = ref(false);
const instruction = ref('');
const draft = reactive<Exercise>(clone(props.exercise));

const TYPE_LABELS: Record<string, string> = {
    calcul: 'Calcul',
    trou: 'Texte à trou',
    cas_pratique: 'Cas pratique',
};
const typeLabel = computed(() => TYPE_LABELS[props.exercise.exercise_type] ?? props.exercise.exercise_type);

const badgeClass = computed(() => {
    if (props.exercise.difficulty_level === 'facile') return 'fr-badge--success';
    if (props.exercise.difficulty_level === 'difficile') return 'fr-badge--error';
    return 'fr-badge--new';
});

function clone(e: Exercise): Exercise {
    return JSON.parse(JSON.stringify(e));
}

function startEdit() {
    Object.assign(draft, clone(props.exercise));
    editing.value = true;
}

function save() {
    store.updateExercise(props.index, clone(draft));
    editing.value = false;
}

async function improve() {
    improving.value = true;
    try {
        await store.improveExercise(props.index, instruction.value);
        instruction.value = '';
    } finally {
        improving.value = false;
    }
}
</script>

<style scoped>
.exercise-card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
}
.verif-output {
    white-space: pre-wrap;
    background: var(--background-alt-grey);
    padding: 0.5rem;
    border-radius: 0.25rem;
}
.pedago {
    color: var(--text-mention-grey);
}
</style>
