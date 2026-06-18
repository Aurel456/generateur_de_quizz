<template>
    <article class="fr-mb-3w fr-p-3w question-card">
        <!-- En-tête : difficulté + actions -->
        <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
            <div class="fr-col">
                <span class="fr-badge fr-badge--sm" :class="badgeClass">
                    {{ question.difficulty_level || 'n/a' }}
                </span>
                <span
                    v-for="notion in question.related_notions"
                    :key="notion"
                    class="fr-badge fr-badge--sm fr-badge--blue-cumulus fr-ml-1v"
                >
                    {{ notion }}
                </span>
                <span
                    v-if="isLlmKnowledge"
                    class="fr-badge fr-badge--sm fr-badge--warning fr-ml-1v"
                    title="Question issue de la base de connaissance du modèle, sans appui documentaire"
                >
                    ⚠️ base LLM
                </span>
            </div>
            <div class="fr-col-auto" v-if="!editing">
                <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm" @click="startEdit">
                    ✏️ Éditer
                </button>
                <button
                    class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                    @click="store.deleteQuestion(index)"
                >
                    🗑️ Supprimer
                </button>
            </div>
        </div>

        <!-- Mode lecture -->
        <template v-if="!editing">
            <p class="fr-text--bold">{{ index + 1 }}. {{ question.question }}</p>
            <ul class="fr-mb-1v">
                <li
                    v-for="(text, label) in question.choices"
                    :key="label"
                    :class="{ 'answer-correct': question.correct_answers.includes(label) }"
                >
                    <strong>{{ label }}.</strong> {{ text }}
                    <span v-if="question.correct_answers.includes(label)"> ✓</span>
                </li>
            </ul>
            <p v-if="question.explanation" class="fr-text--sm fr-mb-1v">
                <em>{{ question.explanation }}</em>
            </p>
            <p v-if="question.citation" class="fr-text--sm fr-mb-1v citation">
                « {{ question.citation }} »
            </p>
            <p v-if="sourceLabel" class="fr-text--xs fr-mb-1v source-line">📄 {{ sourceLabel }}</p>

            <!-- Amélioration par IA -->
            <div class="fr-input-group fr-mt-1w">
                <label class="fr-label fr-text--sm" :for="`improve-${index}`">
                    🤖 Améliorer par IA
                </label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input
                            :id="`improve-${index}`"
                            class="fr-input"
                            v-model="instruction"
                            placeholder="Ex : reformule plus clairement, ajoute un distracteur plausible…"
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

        <!-- Mode édition manuelle -->
        <template v-else>
            <div class="fr-input-group">
                <label class="fr-label" :for="`q-${index}`">Énoncé</label>
                <textarea :id="`q-${index}`" class="fr-input" rows="2" v-model="draft.question" />
            </div>

            <p class="fr-label fr-mb-1v">Choix (cochez les bonnes réponses)</p>
            <div
                v-for="(text, label) in draft.choices"
                :key="label"
                class="fr-grid-row fr-grid-row--gutters fr-grid-row--middle fr-mb-1v"
            >
                <div class="fr-col-auto">
                    <div class="fr-checkbox-group fr-checkbox-group--sm">
                        <input
                            :id="`correct-${index}-${label}`"
                            type="checkbox"
                            :checked="draft.correct_answers.includes(label)"
                            @change="toggleCorrect(label)"
                        />
                        <label class="fr-label" :for="`correct-${index}-${label}`">{{ label }}</label>
                    </div>
                </div>
                <div class="fr-col">
                    <input class="fr-input" v-model="draft.choices[label]" />
                </div>
            </div>

            <div class="fr-input-group fr-mt-1w">
                <label class="fr-label" :for="`exp-${index}`">Explication</label>
                <textarea :id="`exp-${index}`" class="fr-input" rows="2" v-model="draft.explanation" />
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
import type { QuizQuestion } from '@/services/api';
import { useGenerationStore } from '@/stores/generationStore';

const props = defineProps<{ question: QuizQuestion; index: number }>();

const store = useGenerationStore();
const editing = ref(false);
const improving = ref(false);
const instruction = ref('');
const draft = reactive<QuizQuestion>(clone(props.question));

const LLM_KNOWLEDGE_SOURCE = 'Base de connaissance du modèle LLM';

const badgeClass = computed(() => {
    if (props.question.difficulty_level === 'facile') return 'fr-badge--success';
    if (props.question.difficulty_level === 'difficile') return 'fr-badge--error';
    return 'fr-badge--new';
});

const isLlmKnowledge = computed(() => props.question.source_document === LLM_KNOWLEDGE_SOURCE);

const sourceLabel = computed(() => {
    if (isLlmKnowledge.value) return '';
    const parts: string[] = [];
    if (props.question.source_document) parts.push(props.question.source_document);
    if (props.question.source_pages?.length)
        parts.push(`p. ${props.question.source_pages.join(', ')}`);
    return parts.join(' — ');
});

function clone(q: QuizQuestion): QuizQuestion {
    return JSON.parse(JSON.stringify(q));
}

function startEdit() {
    Object.assign(draft, clone(props.question));
    editing.value = true;
}

function toggleCorrect(label: string) {
    const i = draft.correct_answers.indexOf(label);
    if (i >= 0) draft.correct_answers.splice(i, 1);
    else draft.correct_answers.push(label);
}

function save() {
    store.updateQuestion(props.index, clone(draft));
    editing.value = false;
}

async function improve() {
    improving.value = true;
    try {
        await store.improveQuestion(props.index, instruction.value);
        instruction.value = '';
    } finally {
        improving.value = false;
    }
}
</script>

<style scoped>
.question-card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
}
.answer-correct {
    color: var(--text-default-success);
    font-weight: 700;
}
.citation {
    border-left: 3px solid var(--border-default-grey);
    padding-left: 0.5rem;
    color: var(--text-mention-grey);
}
.source-line {
    color: var(--text-mention-grey);
}
</style>
