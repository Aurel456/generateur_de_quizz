<template>
    <div>
        <FrSkipLinks contentLabel="Contenu" :links="linksData" />
        <FrHeader
            id="quizz-head"
            :config="FrHeaderConfig"
            :menuConfig="FrNavigationConfig"
            @displayModal="display"
        />
        <main id="applicationContent" role="main" class="fr-my-2w" :class="containerClass">
            <FrBreadcrumb class="fr-mb-2v fr-mt-0" />
            <slot />
        </main>
        <FrFooter
            id="quizz-footer"
            :config="FrFooterConfig"
            :operatorConfig="FrOperatorConfig"
            @displayModal="display"
        />
        <FrDisplayModal v-model="showModal" :originId="originId" />
    </div>
</template>

<script setup lang="ts">
import { computed, getCurrentInstance, ref } from 'vue';
import FrHeaderConfig from './FrHeaderConfig';
import FrNavigationConfig from './FrNavigationConfig';
import FrFooterConfig from './FrFooterConfig';
import FrOperatorConfig from './FrOperatorConfig';

defineOptions({ name: 'DefaultLayout' });

const instance = getCurrentInstance();

const linksData = [
    { href: '#fr-header-quizz-front', label: 'Menu' },
    { href: '#fr-footer-quizz-front', label: 'Pied de page' },
];

const showModal = ref(false);
const originId = ref('');

const containerClass = computed(() => {
    const clir = instance?.appContext.config.globalProperties.$clir;
    return clir?.isFluid ? 'fr-container--fluid fr-px-5v' : 'fr-container';
});

function display(nextOriginId: string) {
    originId.value = nextOriginId;
    showModal.value = true;
}
</script>
