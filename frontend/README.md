# Frontend — Vue 3 + CLIR DSFR

Interface du générateur de quiz, conforme au DSFR, qui consomme le backend FastAPI
(`../backend`).

## Lancement local

```sh
cp .npmrc.example .npmrc   # DGFIP uniquement (accès nexus au CLIR)
npm install
npm run dev                # http://localhost:8081/quizzator
```

Le backend doit tourner (`uvicorn backend.main:app` depuis la racine du repo). L'URL du
backend est `VITE_APP_BACKEND_HOST` (voir `config/.env`).

## Commandes

```sh
npm run build          # build de production (dans dist/)
npm run type-check     # vue-tsc
npm run lint           # ESLint --fix
npm run format         # Prettier
```

## Pages

| Route | Page |
| ----- | ---- |
| `/` | Accueil : accès aux fonctions + « Derniers changements » (lit `CHANGELOG.md`) |
| `/generer` | Génération, **en onglets** : Documents · Notions · Quiz QCM · Exercices · Aperçu texte · Exports & partage |
| `/participer?code=XXXXXX` | Passage de quiz, scoring serveur et correction |
| `/mode-libre` | Dialogue libre avec le modèle |
| `/atelier?code=XXXXXX` | Atelier formateur (Questions · Exercices · Notions · Outils) |
| `/analytics?code=XXXXXX` | Résultats d'une session |
| `/guide` | Guide d'utilisation |

Les onglets sont rendus par [`src/components/DsfrTabs.vue`](./src/components/DsfrTabs.vue) :
balisage `fr-tabs` avec les rôles ARIA attendus par le RGAA, navigation clavier ←/→, et
panneaux masqués en `v-show` pour que l'état des formulaires survive au changement
d'onglet.

## Registres npm — `# DGFIP`

Le nexus est le **registre par défaut** (`.npmrc`). Son miroir n'est ni à jour ni
exhaustif, d'où deux règles :

1. **Versions figées** : `package-lock.json` committé + `npm ci` au build (jamais
   `npm install`, qui viserait des versions trop récentes → `404` en chaîne).
2. **Paquet absent du miroir** : ce qu'on ne récupère pas sur le nexus se prend sur
   `https://registry.npmjs.org`. Pour un paquet **scopé**, une ligne durable dans le
   `.npmrc` (prise en compte par `npm install`, le lockfile *et* le build Docker) :

   ```ini
   registry=https://nexus3.appli.dgfip/repository/npmjs_group/
   @scope:registry=https://registry.npmjs.org
   ```

   Pour un paquet **non scopé**, npm ne sait pas cibler un registre paquet par paquet :
   `npm install <paquet> --registry=https://registry.npmjs.org` au coup par coup, ou
   inverser la logique du `.npmrc` si les cas se multiplient.

> ⚠️ Dès qu'un paquet est redirigé vers npmjs, le `package-lock.json` devient **mixte** et
> la machine qui builde a besoin d'un accès sortant vers npmjs, pas seulement au nexus.
> Pour savoir où en est le projet :
> `grep -o '"resolved": "https://[^/]*' package-lock.json | sort | uniq -c`.
> Le `.npmrc` est copié dans l'image **avant** `npm ci` (voir `Dockerfile`), sinon la
> redirection ne s'applique pas au build.

## Changelog

[`CHANGELOG.md`](./CHANGELOG.md) alimente les cartes « Derniers changements » de la page
d'accueil. Une section par mise à jour, la plus récente en premier :

```md
# Mise à jour du 1 janvier 2026

- Première modification
```

## Conventions

Identiques au template DSFR : composants CLIR `Fr*` pour la structure, classes `fr-*`
pour le contenu, variables CSS DSFR (jamais de couleur en dur), un seul `<h1>` par page,
aucun `fetch` hors `src/services/`.
