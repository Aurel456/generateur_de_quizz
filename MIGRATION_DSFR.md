# Migration vers le DSFR — feuille de route

Branche : `dev-dsfr`. Migration de l'app **Streamlit** vers l'architecture normée
**backend FastAPI + frontend Vue 3 + CLIR DSFR**, par tranches (strangler pattern).
Streamlit reste fonctionnel pendant toute la transition.

## Principe

La logique métier (`core/`, `generation/`, `processing/`, `sessions/`, `export/`) était
déjà **découplée de Streamlit**. Elle est donc **réutilisée telle quelle** par le nouveau
backend — aucune duplication. Seul reste à reconstruire l'UI (`app.py`, `pages/`, `ui/`)
en Vue + DSFR, et à refactorer `sessions/analytics.py` (calcul ✅ / rendu Plotly ❌).

```
Streamlit (app.py, pages/, ui/)          [historique, conservé]
        │  réutilisent
        ▼
core/ generation/ processing/ sessions/  ← logique métier partagée
        ▲  réutilisés (sans copie)
        │
backend/ (FastAPI)  ◄── HTTP ──  frontend/ (Vue 3 + CLIR DSFR)   [cible]
```

## Architecture cible

| Composant | Emplacement | Port (compose) |
| --------- | ----------- | -------------- |
| App Streamlit (historique) | `app.py`, `pages/` | 3051 |
| Backend FastAPI | `backend/` | 3054 → 8000 |
| Frontend Vue + DSFR | `frontend/` | 3052 → 8080 |

Lancement dev : `uvicorn backend.main:app --reload` (racine) + `npm run dev` (frontend).
Tout-en-un : `docker compose up --build`.

## État d'avancement

### ✅ Fait dans cette itération

- Socle backend FastAPI réutilisant la logique métier (`backend/`).
- Socle frontend Vue 3 + CLIR DSFR (`frontend/`), conventions du template DSFR.
- **Tranche « Génération formateur »** (de bout en bout) :
  - upload multi-documents → extraction + chunking (`/documents`) ;
  - détection des notions (`/notions/detect`) ;
  - génération de QCM avec niveaux/choix/notions/persona/Vrai-Faux/humour (`/quiz/generate`) ;
  - page `/generer` (upload → notions cochables → config → quiz affiché).
- **Tranche « Sessions & participant »** :
  - création de session depuis un quiz (`/sessions`) ;
  - vue participant sans réponses + scoring serveur + correction (`/sessions/{code}`, `/submit`) ;
  - page `/participer?code=XXXXXX`.
- Conteneurisation des 3 services (`compose.yml`), `.dockerignore`, `.gitignore` complétés.
- **Tranche « Édition des questions »** :
  - amélioration par IA via instruction libre (`/quiz/improve-question`, réutilise
    `question_editor.improve_question_with_llm`) ;
  - composant `QuestionCard.vue` : édition manuelle (énoncé, choix, bonnes réponses,
    explication), suppression, et amélioration IA par question.
- **Tranche « Exercices »** (calcul / trou / cas pratique) :
  - génération (`/exercises/generate`, réutilise `exercise_generator.generate_exercises` ;
    le type « calcul » déclenche la vérification sandbox `calc_agent` côté serveur) ;
  - amélioration IA (`/exercises/improve`, réutilise `improve_exercise_with_llm`) ;
  - composant `ExerciseCard.vue` (affichage adapté au type, édition des champs communs,
    suppression, amélioration IA) ; section dédiée dans `/generer` (accumulation).
- **Tranche « Analytics »** :
  - **refactor** : extraction de `generate_ai_recommendations` vers `sessions/analytics_core.py`
    (sans dépendance Streamlit/Plotly) ; `analytics.py` la réimporte (comportement inchangé) ;
  - endpoints `GET /sessions/{code}/analytics` (réutilise `get_session_analytics`) et
    `POST /sessions/{code}/recommendations` (réutilise `analytics_core`) ;
  - page `/analytics?code=…` : métriques, taux par question/notion en **barres DSFR**
    (remplace Plotly), classement (table + podium), recommandations IA.
