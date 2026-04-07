# AGENTS.md — Générateur de Quizz & Exercices IA

Instructions pour les agents IA travaillant sur ce projet.

---

## Exploration rapide de la codebase (onboarding agent IA)

> **Objectif** : comprendre le projet en lisant ce fichier + les fichiers listés ci-dessous, sans exploration itérative.

### Fichiers à lire en priorité (par ordre)

| # | Fichier | Lignes | Rôle |
|---|---------|--------|------|
| 1 | `app.py` | ~2650 | Point d'entrée Streamlit. Auth (désactivé), sidebar, tabs (Exports/Notions/Quizz/Exercices/Analytics/Aperçu/Guide), génération quiz/exercices, mode libre, personas domaine. **Lire en entier.** |
| 2 | `generation/quiz_generator.py` | 459 | Génération QCM : dataclasses Quiz/QuizQuestion, prompts, anti-doublons. **Lire en entier.** |
| 3 | `generation/exercise_generator.py` | 1018 | Génération exercices : dataclass Exercise, 3 types (calcul/trou/cas_pratique), prompts, vérification. **Lire en entier.** |
| 4 | `generation/notion_detector.py` | 319 | Dataclass Notion, détection/fusion/édition notions. **Lire en entier.** |
| 5 | `core/llm_service.py` | 524 | Client LLM unifié : call_llm*, cache, token tracking, vision. **Lire en entier.** |
| 6 | `sessions/session_store.py` | 852 | Backend SQLite : QuizSession, WorkSession, ParticipantResult, pool, CRUD. **Lire en entier.** |
| 7 | `sessions/analytics.py` | 392 | Dashboard Plotly, sélecteur sessions, recommandations IA. **Lire en entier.** |
| 8 | `export/quiz_exporter.py` | 516 | Export HTML/CSV quiz, exercices, combiné. **Lire en entier.** |
| 9 | `processing/document_processor.py` | 850 | Extraction texte multi-format, chunking page/token, vision. **Lire en entier.** |
| 10 | `pages/quiz_session.py` | ~310 | Page participant quiz (pool, scoring, affichage questions manquantes). **Lire en entier.** |
| 11 | `pages/work_session.py` | ~680 | Page Atelier Formateurs : 4 onglets Questions/Exercices/Notions/Outils, chat LLM par onglet, édition, import/fusion, publication. **Lire en entier.** |
| 12 | `core/personas.py` | ~80 | Personas DGFiP par domaine + générique. **Lire en entier.** |
| 13 | `core/auth.py` | ~120 | Auth SQLite PBKDF2 (désactivé temporairement). **Lire en entier.** |
| 14 | `pages/shared_session.py` | ~150 | Page Sessions Partagées (séparée de app.py). **Lire en entier.** |
| 15 | `pages/admin.py` | ~100 | Page admin gestion utilisateurs (désactivé temporairement). **Lire en entier.** |

### Fichiers secondaires (lire si pertinent pour la tâche)

| Fichier | Lignes | Rôle |
|---------|--------|------|
| `core/models.py` | 178 | Modèles Pydantic v2 pour validation JSON LLM |
| `core/llm_cache.py` | 150 | Cache LLM SHA256, LRU, TTL, persistence JSON |
| `core/token_tracker.py` | 65 | Log tokens par appel, résumé agrégé |
| `core/stats_manager.py` | 52 | Stats globales JSON (questions, docs, tokens, sessions) |
| `generation/chat_mode.py` | 601 | Machine à états (ChatState) pour le mode libre IA |
| `generation/quiz_verifier.py` | 371 | Vérification IA des QCM, reformulation auto (max 3) |
| `generation/exercise_verifier.py` | 598 | Vérification IA des exercices trou/cas_pratique |
| `generation/question_editor.py` | 95 | Amélioration IA d'une question individuelle |
| `generation/batch_service.py` | 237 | Traitement par lots ThreadPoolExecutor, retry |
| `generation/calc_agent.py` | 115 | Exécution Python sandboxée pour vérification calculs |
| `processing/vision_processor.py` | 640 | Rendu PDF→images, optimisation DPI, LibreOffice |
| `ui/ui_components.py` | 67 | Composants UI Streamlit réutilisables |
| `templates/quiz_template.html` | — | Template Jinja2 pour export HTML |

