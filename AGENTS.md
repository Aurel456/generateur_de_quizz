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
├── shared_data/                  ← données persistantes (SQLite, stats JSON)
├── core/
│   ├── llm_service.py            ← client LLM (call_llm, call_llm_json, call_llm_chat, call_llm_vision)
│   └── stats_manager.py          ← statistiques globales (questions, docs, tokens, sessions)
├── processing/
│   ├── document_processor.py     ← extraction texte multi-format + chunking
│   └── vision_processor.py       ← rendu PDF→images via PyMuPDF, optimisation DPI
├── generation/
│   ├── quiz_generator.py         ← génération QCM — anti-doublons, variable_correct, persona
│   ├── quiz_verifier.py          ← vérification IA des QCM, reformulation auto (max 3 essais)
│   ├── exercise_generator.py     ← génération exercices — 3 types, persona séparé des règles fixes
│   ├── question_editor.py        ← amélioration LLM d'une question existante (improve_question_with_llm)
│   ├── notion_detector.py        ← détection, édition, fusion des notions fondamentales
│   ├── chat_mode.py              ← machine à états (ChatState) pour le mode libre
│   └── batch_service.py          ← traitement par lots (ThreadPoolExecutor)
├── export/
│   └── quiz_exporter.py          ← export HTML (Jinja2) et CSV
├── sessions/
│   ├── session_store.py          ← backend SQLite (sessions étudiantes + pool + ateliers formateurs)
│   └── analytics.py              ← dashboard Plotly (graphiques par question, par notion, classement)
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

### Structures de données clés

- `QuizQuestion` et `Exercise` ont un champ `related_notions: List[str]`.
- `QuizSession` a des champs optionnels `pool_json`, `subset_size`, `pass_threshold` pour le mode pool.
- `WorkSession` est le brouillon collaboratif formateurs (table `work_sessions` dans SQLite).
- Les chunks de texte portent des marqueurs `[Début Page X] ... [Fin Page X]` pour la traçabilité des sources.

### Structure des prompts (quiz et exercices)

Les prompts sont organisés en 3 couches séparées :

1. **Persona** (modifiable par le formateur) — ex: "Tu es un expert en droit fiscal"
2. **Règles fixes** (affichées en lecture seule dans l'UI) — garantissent la qualité et la stabilité du parsing JSON
3. **Instructions par niveau de difficulté** (modifiables) — définissent le comportement pour Facile/Moyen/Difficile

Constantes dans `quiz_generator.py` : `QUIZ_DEFAULT_PERSONA`, `QUIZ_FIXED_RULES`
Constantes dans `exercise_generator.py` : `EXERCISE_DEFAULT_PERSONA`, `EXERCISE_FIXED_RULES_BY_TYPE` (dict par type)

### Types d'exercices

Trois types supportés : `"calcul"` (vérification Python), `"trou"` (JSON `blanks`), `"cas_pratique"` (JSON `sub_questions`).
Les types `trou` et `cas_pratique` n'ont pas de vérification Python automatique (`verified=True` avec note manuelle).

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
- **Batch API** : le toggle est dans la sidebar de `app.py`. Les fonctions batch sont dans `batch_service.py` et appelées conditionnellement depuis `quiz_generator.py`, `exercise_generator.py`, `quiz_verifier.py` et `chat_mode.py`.
- **Stats globales** : utiliser `increment_stats(questions=N, documents=N, tokens=N, sessions=N)` depuis `core/stats_manager.py`. Appeler `increment_stats(sessions=1)` à chaque création de session étudiante.

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
