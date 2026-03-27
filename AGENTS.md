# AGENTS.md — Générateur de Quizz & Exercices IA

Instructions pour les agents IA travaillant sur ce projet.

---

## Vue d'ensemble

Application **Streamlit** de génération de quizz QCM et d'exercices à partir de documents (PDF, DOCX, ODT, PPTX, TXT) ou par conversation libre avec un LLM. Backend LLM via API compatible OpenAI (locale ou cloud). Inclut un système de sessions partagées (étudiantes et collaboratives), un pipeline de vérification automatique et des outils d'édition interactive.

---

## Arborescence du projet

```text
generateur_de_quizz/
├── app.py                        ← point d'entrée Streamlit (racine obligatoire)
├── pages/
│   ├── quiz_session.py           ← page participant (quizz partagé / pool)
│   └── work_session.py           ← page Atelier Formateurs (collaborative)
├── templates/quiz_template.html  ← template Jinja2 pour export HTML
├── shared_data/                  ← données persistantes (SQLite, stats JSON, cache LLM)
├── core/
│   ├── llm_service.py            ← client LLM (cache SHA256, retry, token tracking, enable_thinking)
│   ├── llm_cache.py              ← cache LLM : SHA256 key, LRU eviction, TTL, persistence JSON
│   ├── token_tracker.py          ← suivi tokens par appel (log_token_usage, get_token_summary)
│   ├── models.py                 ← modèles Pydantic v2 (QuizQuestionModel, ExerciseModel, NotionModel...)
│   └── stats_manager.py          ← statistiques globales (questions, docs, tokens, sessions)
├── processing/
│   ├── document_processor.py     ← extraction texte multi-format + chunking
│   └── vision_processor.py       ← rendu PDF→images via PyMuPDF, optimisation DPI
├── generation/
│   ├── quiz_generator.py         ← génération QCM — anti-doublons, variable_correct, persona
│   ├── quiz_verifier.py          ← vérification IA des QCM, reformulation auto (max 3 essais)
│   ├── exercise_generator.py     ← génération exercices — 3 types, persona séparé des règles fixes
│   ├── exercise_verifier.py      ← vérification IA des exercices trou/cas_pratique (verify→reformulate→delete)
│   ├── question_editor.py        ← amélioration LLM d'une question existante (improve_question_with_llm)
│   ├── notion_detector.py        ← détection, édition, fusion des notions fondamentales
│   ├── chat_mode.py              ← machine à états (ChatState) pour le mode libre
│   └── batch_service.py          ← traitement par lots (ThreadPoolExecutor, retry par requête, BatchResult)
├── export/
│   └── quiz_exporter.py          ← export HTML/CSV (quiz, exercices, combiné quiz+exercices)
├── sessions/
│   ├── session_store.py          ← backend SQLite (sessions + exercices + ateliers formateurs)
│   └── analytics.py              ← dashboard Plotly + recommandations IA (generate_ai_recommendations)
├── tests/                        ← tests unitaires (pytest, 51 tests)
│   ├── conftest.py               ← fixtures partagées (sample data)
│   ├── test_llm_cache.py         ← cache LRU, TTL, persistence
│   ├── test_llm_service.py       ← parsing JSON, count_tokens
│   ├── test_token_tracker.py     ← log, summary, reset
│   ├── test_models.py            ← validation Pydantic (quiz, exercice, notion)
│   ├── test_session_store.py     ← CRUD SQLite, analytics
│   └── test_quiz_exporter.py     ← HTML/CSV, export combiné
└── ui/
    └── ui_components.py          ← badges difficulté, stat cards, render_guide_tab()
```

---

## Conventions de code

### Appels LLM