### Dataclasses principales

```python
# generation/quiz_generator.py:22
@dataclass
class QuizQuestion:
    question: str
    choices: Dict[str, str]       # {"A": "...", "B": "..."}
    correct_answers: List[str]    # ["A", "C"]
    explanation: str = ""
    source_pages: List[int]
    difficulty_level: str = ""    # "facile" | "moyen" | "difficile"
    source_document: str = ""
    citation: str = ""
    related_notions: List[str]    # Titres des notions couvertes

# generation/quiz_generator.py:36
@dataclass
class Quiz:
    title: str
    difficulty: str
    questions: List[QuizQuestion]
    metadata: dict

# generation/exercise_generator.py:287
@dataclass
class Exercise:
    statement: str
    expected_answer: str          # Réponse numérique (type "calcul")
    steps: List[str]              # Étapes de résolution
    num_steps: int = 0
    correction: str = ""
    verification_code: str = ""   # Code Python (type "calcul")
    verified: bool = False
    verification_output: str = ""
    source_pages: List[int]
    source_document: str = ""
    citation: str = ""
    difficulty_level: str = "moyen"
    related_notions: List[str]
    exercise_type: str = "calcul" # "calcul" | "trou" | "cas_pratique"
    blanks: List[dict]            # Pour type "trou"
    sub_questions: List[dict]     # Pour type "cas_pratique"
    sub_parts: List[dict]         # Multi-questions calcul

# generation/notion_detector.py:16
@dataclass
class Notion:
    title: str
    description: str
    source_document: str = ""
    source_pages: List[int]
    enabled: bool = True
    category: str = ""
    question_count: int = 0

# processing/document_processor.py:29
@dataclass
class TextChunk:
    text: str
    source_pages: List[int]
    token_count: int = 0
    source_document: str = ""
    page_images: List[str]        # base64 images pour vision

# sessions/session_store.py:26,41,57
@dataclass
class WorkSession:
    work_session_id, work_code, title, draft_quiz_json, draft_notions_json,
    owner_name, last_modified, created_at, status, draft_exercises_json, original_quiz_json

@dataclass
class QuizSession:
    session_id, session_code, title, quiz_json, notions_json, created_at,
    is_active, pool_json, subset_size, pass_threshold, exercises_json

@dataclass
class ParticipantResult:
    result_id, session_id, participant_name, answers_json, score, total,
    per_question_json, submitted_at

# core/auth.py (désactivé temporairement)
@dataclass
class User:
    user_id, username, display_name, role, created_at
```

### Constantes importantes

| Constante | Fichier:ligne | Valeur / Usage |
|-----------|---------------|----------------|
| `QUIZ_DEFAULT_PERSONA` | `quiz_generator.py:45` | Persona par défaut quiz (modifiable UI) |
| `QUIZ_FIXED_RULES_DISPLAY` | `quiz_generator.py:52` | Règles fixes affichées en lecture seule |
| `DIFFICULTY_PROMPTS` | `quiz_generator.py:62` | Dict facile/moyen/difficile → instructions LLM |
| `EXERCISE_DEFAULT_PERSONA` | `exercise_generator.py:114` | Persona par défaut exercices |
| `EXERCISE_FIXED_RULES_BY_TYPE` | `exercise_generator.py:171` | Dict par type → règles fixes |
| `DEFAULT_EXERCISE_PROMPTS` | `exercise_generator.py:257` | Dict facile/moyen/difficile (type calcul) |
| `DEFAULT_EXERCISE_PROMPTS_TROU` | `exercise_generator.py:245` | Instructions par niveau (type trou) |
| `DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE` | `exercise_generator.py:251` | Instructions par niveau (type cas pratique) |
| `TEXT_MODEL_NAME` | `llm_service.py:27` | Modèle texte par défaut (env `TEXT_MODEL_NAME`, rétro-compat `MODEL_NAME`) |
| `TEXT_MODEL_CONTEXT` | `llm_service.py:28` | Fenêtre de contexte texte (env `TEXT_MODEL_CONTEXT`, rétro-compat `MODEL_CONTEXT_WINDOW`) |
| `VISION_MODEL_NAME` | `llm_service.py:40` | Modèle vision (env `VISION_MODEL_NAME`) |
| `VISION_MODEL_CONTEXT` | `llm_service.py:41` | Fenêtre de contexte vision (env `VISION_MODEL_CONTEXT`, défaut 262000) |
| `VISION_MODEL_NAMES` | `llm_service.py:35` | Liste modèles vision (JSON ou string) |
| `ONESHOT_RESERVE_TOKENS` | `llm_service.py` | 50000 — tokens réservés pour prompts en mode one-shot |
| `ONESHOT_DPI` | `llm_service.py` | 85 — DPI fixe en mode one-shot |
| `ONESHOT_SLICE_TOKENS` | `llm_service.py` | 50000 — taille des tranches si document trop gros |
| `DB_PATH` | `session_store.py:22` | Chemin SQLite (env `QUIZ_SESSIONS_DB`) |