- **Tranche « Vérification IA des QCM »** : `/quiz/verify` (réutilise `quiz_verifier.verify_quiz`)
  + bouton + résumé (validées / reformulées / supprimées) dans `/generer`.
- **Tranche « Acronymes »** : `/acronyms/detect` (référentiel best-effort + détection LLM)
  + section dédiée dans `/generer`.
- **Tranche « Notions avancées »** : `/notions/edit` (chat LLM) + `/notions/merge` (fusion)
  + boutons tout cocher / décocher / regrouper + édition par instruction.
- **Tranche « Exports »** : `/export` (HTML / CSV / Moodle XML pour quiz, exercices, combiné ;
  réutilise `export.quiz_exporter`) + boutons de téléchargement.
- **Tranche « Ateliers formateurs »** : `/workshops` CRUD + `/workshops/{code}/publish`
  (réutilise les work_sessions de `session_store`) + page `/atelier` (liste, vue, publication,
  mode pool) + bouton « Créer un atelier » depuis `/generer`.
- **Tranche « Mode libre »** : `/chat/start`, `/chat/{id}/message`, `/chat/{id}/generate-quiz`
  (réutilise `chat_mode`, état en mémoire via `chat_store`) + page `/mode-libre`.
- **Tranche « Vision + Batch »** : option `vision_mode` à l'upload (`extract_and_chunk_multiple_vision`,
  modèle vision propagé) + toggle `batch_mode` sur quiz/exercices.
- **Tranche « Stats + Guide »** : `/stats/global` (réutilise `stats_manager.load_stats`) + page
  `/guide` (métriques, schéma du pipeline, FAQ).

### ✅ Toutes les tranches fonctionnelles sont migrées

Hors périmètre (volontaire) :
- **Auth** (`core/auth.py`) : désactivée dans l'app Streamlit d'origine — non migrée. À
  brancher via une dépendance FastAPI (`Depends`) + SSO applicatif si nécessaire (voir le
  template DSFR, `docs/00-architecture.md §6`).
- **Détails non répliqués à l'identique** : historique des modifications, ajout manuel de
  questions/exercices/notions « from scratch », édition fine des tableaux (blancs / sous-questions)
  — couverts partiellement (édition des champs communs + amélioration IA).

## Dettes techniques à traiter avant la prod

- **Génération = requêtes longues** : aujourd'hui synchrones (threadpool). Passer à des
  **jobs asynchrones + progression** (SSE/polling) pour `/quiz/generate`, `/notions/detect`
  (réutiliser les `progress_callback` et `on_item` déjà présents dans le métier) — sinon
  risque de timeout derrière un reverse-proxy.
- **`doc_store` en mémoire mono-instance** : remplacer par Redis ou un stockage persistant
  pour le multi-instances ; ajouter une expiration (TTL) explicite.
- **CORS** : restreindre `CORS_ORIGINS` aux origines réelles en production.
- **Vision/batch non câblés** dans `/documents` (mode texte uniquement pour l'instant).
- **Tests** : ajouter des tests d'API (pytest + httpx) sur les nouveaux endpoints ; les 51
  tests métier existants restent valables.
- **Accessibilité** : audit RGAA + mise à jour de la déclaration avant mise en service.

## Méthode pour migrer une tranche

1. Identifier la fonction métier dans `generation/` ou `sessions/` (déjà découplée).
2. Ajouter un schéma (DTO) dans `backend/app/schemas.py` + un router dans `backend/app/api/`.
3. Vérifier via Swagger (`http://localhost:8000/docs`).
4. Construire la page Vue + DSFR correspondante (appel via `frontend/src/services/api.ts`).
5. Cocher la tranche ici, retirer l'équivalent Streamlit une fois validé.
