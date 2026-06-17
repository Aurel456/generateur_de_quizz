import routes from '@/routes';
import { createRouter, createWebHistory } from 'vue-router';
import type { RouteLocationNormalizedLoaded } from 'vue-router';

const base = import.meta.env?.VITE_APP_BASE_URL ?? '';
const appName = import.meta.env?.VITE_APP_TITLE ?? 'Générateur de Quiz';

const router = createRouter({
    history: createWebHistory(base),
    routes,
});

function resolveRouteTitle(route: RouteLocationNormalizedLoaded) {
    for (let index = route.matched.length - 1; index >= 0; index -= 1) {
        const meta = route.matched[index].meta as {
            title?: string;
            breadcrumb?: { title?: string };
        };
        const title = meta.title || meta.breadcrumb?.title;
        if (typeof title === 'string' && title.trim()) return title.trim();
    }
    return '';
}

router.afterEach((to) => {
    const title = resolveRouteTitle(to);
    document.title = title ? `${title} - ${appName}` : appName;
});

export default router;