### Index des fonctions clés par fichier

**`core/llm_service.py`** : `call_llm()`, `call_llm_json()`, `call_llm_chat()`, `call_llm_chat_json()`, `call_llm_vision()`, `call_llm_vision_json()`, `call_llm_stream()`, `call_llm_vision_stream()`, `call_llm_json_stream()`, `count_tokens()`, `list_models()`, `get_model_info()`

**`generation/quiz_generator.py`** : `generate_quiz()`, `generate_quiz_from_chunk()`, `_build_quiz_prompt()`, `_parse_quiz_questions()`, `_distribute_questions()`

**`generation/exercise_generator.py`** : `generate_exercises()`, `generate_exercises_from_chunk()`, `_build_exercise_prompt()`, `_verify_exercise_with_agent()`, `_verify_exercise_direct()`, `_correct_exercise_with_llm()`, `_verify_and_correct_exercise()`

**`generation/notion_detector.py`** : `detect_notions()`, `edit_notions_with_llm()`, `merge_similar_notions()`, `notions_to_prompt_text()`

**`generation/chat_mode.py`** : `init_session()`, `process_user_message()`, `generate_notions_from_chat()`, `extract_generation_config()`, `generate_quiz_direct()`, `generate_exercises_direct()`

**`generation/quiz_verifier.py`** : `verify_quiz()`, `_verify_question_with_llm()`, `_reformulate_question()`

**`generation/exercise_verifier.py`** : `verify_exercises()`, `_verify_trou_with_llm()`, `_verify_cas_pratique_with_llm()`, `_verify_with_calc_agent()`, `_reformulate_exercise()`

**`export/quiz_exporter.py`** : `export_quiz_html()`, `export_quiz_csv()`, `export_exercises_html()`, `export_exercises_csv()`, `export_combined_html()`, `export_combined_csv()`

**`sessions/session_store.py`** : `init_db()`, `create_session()`, `get_session()`, `submit_result()`, `get_session_results()`, `get_session_analytics()`, `deactivate_session()`, `list_sessions()`, `create_pool_session()`, `get_next_subset()`, `create_work_session()`, `get_work_session()`, `update_work_session_draft()`, `publish_work_session()`, `list_work_sessions()`

**`sessions/analytics.py`** : `render_analytics_dashboard()`, `render_global_metrics()`, `render_per_question_chart()`, `render_per_notion_chart()`, `render_participant_table()`, `render_session_selector()`, `generate_ai_recommendations()`

**`core/personas.py`** : `get_persona_for_domain()`, `PERSONA_DOMAINS`, `DGFIP_PERSONAS`, `DEFAULT_PERSONA_GENERIC`

**`core/auth.py`** *(désactivé)* : `authenticate()`, `create_user()`, `list_users()`, `update_user_role()`, `delete_user()`, `change_password()`

**`processing/document_processor.py`** : `extract_and_chunk()`, `extract_and_chunk_multiple()`, `extract_and_chunk_vision()`, `extract_and_chunk_multiple_vision()`, `extract_and_chunk_vision_text()`, `extract_oneshot_chunks()`, `extract_text_from_file()`, `chunk_text()`, `split_into_pages()`, `get_text_stats()`, `get_text_stats_multiple()`

### Structure de app.py (sections par numéro de ligne approximatif)

