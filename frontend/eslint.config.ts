import eslint from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript';
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting';

// API de @vue/eslint-config-typescript v14 : `defineConfigWithVueTs` branche le parser
// vue-eslint-parser + typescript-eslint sur les .vue. `skipFormatting` reste en dernier :
// il neutralise les règles de mise en forme, laissées à Prettier.
export default defineConfigWithVueTs(
    {
        name: 'app/files-to-lint',
        files: ['**/*.{ts,mts,tsx,vue}'],
    },
    {
        name: 'app/files-to-ignore',
        ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/node_modules/**'],
    },
    eslint.configs.recommended,
    pluginVue.configs['flat/essential'],
    vueTsConfigs.recommended,
    {
        name: 'app/rules',
        rules: {
            // Interdit l'injection de HTML brut (risque XSS) : passer par du texte ou un
            // rendu markdown assaini.
            'vue/no-v-html': 'error',
        },
    },
    skipFormatting,
);
