<template>
    <div class="fr-my-7w text-align-center">
        <h1>Page introuvable</h1>
        <p class="fr-text--lead">La page demandée n'existe pas.</p>
        <RouterLink class="fr-btn fr-mt-2w" :to="{ name: 'HomePage' }">
            Retour à l'accueil
        </RouterLink>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'ErrorPage' });
</script>