| Lignes | Section |
|--------|---------|
| 1-77 | Imports, st.set_page_config, auth gate (désactivé), CSS |
| 178-230 | Initialisation session_state (18 variables) |
| 232-456 | **Sidebar** : page links, mode radio, file upload (avec cache persistant entre pages), options avancées (batch/vision/thinking), modèle LLM, stats globales |
| 457-714 | Traitement document : extraction, chunking, vision, DPI, aperçu |
| 715 | **Tabs** : Notions, Quizz, Exercices, Aperçu texte, Guide |
| 717-835 | Onglet Notions : détection, affichage, édition, fusion |
| 836-1001 | Onglet Quizz : config (difficulté, choix, persona), génération |
| 1002-1286 | Onglet Quizz : affichage questions, édition, vérification IA, changelog |
| 1287-1470 | Onglet Quizz : export tabs (téléchargements, session partagée, atelier) |
| 1471-1760 | Onglet Exercices : config, génération, affichage, vérification |
| 1761-1870 | Onglet Exercices : export tabs |
| 1871-2155 | Onglets Aperçu texte et Guide |
| 2156-2539 | **Mode libre (IA)** : chat, génération directe quiz/exercices |
| 2540-2650 | **Mode libre (IA)** suite : exports, sessions partagées |

---

## Vue d'ensemble

Application **Streamlit** de génération de quizz QCM et d'exercices à partir de documents (PDF, DOCX, ODT, PPTX, TXT) ou par conversation libre avec un LLM. Backend LLM via API compatible OpenAI (locale ou cloud). Inclut un système de sessions partagées (étudiantes et collaboratives), un pipeline de vérification automatique et des outils d'édition interactive.

---

## Arborescence du projet

