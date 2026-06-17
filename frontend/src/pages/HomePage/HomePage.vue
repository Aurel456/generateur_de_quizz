<template>
    <div class="fr-grid-row fr-grid-row--middle fr-my-4w hero fr-p-4w">
        <div class="fr-col-12">
            <h1 class="fr-mb-2v">Générateur de Quiz &amp; Exercices IA</h1>
            <p class="fr-text--lead fr-mb-0">
                Version DSFR (en cours de migration). Générez des QCM à partir de vos
                documents, puis partagez-les en session.
            </p>
        </div>
    </div>

    <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-12 fr-col-md-6">
            <div class="fr-tile fr-enlarge-link">
                <div class="fr-tile__body">
                    <div class="fr-tile__content">
                        <h2 class="fr-tile__title">
                            <RouterLink :to="{ name: 'GeneratePage' }">Générer un quiz</RouterLink>
                        </h2>
                        <p class="fr-tile__desc">
                            Déposez un document, détectez les notions, générez le QCM.
                        </p>
                    </div>
                </div>
            </div>
        </div>
        <div class="fr-col-12 fr-col-md-6">
            <div class="fr-tile fr-enlarge-link">
                <div class="fr-tile__body">
                    <div class="fr-tile__content">
                        <h2 class="fr-tile__title">
                            <RouterLink :to="{ name: 'ParticipantPage' }">Passer un quiz</RouterLink>
                        </h2>
                        <p class="fr-tile__desc">Saisissez un code de session et répondez.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="fr-alert fr-alert--info fr-mt-4w">
        <h3 class="fr-alert__title">Migration en cours</h3>
        <p>
            Les fonctionnalités avancées (exercices, ateliers formateurs, analytics, mode
            vision, batch) restent disponibles sur l'interface Streamlit historique pendant
            la transition.
        </p>
    </div>
</template>

<script setup>
defineOptions({ name: 'HomePage' });
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
</style>
