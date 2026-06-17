<template>
    <h1>Analytics d'une session</h1>

    <div v-if="error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ error }}</p>
    </div>

    <!-- Accès -->
    <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom fr-mb-3w">
        <div class="fr-col">
            <label class="fr-label" for="code">Code de session</label>
            <input id="code" class="fr-input" v-model="code" placeholder="Ex : K8S42X" />
        </div>
        <div class="fr-col-auto">
            <button class="fr-btn" :disabled="loading || !code.trim()" @click="load">
                {{ loading ? 'Chargement…' : 'Afficher' }}
            </button>
        </div>
    </div>

    <template v-if="data">
        <h2 class="fr-h4">{{ data.session.title }}</h2>

        <!-- Métriques globales -->
        <div class="fr-grid-row fr-grid-row--gutters fr-mb-4w">
            <div class="fr-col-6 fr-col-md-3" v-for="metric in metrics" :key="metric.label">
                <div class="fr-p-3w metric-tile">
                    <p class="fr-display--xs fr-mb-0">{{ metric.value }}</p>
                    <p class="fr-text--sm fr-mb-0">{{ metric.label }}</p>
                </div>
            </div>
        </div>

        <p v-if="!data.participants.length" class="fr-alert fr-alert--info">
            <span>Aucun participant n'a encore soumis ses réponses.</span>
        </p>

        <template v-else>
            <!-- Taux par question -->
            <h3 class="fr-h6">Taux de réussite par question</h3>
            <div v-for="(q, idx) in perQuestionList" :key="idx" class="fr-mb-2w">
                <p class="fr-text--sm fr-mb-1v">
                    <strong>Q{{ Number(idx) + 1 }}.</strong> {{ q.question_text }}
                </p>
                <div class="bar-track">
                    <div
                        class="bar-fill"
                        :style="{ width: pct(q.success_rate), background: rateColor(q.success_rate) }"
                    >
                        {{ pct(q.success_rate) }}
                    </div>
                </div>
            </div>

            <!-- Taux par notion -->
            <template v-if="perNotionList.length">
                <h3 class="fr-h6 fr-mt-4w">Taux de réussite par notion</h3>
                <div v-for="notion in perNotionList" :key="notion.title" class="fr-mb-2w">
                    <p class="fr-text--sm fr-mb-1v">
                        {{ notion.title }} <span class="fr-hint-text">({{ notion.question_count }} q.)</span>
                    </p>
                    <div class="bar-track">
                        <div
                            class="bar-fill"
                            :style="{ width: pct(notion.avg_success_rate), background: rateColor(notion.avg_success_rate) }"
                        >
                            {{ pct(notion.avg_success_rate) }}
                        </div>
                    </div>
                </div>
            </template>

            <!-- Classement -->
            <h3 class="fr-h6 fr-mt-4w">Classement des participants</h3>
            <div class="fr-table fr-table--bordered">
                <table>
                    <thead>
                        <tr>
                            <th scope="col">Rang</th>
                            <th scope="col">Participant</th>
                            <th scope="col">Score</th>
                            <th scope="col">%</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(p, i) in data.participants" :key="i">
                            <td>{{ medal(i) }}</td>
                            <td>{{ p.name }}</td>
                            <td>{{ p.score }} / {{ p.total }}</td>
                            <td>{{ p.percentage }} %</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Recommandations IA -->
            <h3 class="fr-h6 fr-mt-4w">Recommandations IA</h3>
            <button
                class="fr-btn fr-btn--secondary"
                :disabled="recoLoading"
                @click="loadRecommendations"
            >
                {{ recoLoading ? 'Analyse…' : 'Analyser les résultats avec l’IA' }}
            </button>

            <div v-if="reco" class="fr-mt-3w">
                <div v-if="reco.weak_notions.length" class="fr-alert fr-alert--warning fr-mb-2w">
                    <h4 class="fr-alert__title">Notions faibles</h4>
                    <ul class="fr-mb-0">
                        <li v-for="(w, i) in reco.weak_notions" :key="i">
                            <strong>{{ w.notion }} ({{ Math.round(w.success_rate) }} %)</strong> —
                            {{ w.recommendation }}
                        </li>
                    </ul>
                </div>
                <div v-if="reco.problematic_questions.length" class="fr-mb-2w">
                    <h4 class="fr-h6">Questions problématiques</h4>
                    <ul>
                        <li v-for="(p, i) in reco.problematic_questions" :key="i">
                            <strong>Q{{ p.question_index + 1 }}</strong> : {{ p.issue }} —
                            <em>{{ p.suggestion }}</em>
                        </li>
                    </ul>
                </div>
                <div v-if="reco.student_patterns.length" class="fr-mb-2w">
                    <h4 class="fr-h6">Patterns observés</h4>
                    <ul>
                        <li v-for="(s, i) in reco.student_patterns" :key="i">
                            <strong>{{ s.pattern }}</strong> — {{ s.recommendation }}
                        </li>
                    </ul>
                </div>
                <div v-if="reco.global_recommendations.length" class="fr-callout">
                    <h4 class="fr-callout__title">Recommandations globales</h4>
                    <ul class="fr-mb-0">
                        <li v-for="(g, i) in reco.global_recommendations" :key="i">{{ g }}</li>
                    </ul>
                </div>
            </div>
        </template>
    </template>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api, type AnalyticsData, type Recommendations } from '@/services/api';

