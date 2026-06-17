<template>
    <component :is="layout">
        <router-view />
    </component>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const layout = computed(() => `${route.meta.layout || 'Default'}-layout`);
</script>

<style>
.text-align-center {
    text-align: center;
}
</style>
