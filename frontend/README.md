# Frontend — Vue 3 + CLIR DSFR (migration)

Nouvelle interface du générateur de quiz, conforme au DSFR, qui consomme le backend
FastAPI (`../backend`). Coexiste avec l'app Streamlit pendant la migration.

## Lancement local

```sh
cp .npmrc.example .npmrc   # DGFIP uniquement (accès nexus au CLIR)
npm install
npm run dev                # http://localhost:8081/quizz
```

Le backend doit tourner (`uvicorn backend.main:app` depuis la racine du repo). L'URL du
backend est `VITE_APP_BACKEND_HOST` (voir `config/.env`).

## Pages migrées

| Route | Page | Backend utilisé |
| ----- | ---- | --------------- |
| `/generer` | Upload → notions → génération QCM → création de session | `/documents`, `/notions/detect`, `/quiz/generate`, `/sessions` |
| `/participer?code=XXXXXX` | Passage de quiz + scoring serveur + correction | `/sessions/{code}`, `/sessions/{code}/submit` |

## Conventions

Identiques au template DSFR : composants CLIR `Fr*` pour la structure, classes `fr-*`
pour le contenu, variables CSS DSFR (jamais de couleur en dur), un seul `<h1>` par page.
