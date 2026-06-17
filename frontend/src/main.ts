import { createApp, defineAsyncComponent } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import layouts from './layouts';
import ClirDsfrComponents from '@dgfip/clir-dsfr-components';
import '@dgfip/clir-dsfr-components/styles';

const pinia = createPinia();
const app = createApp(App);

for (const layout of layouts) {
    app.component(
        `${layout}-layout`,
        defineAsyncComponent(() => import(`./layouts/${layout}.vue`)),
    );
}

app.use(router);
app.use(pinia);
app.use(ClirDsfrComponents, {
    isFluid: import.meta.env.VITE_APP_IS_FLUID === 'true',
    isGreyThemeAvailable: import.meta.env.VITE_APP_IS_GREY_THEME === 'true',
});

app.mount('#app');