```text
generateur_de_quizz/
├── app.py                        ← point d'entrée Streamlit (racine obligatoire)
├── pages/
│   ├── quiz_session.py           ← page participant (quizz partagé / pool, questions manquantes)
│   ├── work_session.py           ← page Atelier Formateurs (4 onglets : Questions/Exercices/Notions/Outils, chat LLM)
│   ├── shared_session.py         ← page Sessions Partagées (séparée de app.py)
│   └── admin.py                  ← page admin gestion utilisateurs (désactivé)
├── templates/quiz_template.html  ← template Jinja2 pour export HTML
├── shared_data/                  ← données persistantes (SQLite, stats JSON, cache LLM)
├── core/
│   ├── llm_service.py            ← client LLM (cache SHA256, retry, token tracking, enable_thinking)
│   ├── llm_cache.py              ← cache LLM : SHA256 key, LRU eviction, TTL, persistence JSON
│   ├── token_tracker.py          ← suivi tokens par appel (log_token_usage, get_token_summary)
│   ├── models.py                 ← modèles Pydantic v2 (QuizQuestionModel, ExerciseModel, NotionModel...)
│   ├── stats_manager.py          ← statistiques globales (questions, docs, tokens, sessions)
│   ├── personas.py               ← personas DGFiP par domaine + générique
│   └── auth.py                   ← auth SQLite PBKDF2 (désactivé temporairement)
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
- **Réparation JSON** : Si le JSON est invalide après le premier essai, le JSON cassé est envoyé au LLM avec une instruction de correction (au lieu de relancer le même prompt).
- **Streaming** : `call_llm_stream()`, `call_llm_vision_stream()` yields les fragments de texte. `call_llm_json_stream()` accumule le flux et extrait les objets JSON complets via `_extract_complete_json_objects()`. Fallback automatique vers non-streaming si l'API ne le supporte pas.
- **Mode One-shot** : `extract_oneshot_chunks()` dans `document_processor.py` crée le minimum de chunks pour envoyer tout en une requête vision (DPI 85, 262k tokens). Découpe automatiquement si trop gros.
- **Variables d'env** : Les nouvelles constantes sont `TEXT_MODEL_NAME`, `TEXT_MODEL_CONTEXT`, `VISION_MODEL_CONTEXT`. Les anciens noms (`MODEL_NAME`, `MODEL_CONTEXT_WINDOW`, `VISION_CONTEXT_WINDOW`) sont supportés par rétro-compatibilité via aliases.

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
- Interface en **4 onglets** : Questions / Exercices / Notions / Outils (diff, import, fusion, publication).
- **Chat LLM** dans chaque onglet de contenu (Questions, Exercices, Notions) : instruction en langage naturel → le LLM modifie la liste complète.
- Onglet Notions : affichage groupé par catégorie/thème, toggle actif/inactif, édition (titre, description, catégorie, source), ajout manuel.
- Export notions enrichi (`category`, `source_document`, `source_pages`) + bouton d'export dédié dans app.py.
- Affichage complet des exercices par type (calcul/trou/cas_pratique) avec badges, notions, sources, édition inline.
- Questions réordonnables (monter/descendre), supprimables, éditables (difficulté incluse).
- Import/fusion depuis sessions et ateliers : récupère questions, exercices **et notions** (dédoublonnage par titre).
- Modèle de concurrence simple : "dernier à sauvegarder gagne" — `update_work_session_draft()` est atomique + horodaté.
- `publish_work_session()` crée une `QuizSession` étudiante depuis le brouillon.
- **Auto-remplissage** : après création d'un atelier depuis l'onglet Exports, le code est auto-rempli dans le champ `export_ws_code` pour permettre l'export direct des exercices.

### Changelog des questions

`st.session_state._quiz_changelog` est une liste d'entrées `{"type", "idx", "question_before", "question_after", "timestamp"}`. Alimenté par : édition manuelle, amélioration IA (`question_editor.py`), reformulation lors de la vérification (`quiz_verifier.py`), suppressions. Affiché dans "📜 Historique des modifications".

### UI (app.py)

- Langue : **français** partout.
- Barres de progression style **tqdm avec ETA**.
- Pas d'affichage des infos du modèle dans la sidebar.
- Graphiques via **Plotly** (pas de tables simples pour les analytics).
- Badges de notions affichés en **pills violettes**.
- **7 onglets en mode document** : Exports / Notions / Quizz / Exercices / Analytics / Aperçu texte / Guide.
- Sidebar : sélecteur de mode (Document / Libre) + liens pages (Ateliers, Sessions Partagées) + stats globales.
- **Personas domaine** : sélecteur DGFiP (8 domaines) + Générique + Personnalisé (`core/personas.py`).
- **Humour** : toggle dans config quiz, ajoute une mauvaise réponse décalée par question.
- **Accumulation quiz** : les générations s'ajoutent au quiz existant (bouton Réinit. pour remettre à zéro).
- **Notions manquantes** : bouton dédié "🎯 Notions manquantes" pour générer uniquement sur les notions non couvertes.
- **Auth** : système login/rôles désactivé temporairement (code commenté dans app.py, work_session.py).
- **Persistance documents** : les fichiers uploadés sont cachés dans `session_state["_uploaded_files_cache"]` (bytes + noms) pour survivre à la navigation entre pages.
- **Quiz session** : les questions non remplies sont affichées par numéro dans un warning, bouton de soumission désactivé tant que tout n'est pas répondu.
- **Tag version** : popover `v3.1` en haut de page avec changelog complet (v1 → v2 → v3.0 → v3.1).

### Sécurité

- L'exécution du code Python des exercices se fait dans un **sous-processus isolé** avec timeout 30s — ne pas changer ce mécanisme.
- Le scoring des sessions partagées est calculé **côté serveur** — les bonnes réponses ne doivent jamais être envoyées au client.

---

## Configuration

Fichier `.env` à la racine (copier depuis `.env.example`) :

```ini
OPENAI_API_BASE=http://...
OPENAI_API_KEY=sk-...
TEXT_MODEL_NAME=...
TEXT_MODEL_CONTEXT=32000
TIKTOKEN_ENCODING=cl100k_base
VISION_MODEL_NAME=Qwen3-VL-32B-Instruct-FP8
VISION_MODEL_CONTEXT=262000
QUIZ_SESSIONS_DB=shared_data/quiz_sessions.db
GLOBAL_STATS=shared_data/global_stats.json
```

Note : les anciens noms `MODEL_NAME`, `MODEL_CONTEXT_WINDOW`, `VISION_CONTEXT_WINDOW` sont encore supportés par rétro-compatibilité.

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
