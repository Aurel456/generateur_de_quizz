/*
 * Routes migrées vers Vue + DSFR. Les fonctionnalités non encore portées
 * (exercices, ateliers, analytics, vision, batch…) restent sur Streamlit.
 */
const routesConfig = [
    {
        path: '/',
        name: 'HomePage',
        component: () => import('@/pages/HomePage/HomePage.vue'),
        meta: { breadcrumb: { hide: true, title: 'Accueil' } },
    },
    {
        path: '/generer',
        name: 'GeneratePage',
        component: () => import('@/pages/GeneratePage/GeneratePage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Générer un quiz' } },
    },
    {
        // `?code=XXXXXX` pré-remplit le code de session participant.
        path: '/participer',
        name: 'ParticipantPage',
        component: () => import('@/pages/ParticipantPage/ParticipantPage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Passer un quiz' } },
    },
    {
        path: '/mode-libre',
        name: 'ChatPage',
        component: () => import('@/pages/ChatPage/ChatPage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Mode libre' } },
    },
    {
        // `?code=XXXXXX` ouvre directement l'atelier.
        path: '/atelier',
        name: 'WorkshopPage',
        component: () => import('@/pages/WorkshopPage/WorkshopPage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Atelier formateur' } },
    },
    {
        // `?code=XXXXXX` charge directement les analytics de la session.
        path: '/analytics',
        name: 'AnalyticsPage',
        component: () => import('@/pages/AnalyticsPage/AnalyticsPage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Analytics' } },
    },
    {
        path: '/guide',
        name: 'GuidePage',
        component: () => import('@/pages/GuidePage/GuidePage.vue'),
        meta: { breadcrumb: { hide: false, title: 'Guide' } },
    },
    {
        path: '/accessibilite',
        name: 'AccessibilityPage',
        component: () => import('@/pages/AccessibilityPage/AccessibilityPage.vue'),
        meta: { title: 'Accessibilité' },
    },
    {
        path: '/:pathMatch(.*)*',
        name: 'ErrorPage',
        component: () => import('@/pages/ErrorPage/ErrorPage.vue'),
        meta: { title: 'Page introuvable' },
    },
];

export default routesConfig;
