<template>
    <div class="fr-grid-row fr-grid-row--middle fr-my-4w hero fr-p-4w">
        <div class="fr-col-12">
            <h1 class="fr-mb-2v">Générateur de Quiz &amp; Exercices IA</h1>
            <p class="fr-text--lead fr-mb-0">
                Générez des QCM et des exercices à partir de vos documents, puis partagez-les
                en session ou en atelier.
            </p>
        </div>
    </div>

    <!-- Une tuile par grande fonction : la page d'accueil reste un point d'entrée,
         le détail vit dans les onglets de chaque page. -->
    <div class="fr-grid-row fr-grid-row--gutters">
        <div v-for="entry in entries" :key="entry.route" class="fr-col-12 fr-col-md-4">
            <div class="fr-tile fr-enlarge-link fr-tile--sm">
                <div class="fr-tile__body">
                    <div class="fr-tile__content">
                        <h2 class="fr-tile__title">
                            <RouterLink :to="{ name: entry.route }">{{ entry.title }}</RouterLink>
                        </h2>
                        <p class="fr-tile__desc">{{ entry.description }}</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <template v-if="changelogEntries.length">
        <div class="fr-grid-row fr-grid-row--middle fr-mt-6v fr-mb-2v">
            <div class="fr-col fr-p-2v">
                <h2 class="fr-mb-0">Derniers changements</h2>
            </div>
            <div class="fr-col-auto changelog-panel--badge">
                <span>
                    {{ changelogEntries.length }} mise{{ changelogEntries.length > 1 ? 's' : '' }} à
                    jour
                </span>
            </div>
        </div>

        <div class="fr-grid-row fr-grid-row--gutters">
            <div
                v-for="section in changelogEntries"
                :key="section.title"
                class="fr-col-12 fr-col-md-4"
            >
                <article class="changelog-card">
                    <p class="changelog-card--type">{{ section.title }}</p>
                    <ul class="changelog-card--list">
                        <li v-for="item in section.items" :key="item">{{ item }}</li>
                    </ul>
                </article>
            </div>
        </div>
    </template>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import changelogContent from '../../../CHANGELOG.md?raw';
import { parseChangelogMarkdown } from './homePageChangelog';

defineOptions({ name: 'HomePage' });

const entries = [
    {
        route: 'GeneratePage',
        title: 'Générer un quiz',
        description: 'Documents, notions, QCM, exercices et exports — en onglets.',
    },
    {
        route: 'ParticipantPage',
        title: 'Passer un quiz',
        description: 'Saisissez un code de session et répondez.',
    },
    {
        route: 'ChatPage',
        title: 'Mode libre',
        description: 'Dialoguez avec le modèle sur vos documents.',
    },
    {
        route: 'WorkshopPage',
        title: 'Atelier formateur',
        description: 'Retravaillez un quiz à plusieurs avant publication.',
    },
    {
        route: 'AnalyticsPage',
        title: 'Analytics',
        description: 'Résultats et statistiques d’une session.',
    },
    {
        route: 'GuidePage',
        title: 'Guide',
        description: 'Prise en main, bonnes pratiques et formats d’export.',
    },
];

const changelog = parseChangelogMarkdown(changelogContent);
const changelogEntries = computed(() =>
    changelog.sections.filter((section) => section.items.length > 0),
);
</script>

<style scoped>
.hero {
    border: 1px solid var(--border-default-grey);
    border-radius: 1.5rem;
    background: linear-gradient(
        135deg,
        var(--background-default-grey),
        var(--background-alt-blue-france) 55%,
        var(--background-default-grey)
    );
}

.changelog-panel--badge {
    text-align: right;
}

.changelog-panel--badge span {
    padding: 0.4rem 0.8rem;
    border-radius: 999px;
    background: var(--background-contrast-blue-france);
    border: 1px solid var(--border-default-blue-france);
    color: var(--text-action-high-blue-france);
    font-size: 0.875rem;
    font-weight: 700;
    white-space: nowrap;
}

.changelog-card {
    height: 100%;
    padding: 1.25rem;
    border-radius: 1rem;
    background: var(--background-default-grey);
    border: 1px solid var(--border-default-grey);
}

.changelog-card--type {
    margin: 0;
    color: var(--text-action-high-blue-france);
    font-size: 0.875rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.changelog-card--list {
    margin: 1rem 0 0;
    padding-left: 1.25rem;
}

.changelog-card--list li + li {
    margin-top: 0.75rem;
}
</style>
