# AGENTS.md — Générateur de Quizz & Exercices IA

Instructions pour les agents IA travaillant sur ce projet.

---

## Vue d'ensemble

Application **Streamlit** de génération de quizz QCM et d'exercices mathématiques/logiques à partir de documents (PDF, DOCX, ODT, PPTX, TXT) ou par conversation libre avec un LLM. Backend LLM via API compatible OpenAI (locale ou cloud).

---

## Arborescence du projet

```text
generateur_de_quizz/
├── app.py                        ← point d'entrée Streamlit (racine obligatoire)
├── pages/quiz_session.py         ← page participant (racine obligatoire Streamlit)
├── templates/quiz_template.html  ← template Jinja2 pour export HTML
├── shared_data/                  ← données persistantes (SQLite, stats JSON)
├── core/                         ← infrastructure de base
│   ├── llm_service.py            ← client LLM (call_llm, call_llm_json, call_llm_chat, call_llm_vision)
│   └── stats_manager.py          ← statistiques globales persistantes (JSON)
├── processing/                   ← traitement des documents
│   ├── document_processor.py     ← extraction texte multi-format + chunking
│   └── vision_processor.py       ← rendu PDF→images via PyMuPDF, optimisation DPI
├── generation/                   ← génération IA
│   ├── quiz_generator.py         ← génération QCM — QuizQuestion avec related_notions
│   ├── quiz_verifier.py          ← vérification IA des QCM, reformulation auto (max 3 essais)
│   ├── exercise_generator.py     ← génération exercices — DEFAULT_EXERCISE_PROMPTS + EXERCISE_JSON_FORMAT fixe
│   ├── notion_detector.py        ← détection, édition, fusion des notions fondamentales
│   ├── chat_mode.py              ← machine à états (ChatState) pour le mode libre
│   └── batch_service.py          ← traitement par lots (ThreadPoolExecutor)
├── export/                       ← exports
│   └── quiz_exporter.py          ← export HTML (Jinja2) et CSV
├── sessions/                     ← sessions partagées & analytics
│   ├── session_store.py          ← backend SQLite (shared_data/quiz_sessions.db)
│   └── analytics.py              ← dashboard Plotly (graphiques par question, par notion, classement)
└── ui/                           ← composants UI Streamlit
    └── ui_components.py          ← badges difficulté, stat cards, sources
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
- Les prompts d'exercices sont dans `DEFAULT_EXERCISE_PROMPTS` (dict par niveau). Le bloc `EXERCISE_JSON_FORMAT` est **fixe et non modifiable** (garantit le parsing stable).
- Les chunks de texte portent des marqueurs `[Début Page X] ... [Fin Page X]` pour la traçabilité des sources.

### UI (app.py)
- Langue : **français** partout.
- Barres de progression style **tqdm avec ETA**.
- Pas d'affichage des infos du modèle dans la sidebar.
- Graphiques via **Plotly** (pas de tables simples pour les analytics).
- Badges de notions affichés en **pills violettes**.
- 5 onglets en mode document : Notions / Quizz / Exercices / Analytics / Aperçu texte.

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
```

---

## Lancer l'application

```bash
streamlit run app.py
```

---

## Points d'attention pour les modifications

- **Modifier les prompts** : les prompts utilisateur sont dans `quiz_generator.py`, `exercise_generator.py`, `notion_detector.py` et `chat_mode.py`. Le bloc JSON format dans `exercise_generator.py` ne doit pas être éditable par l'utilisateur.
- **Ajouter un format de fichier** : modifier `document_processor.py` (extraction texte) et mettre à jour les extensions acceptées dans `app.py`.
- **Modifier les exports** : `quiz_exporter.py` + `templates/quiz_template.html` pour l'HTML ; le CSV est construit directement dans `quiz_exporter.py`.
- **Sessions partagées** : toute la logique DB est dans `session_store.py` (SQLite). Le schéma est créé automatiquement au premier lancement.
- **Batch API** : le toggle est dans la sidebar de `app.py`. Les fonctions batch sont dans `batch_service.py` et appelées conditionnellement depuis `quiz_generator.py`, `exercise_generator.py`, `quiz_verifier.py` et `chat_mode.py`.

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
