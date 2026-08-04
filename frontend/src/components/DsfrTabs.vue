<!--
  Onglets DSFR pilotés par Vue (`fr-tabs`).

  Le balisage suit le motif ARIA « tabs » attendu par le RGAA : `role=tablist` /
  `role=tab` / `role=tabpanel`, `aria-selected`, `aria-controls`, tabindex mobile
  (« roving tabindex ») et navigation au clavier ←/→/Début/Fin.

  Les panneaux sont tous rendus et masqués par `v-show` : l'état des formulaires
  d'un onglet survit au changement d'onglet (indispensable ici — la configuration
  du quiz ne doit pas se réinitialiser quand on va voir les notions).

  ⚠️ Si le CLIR embarque un jour le JS vanilla du DSFR, celui-ci initialiserait
  aussi `.fr-tabs` et gérerait le clavier une seconde fois (une flèche sauterait
  deux onglets). Le correctif serait alors de retirer `@keydown` ci-dessous.
-->
<template>
    <div class="fr-tabs">
        <ul class="fr-tabs__list" role="tablist" :aria-label="tabsLabel">
            <li v-for="tab in tabs" :key="tab.key" role="presentation">
                <button
                    :id="tabId(tab.key)"
                    class="fr-tabs__tab"
                    role="tab"
                    type="button"
                    :aria-selected="tab.key === modelValue"
                    :aria-controls="panelId(tab.key)"
                    :tabindex="tab.key === modelValue ? 0 : -1"
                    :disabled="tab.disabled"
                    :title="tab.disabled ? tab.disabledHint : undefined"
                    @click="select(tab)"
                    @keydown="onKeydown"
                >
                    {{ tab.label }}
                    <span v-if="tab.badge" class="fr-badge fr-badge--sm fr-ml-1v">
                        {{ tab.badge }}
                    </span>
                </button>
            </li>
        </ul>

        <div
            v-for="tab in tabs"
            v-show="tab.key === modelValue"
            :id="panelId(tab.key)"
            :key="`panel-${tab.key}`"
            class="fr-tabs__panel"
            :class="{ 'fr-tabs__panel--selected': tab.key === modelValue }"
            role="tabpanel"
            :aria-labelledby="tabId(tab.key)"
            tabindex="0"
        >
            <slot :name="tab.key" />
        </div>
    </div>
</template>

<script setup lang="ts">
import { useId } from 'vue';
import type { TabDefinition } from './dsfrTabs';

defineOptions({ name: 'DsfrTabs' });

const props = defineProps<{
    tabs: TabDefinition[];
    modelValue: string;
    /**
     * Libellé du groupe d'onglets, lu par les lecteurs d'écran.
     * Nommé `tabsLabel` et non `ariaLabel` : `aria-label` est aussi un attribut
     * HTML valide, et vue-tsc ne le rattache alors pas à la prop.
     */
    tabsLabel: string;
}>();

const emit = defineEmits<{ 'update:modelValue': [key: string] }>();

// Identifiant propre à l'instance : deux groupes d'onglets peuvent coexister sur la
// même page (onglets imbriqués) et partager des clés — les `id` doivent rester uniques
// pour que `aria-controls` / `aria-labelledby` désignent le bon élément.
const uid = useId();
const tabId = (key: string) => `tab-${uid}-${key}`;
const panelId = (key: string) => `panel-${uid}-${key}`;

function select(tab: TabDefinition) {
    if (tab.disabled || tab.key === props.modelValue) return;
    emit('update:modelValue', tab.key);
}

/** Onglets réellement atteignables au clavier. */
function selectableTabs() {
    return props.tabs.filter((tab) => !tab.disabled);
}

function focusTab(key: string) {
    emit('update:modelValue', key);
    // Le bouton n'existe qu'après le rendu : on attend la frame suivante.
    requestAnimationFrame(() => document.getElementById(tabId(key))?.focus());
}

function onKeydown(event: KeyboardEvent) {
    const tabs = selectableTabs();
    if (!tabs.length) return;

    const current = tabs.findIndex((tab) => tab.key === props.modelValue);
    let target: TabDefinition | undefined;

    switch (event.key) {
        case 'ArrowRight':
            target = tabs[(current + 1) % tabs.length];
            break;
        case 'ArrowLeft':
            target = tabs[(current - 1 + tabs.length) % tabs.length];
            break;
        case 'Home':
            target = tabs[0];
            break;
        case 'End':
            target = tabs[tabs.length - 1];
            break;
        default:
            return;
    }

    event.preventDefault();
    if (target) focusTab(target.key);
}
</script>
