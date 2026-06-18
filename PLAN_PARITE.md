# Plan de parité — porter TOUTES les fonctionnalités Streamlit dans l'app DSFR

But : amener le nouveau couple **backend FastAPI + frontend Vue/DSFR** à la **parité
fonctionnelle complète** avec l'app Streamlit historique, puis retirer Streamlit.

Ce fichier est la **source de vérité** du reste à faire (il survit au compactage du
contexte). Compléter au fur et à mesure. Voir aussi `MIGRATION_DSFR.md` (architecture,
dettes) et `README.md` (Streamlit) pour la liste exhaustive des fonctionnalités d'origine.

## Rappel d'architecture
- La logique métier (`core/`, `generation/`, `processing/`, `sessions/`, `export/`) est
  **réutilisée telle quelle** par le backend (`backend/app/api/*`). Le travail restant =
  surtout **profondeur d'UI** + **jobs asynchrones** (les endpoints existent souvent déjà).
- Ajouter une fonctionnalité = (1) endpoint/DTO dans `backend/app/`, (2) appel dans
  `frontend/src/services/api.ts`, (3) action store + composant/page Vue. Voir `MIGRATION_DSFR.md §"Méthode"`.
- Déploiement : `npm ci` + `package-lock.json` committé ; sous-chemin `/quizzator`. (cf. historique).

## Légende
✅ fait · 🟡 partiel · ❌ manquant

---

## Inventaire par domaine

### Quiz QCM
- ✅ Multi-documents, multi-format, chunking tokens, génération multi-niveaux, anti-doublons
- ✅ Nb choix 2–6, mode Fixe/Variable, mode Vrai/Faux, badges difficulté, tags notions
- ✅ Édition manuelle + amélioration IA (QuestionCard), vérification IA (reformulation/suppression)
- ✅ Exports HTML/CSV/Moodle, citations
- ✅ Persona ; instructions PAR niveau personnalisables + règles fixes en lecture seule (Phase 2)
- ✅ Affichage source (document + pages précises) + citation dans QuestionCard (Phase 2)
- ✅ Consigne libre unifiée (classification formulation/périmètre via `instruction_classifier` + filtrage chunks par périmètre) (Phase 2)
- ✅ Quiz sur base de connaissance LLM sans document (`generate_quiz_from_llm_knowledge`) (Phase 2)
- ✅ Historique des modifications (undo, snapshot avant modif) (Phase 2)

### Exercices (calcul / trou / cas pratique)
- ✅ 3 types, 3 niveaux, accumulation, vérification calcul (sandbox Python), retry hybride JSON, tags
- ✅ Édition champs communs + amélioration IA (ExerciseCard)
- ✅ Prompts par niveau + règles fixes affichées (Phase 2) ; 🟡 vérification IA trou/cas_pratique à exposer
- ✅ Édition fine des structures (étapes, blancs, sous-questions) ; ajout manuel d'exercice (Phase 2)

### Mode libre (génération par conversation)
- ✅ Conversation, génération des notions depuis le chat, génération quiz directe (ChatPage)
- 🟡 Notions affichées mais **non éditables/validables** dans le chat ; `suggested_config` renvoyé mais **non appliqué** au formulaire
- ❌ Création de session partagée depuis le mode libre ; récupération du quiz dans le store principal
- ❌ `generate_exercises_direct` (exercices en mode libre)

### Notions fondamentales
- ✅ Détection, fusion (Regrouper), tout cocher/décocher, chat LLM (edit), toggle actif
- ✅ Regroupement visuel par thématique (toggle « Par thématique ») (Phase 3)
- ✅ Comptage « N questions » par notion (Phase 2) ; ajout/suppression/édition manuelle + mélange (`notion_mixing`) (Phase 3)

### Acronymes
- ✅ Détection (référentiel + LLM)
- ✅ Édition LLM (`edit_acronyms_with_llm`), toggle actif/inactif, ajout/suppression manuelle (Phase 3) ; glossaire dans exports géré côté métier