defineOptions({ name: 'AnalyticsPage' });

const route = useRoute();
const code = ref('');
const data = ref<AnalyticsData | null>(null);
const reco = ref<Recommendations | null>(null);
const loading = ref(false);
const recoLoading = ref(false);
const error = ref('');

const metrics = computed(() => {
    const g = data.value?.global_stats;
    if (!g) return [];
    return [
        { label: 'Participants', value: g.num_participants },
        { label: 'Score moyen', value: `${g.avg_score} %` },
        { label: 'Score médian', value: `${g.median_score} %` },
        { label: 'Questions', value: g.total_questions },
    ];
});

const perQuestionList = computed(() => data.value?.per_question ?? {});

const perNotionList = computed(() =>
    Object.entries(data.value?.per_notion ?? {}).map(([title, v]) => ({ title, ...v })),
);

function pct(rate: number) {
    return `${Math.round(rate * 100)}%`;
}

function rateColor(rate: number) {
    if (rate < 0.4) return 'var(--background-flat-error)';
    if (rate < 0.7) return 'var(--background-flat-warning)';
    return 'var(--background-flat-success)';
}

function medal(rank: number) {
    return ['🥇', '🥈', '🥉'][rank] ?? String(rank + 1);
}

async function load() {
    loading.value = true;
    error.value = '';
    reco.value = null;
    try {
        data.value = await api.getAnalytics(code.value.trim().toUpperCase());
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Session introuvable.';
        data.value = null;
    } finally {
        loading.value = false;
    }
}

async function loadRecommendations() {
    recoLoading.value = true;
    error.value = '';
    try {
        reco.value = await api.getRecommendations(code.value.trim().toUpperCase());
    } catch (err) {
        error.value = err instanceof Error ? err.message : 'Échec de l’analyse IA.';
    } finally {
        recoLoading.value = false;
    }
}

onMounted(() => {
    const queryCode = route.query.code;
    if (typeof queryCode === 'string' && queryCode) {
        code.value = queryCode;
        load();
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
.bar-track {
    background: var(--background-contrast-grey);
    border-radius: 0.25rem;
    overflow: hidden;
}
.bar-fill {
    min-width: 2.5rem;
    padding: 0.1rem 0.5rem;
    color: var(--text-inverted-grey);
    font-size: 0.75rem;
    font-weight: 700;
    text-align: right;
    white-space: nowrap;
}
</style>