- Toujours passer par `llm_service.py` — ne jamais appeler `openai` directement depuis les autres modules.
- Pas de `max_tokens` envoyé à l'API par défaut (réponses longues autorisées).
- `call_llm_json` / `call_llm_chat_json` gèrent le retry automatique (jusqu'à 3 fois) si le JSON est invalide.
- `call_llm_vision` / `call_llm_vision_json` pour les requêtes avec images base64.
- **Cache** : `call_llm()` et `call_llm_json()` utilisent le cache SHA256 par défaut (`use_cache=True`). Ne PAS cacher `call_llm_chat` (contexte conversationnel) ni `call_llm_vision` (images trop lourdes).
- **enable_thinking** : Toutes les fonctions `call_llm*` acceptent `enable_thinking: bool` (défaut `True` pour texte, `False` pour vision). Passe `extra_body={"enable_thinking": ..., "chat_template_kwargs": {"enable_thinking": ...}}` pour les modèles Qwen.
- **Token tracking** : Tous les appels sont tracés automatiquement via `log_token_usage()` dans `_execute_completion()`.
- **Parsing JSON résilient** : `_parse_json_response()` tente 3 stratégies (direct, bloc markdown, extraction braces).

### Structures de données clés

- `QuizQuestion` et `Exercise` ont un champ `related_notions: List[str]`.
- `Exercise` a un champ `verification_code: str` pour les cas pratiques avec calculs.
- `QuizSession` a des champs optionnels `pool_json`, `subset_size`, `pass_threshold` pour le mode pool, et `exercises_json` pour stocker les exercices.
- `WorkSession` est le brouillon collaboratif formateurs (table `work_sessions` dans SQLite), avec `draft_exercises_json`.
- Les chunks de texte portent des marqueurs `[Début Page X] ... [Fin Page X]` pour la traçabilité des sources.
- **Modèles Pydantic v2** (`core/models.py`) : `QuizQuestionModel`, `ExerciseModel`, `NotionModel` etc. Utilisés pour valider les réponses JSON du LLM avant conversion vers les dataclasses existants (`model_validate()` → `model_dump()`). Migration graduelle — ne pas remplacer les dataclasses existants.

### Structure des prompts (quiz et exercices)

Les prompts sont organisés en 3 couches séparées :

1. **Persona** (modifiable par le formateur) — ex: "Tu es un expert en droit fiscal"
2. **Règles fixes** (affichées en lecture seule dans l'UI) — garantissent la qualité et la stabilité du parsing JSON
3. **Instructions par niveau de difficulté** (modifiables) — définissent le comportement pour Facile/Moyen/Difficile

Constantes dans `quiz_generator.py` : `QUIZ_DEFAULT_PERSONA`, `QUIZ_FIXED_RULES`
Constantes dans `exercise_generator.py` : `EXERCISE_DEFAULT_PERSONA`, `EXERCISE_FIXED_RULES_BY_TYPE` (dict par type)

### Types d'exercices

Trois types supportés : `"calcul"` (vérification Python), `"trou"` (JSON `blanks`), `"cas_pratique"` (JSON `sub_questions`).

**Vérification par type :**

- `calcul` : Vérification par exécution Python (subprocess isolé) + auto-correction LLM.
- `trou` : Vérification par LLM (le LLM remplit les blancs depuis le document source, comparaison flexible, seuil 70%).
- `cas_pratique` : Vérification par LLM (le LLM répond aux sous-questions) + exécution du `verification_code` s'il existe.

Le module `exercise_verifier.py` gère la boucle vérifier → reformuler (max 3 tentatives) → supprimer pour trou et cas_pratique. Les exercices calcul sont vérifiés directement dans `exercise_generator.py`.

### Accumulation des exercices

Les générations successives s'ajoutent aux exercices existants (`st.session_state.exercises + new`). Bouton "Effacer tout" pour réinitialiser. Même logique pour le mode document et le mode libre.

### Sessions étudiantes

- **Mode standard** : toutes les questions, scoring direct.
- **Mode pool** : `pool_json` contient toutes les questions, `subset_size` définit la taille du sous-ensemble par participant. `_sample_subset_by_difficulty()` tire proportionnellement par difficulté. `get_next_subset()` exclut les questions déjà vues (tracées dans `seen_question_indices` par participant).

### Ateliers formateurs (work sessions)

- Table `work_sessions` dans SQLite, accès via `work_session.py` (Streamlit multipage).
- Modèle de concurrence simple : "dernier à sauvegarder gagne" — `update_work_session_draft()` est atomique + horodaté.
- `publish_work_session()` crée une `QuizSession` étudiante depuis le brouillon.

### Changelog des questions

`st.session_state._quiz_changelog` est une liste d'entrées `{"type", "idx", "question_before", "question_after", "timestamp"}`. Alimenté par : édition manuelle, amélioration IA (`question_editor.py`), reformulation lors de la vérification (`quiz_verifier.py`), suppressions. Affiché dans "📜 Historique des modifications".

### UI (app.py)

- Langue : **français** partout.
- Barres de progression style **tqdm avec ETA**.
- Pas d'affichage des infos du modèle dans la sidebar.
- Graphiques via **Plotly** (pas de tables simples pour les analytics).
- Badges de notions affichés en **pills violettes**.
- **6 onglets en mode document** : Notions / Quizz / Exercices / Analytics / Aperçu texte / Guide.
- Sidebar : sélecteur de mode (Document / Libre / Sessions Partagées / Ateliers Formateurs) + stats globales (questions, docs, tokens, sessions).

### Sécurité

- L'exécution du code Python des exercices se fait dans un **sous-processus isolé** avec timeout 30s — ne pas changer ce mécanisme.
- Le scoring des sessions partagées est calculé **côté serveur** — les bonnes réponses ne doivent jamais être envoyées au client.

---

## Configuration

Fichier `.env` à la racine (copier depuis `.env.example`) :

```ini
OPENAI_API_BASE=http://...
OPENAI_API_KEY=sk-...
MODEL_NAME=...
MODEL_CONTEXT_WINDOW=32000
TIKTOKEN_ENCODING=cl100k_base
VISION_MODEL_NAME=Qwen3-VL-32B-Instruct-FP8
VISION_CONTEXT_WINDOW=80000
QUIZ_SESSIONS_DB=shared_data/quiz_sessions.db
GLOBAL_STATS=shared_data/global_stats.json
```

---

## Lancer l'application

```bash
streamlit run app.py
```

---

## Points d'attention pour les modifications

- **Modifier les prompts quiz** : `quiz_generator.py` — `QUIZ_DEFAULT_PERSONA` (persona), `QUIZ_FIXED_RULES` (règles fixes), `_build_quiz_prompt()` prend `persona`, `existing_questions`, `variable_correct`.
- **Modifier les prompts exercices** : `exercise_generator.py` — `EXERCISE_DEFAULT_PERSONA`, `EXERCISE_FIXED_RULES_BY_TYPE`, `DEFAULT_EXERCISE_PROMPTS` / `DEFAULT_EXERCISE_PROMPTS_TROU` / `DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE` (instructions par niveau uniquement). `_build_exercise_prompt()` prend `persona` et `exercise_type`.
- **Amélioration IA d'une question** : `generation/question_editor.py` → `improve_question_with_llm(question, instruction, source_text, model)`.
- **Ajouter un format de fichier** : modifier `document_processor.py` et les extensions acceptées dans `app.py`.
- **Modifier les exports** : `quiz_exporter.py` + `templates/quiz_template.html`. Pour les nouveaux types d'exercices, adapter l'affichage dans `quiz_exporter.py`.
- **Sessions partagées** : toute la logique DB est dans `session_store.py` (SQLite WAL mode). Le schéma évolue via `ALTER TABLE` backward-compatible dans `init_db()`.
- **Nouvelles migrations SQLite** : toujours utiliser `try/except` autour des `ALTER TABLE` dans `init_db()` (les colonnes peuvent déjà exister).
- **Ateliers formateurs** : logique dans `session_store.py` (fonctions `*_work_session*`), UI dans `pages/work_session.py`.
- **Batch API** : le toggle est dans la sidebar de `app.py`. Les fonctions batch sont dans `batch_service.py` et appelées conditionnellement depuis `quiz_generator.py`, `exercise_generator.py`, `quiz_verifier.py` et `chat_mode.py`. `BatchResult` dataclass retourne `results`, `failures` et `retry_count`.
- **Stats globales** : utiliser `increment_stats(questions=N, documents=N, tokens=N, sessions=N)` depuis `core/stats_manager.py`. Appeler `increment_stats(sessions=1)` à chaque création de session étudiante.
- **Cache LLM** : `core/llm_cache.py`. Instance globale via `get_cache()`. Clé SHA256 des paramètres, LRU (max 500), TTL (1h), persistence vers `shared_data/llm_cache.json`. Ne PAS cacher les appels chat ou vision.
- **Token tracker** : `core/token_tracker.py`. Appelé automatiquement par `_execute_completion()`. `get_token_summary()` pour les stats agrégées. `reset_token_log()` pour les tests.
- **Modèles Pydantic** : `core/models.py`. Utiliser `validate_quiz_question(data)` et `validate_exercise(data)` pour valider les JSON du LLM. Lèvent `ValidationError` si invalide.
- **Vérification exercices** : `generation/exercise_verifier.py`. `verify_exercises(exercises, chunks, model)` retourne `(exercises_ok, results)`. Pattern identique à `quiz_verifier.py`.
- **Export combiné** : `quiz_exporter.py` — `export_combined_html(quiz, exercises)` et `export_combined_csv(quiz, exercises)`.
- **enable_thinking** : Toujours propager `enable_thinking=st.session_state.get("enable_thinking", True)` lors des appels de génération depuis `app.py`. Le paramètre est accepté par toutes les fonctions publiques de generation/.
- **Tests** : `python -m pytest tests/ -v`. Ajouter des tests dans `tests/` pour tout nouveau module. Fixtures dans `conftest.py`.

---

## Gestion Git

### Branche

Travailler directement sur `main`.

### Fichiers à ne jamais committer

Au-delà du `.gitignore`, ne jamais stager :

- `.env` (clés API)
- `shared_data/quiz_sessions.db` (données utilisateurs)
- tout fichier uploadé temporairement

### Convention des messages de commit

Format : `<type>: <description courte en français>`

| Type | Usage |
| --- | --- |
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `refactor` | Refactoring sans changement de comportement |
| `docs` | Mise à jour README, AGENTS.md ou commentaires |
| `chore` | Dépendances, config, fichiers non-source |

Exemple : `feat: ajout export PDF des exercices`

### Workflow de fin de session (obligatoire)

Avant chaque commit de fin de session :

1. Mettre à jour `README.md` si des fonctionnalités ont changé (nouvelles features, options, comportements).
2. Mettre à jour `AGENTS.md` si l'architecture, les conventions ou les fichiers clés ont évolué.
3. Stager uniquement les fichiers pertinents — **ne pas utiliser `git add -A` ou `git add .`** sans vérification préalable.
4. Créer le commit avec le bon préfixe.

```bash
git status                        # vérifier ce qui a changé
git add app.py quiz_generator.py  # stager fichier par fichier
git add README.md AGENTS.md       # inclure la doc mise à jour
git commit -m "feat: ..."
```