### Sessions partagées & Analytics
- ✅ Création session, page participant (questions manquantes), scoring serveur, correction
- ✅ Dashboard analytics (métriques, taux/question, taux/notion, classement, recommandations IA)
- 🟡 Fermeture de session (`deactivate_session`) non exposée
- ❌ **Mode Pool** (création pool, sous-ensemble par participant, seuil, « réessayer » — `create_pool_session`/`get_next_subset`)
- ❌ Sessions incluant les exercices (le back accepte `exercises_data`, le front ne l'envoie pas)

### Ateliers formateurs
- ✅ Création (depuis Génération), lecture, mise à jour, publication (avec option pool), rafraîchir
- 🟡 WorkshopPage = vue + publication ; **édition** réelle limitée
- ❌ 4 onglets (Questions/Exercices/Notions/Outils), édition complète + réordonnancement (⬆️/⬇️), chat LLM par onglet, ajout manuel, import depuis une session, fusion de deux ateliers

### Guide formateur & Stats
- ✅ Schéma pipeline, FAQ, stats globales (GuidePage)
- 🟡 Points d'intervention détaillés ; stats en bandeau permanent
- ❌ Chatbot « assistant formateur » (chat d'aide à l'usage, distinct du mode libre)

### Mode Vision / Batch / Raisonnement
- ✅ Toggle Vision à l'upload, toggle Batch (quiz/exercices), cache LLM + token tracking (métier)
- ✅ Vision : DPI min/max + pages-par-bloc réglables UI (Phase 3) ; batch compatible vision
- ✅ Réglage DPI / pages par bloc, mode One-shot, toggle `enable_thinking` (Phase 3) ; ❌ parser API externe ; suivi de progression spécifique des batchs (la barre globale couvre déjà le batch)

---

## Chantiers transverses (prioritaires — conditionnent la qualité du reste)

1. **Jobs asynchrones + progression** 🔴 le plus important.
   Les générations/vérifications sont aujourd'hui **synchrones** (risque de timeout, pas de
   feedback). Transformer `/quiz/generate`, `/exercises/generate`, `/notions/detect`,
   `/quiz/verify` (et batch) en **tâches asynchrones** : `POST` → `job_id`, puis **SSE** ou
   polling `GET /jobs/{id}` (progression + items au fil de l'eau). Réutiliser les
   `progress_callback` et `on_item` déjà présents dans le métier. UI : barre de progression
   + affichage incrémental.
2. **Persistance de l'état de travail** : `doc_store` / `chat_store` sont en mémoire
   mono-instance → passer à Redis ou disque + TTL (sinon perte au redémarrage / multi-réplicas).
3. **Réglages avancés exposés** : taille de chunk, `enable_thinking`, `notion_mixing`,
   vision (DPI / pages), one-shot.
4. **Tests d'API** (pytest + httpx) sur les nouveaux endpoints ; les 51 tests métier restent valables.
5. **Auth** (si requise) : dépendance FastAPI `Depends` + SSO applicatif. (Désactivée aussi côté Streamlit.)

---

## Plan par phases (ordre conseillé)

**Phase 1 — Infra & feedback** (débloque tout le reste)
- [x] Jobs async + progression (polling) pour génération quiz/exercices, détection notions,
      vérification + barres UI DSFR. Endpoints `POST /…-async` → `job_id` ; suivi via
      `GET /jobs/{id}` (polling) ou `GET /jobs/{id}/stream` (SSE). Voir `backend/app/jobs.py`,
      `backend/app/api/jobs.py`, `frontend/src/services/api.ts` (`runJob`),
      `frontend/src/components/GenerationProgress.vue`.
- [x] Affichage incrémental des items (on_item) : questions & exercices s'affichent au fil
      de l'eau (le métier expose `stream=True` + `on_item`, hors mode batch).
- [ ] Génération en **mode libre (chat)** encore synchrone (`/chat/{id}/generate-quiz`) → à
      passer en async en Phase 4 (mode libre complet).
- [ ] Persistance doc_store/chat_store/**job_store** (Redis ou disque) — **différé** : nécessite
      une décision d'infra (Redis dispo sur le nexus figé ?) ; OK en mono-instance podman pour
      l'instant. Les 3 stores partagent la même limite mémoire mono-instance.

**Phase 2 — Parité quiz & exercices** ✅ (2026-06-18)
- [x] Éditeur de prompts par niveau + règles fixes (quiz & exercices) : `GET /prompts/defaults`,
      params `difficulty_prompts` (quiz) / `custom_exercise_prompts` (exercices) ;
      accordéons `<details>` dans GeneratePage avec reset + note « règles fixes » en lecture seule.
- [x] Consigne libre unifiée : `classify_user_input` (style → `user_instructions`, périmètre →
      `user_context` qui filtre les chunks) via case « Analyser la consigne » ; le périmètre
      détecté s'affiche dans le message du job.
- [x] Affichage sources (doc + pages) + citation dans QuestionCard/ExerciseCard ;
      comptage questions/notion (getter `notionQuestionCounts`, badge « N Q »).
- [x] Édition fine exercices (étapes/blancs/sous-questions avec add/remove) + ajout manuel
      question/exercice (`addQuestion`/`addExercise`).
- [x] Historique des modifications : snapshot avant chaque modif + bouton « ↩ Annuler »
      (`history`/`undo`, profondeur 20).
- [x] Quiz sur base de connaissance LLM (sans document) : `POST /quiz/generate-from-knowledge[-async]`
      (`generate_quiz_from_llm_knowledge`), section dédiée + badge « ⚠️ base LLM » sur les questions.

**Phase 3 — Notions, acronymes, options** ✅ (2026-06-18)
- [x] Notions : ajout/suppression/édition manuelle (titre/catégorie/description), regroupement
      par thématique (toggle), mélange (`notion_mixing`), comptage (Phase 2).
- [x] Acronymes : édition LLM (`POST /acronyms/edit`), toggle actif, ajout/suppression manuelle,
      édition inline sigle/définition.
- [x] Réglages avancés : taille de bloc (chunk), `enable_thinking`, mélange notions, vision
      DPI min/max + pages par bloc, mode One-shot (`extract_oneshot_chunks`). Params Form ajoutés
      à `/documents`.
- [ ] Restent ❌ : parser API externe (vision), suivi de progression spécifique des batchs.

**Phase 4 — Sessions, pool, ateliers**
- [ ] Mode Pool (création + sous-ensemble participant + seuil + réessayer)
- [ ] Sessions avec exercices ; fermeture de session
- [ ] Ateliers complets : 4 onglets, édition + réordonnancement, chat LLM par onglet, import depuis session, fusion d'ateliers
- [ ] Mode libre complet : édition/validation notions, pré-remplissage config, création de session, exercices

**Phase 5 — Compléments & bascule**
- [ ] Guide : points d'intervention + chatbot assistant formateur ; stats en bandeau
- [ ] Vision one-shot + parser API externe ; suivi progression batch
- [ ] Tests d'API ; (auth si besoin)
- [ ] Recette de bout en bout, puis **retrait du service Streamlit** de `compose.yml`

---

## Notes d'implémentation à ne pas oublier
- Endpoints LLM longs → garder `def` (threadpool) tant que Phase 1 pas faite ; sinon timeouts.
- Tout `fetch` passe par `frontend/src/services/api.ts` ; tout `os.getenv` par `backend/app/config.py`.
- Reverse-proxy : back `proxy_pass …/;` (slash final), front sans slash, `--root-path /quizzator-back`.
- Après changement de `frontend/config/.env.production` → **rebuild** l'image frontend.
