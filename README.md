# 📝 Générateur de Quizz & Exercices IA (Streamlit + LangGraph)

Application Streamlit permettant de générer automatiquement des **Quizz QCM** et des **Exercices mathématiques/logiques** à partir de **multiples documents** PDF, DOCX, ODT, PPTX et TXT, ou **directement par conversation avec l'IA** (mode libre), en utilisant des modèles LLM via l'API OpenAI (ou compatible).

## ✨ Fonctionnalités

### 🎯 Quizz QCM

- **Support multi-documents** : Uploadez **plusieurs fichiers simultanément** et générez des questions couvrant l'ensemble des documents.
- **Extraction multi-format** : Support des fichiers **PDF, DOCX, ODT, ODP, PPTX et TXT**.
- **Chunking par blocs de tokens** : Analyse par blocs de 10 000 tokens par défaut avec chevauchement et marqueurs de pages.
- **Génération multi-niveaux** :
  - Configurez simultanément le nombre de questions pour chaque niveau (**Facile**, **Moyen**, **Difficile**) en un seul run.
  - **Anti-doublons entre niveaux** : Les questions déjà générées sont passées en contexte lors des niveaux suivants, évitant les répétitions.
  - **Éditeur de Prompts** : Personnalisez le **persona expert** (ex: "Tu es un expert en droit fiscal") et les **instructions par niveau de difficulté**. Les règles techniques garantissant la qualité sont affichées en lecture seule.
- **Paramétrage précis** :
  - Nombre de choix de réponses (A, B, C, D... jusqu'à G).
  - **Mode "Fixe"** : nombre de bonnes réponses constant (slider).
  - **Mode "Variable (1 à N)"** : le LLM choisit le nombre de bonnes réponses selon la question — élimine les formulations prévisibles.
- **Questions autonomes** : Les questions sont conçues pour être répondables **sans le document source**, uniquement avec les connaissances acquises en formation.
- **Tags de notions** : Chaque question affiche les **notions fondamentales** qu'elle couvre sous forme de badges cliquables.
- **Édition interactive des questions** : Bouton "✏️ Éditer" par question pour modifier l'énoncé, les choix, les bonnes réponses et l'explication. Bouton "🤖 Améliorer par IA" pour soumettre une instruction libre au LLM (ex: "Reformule plus clairement" ou "Ajoute un choix de type piège").
- **Historique des modifications** : Toutes les modifications (édition manuelle, amélioration IA, reformulation lors de la vérification, suppressions) sont tracées dans un journal "📜 Historique des modifications" avec avant/après.
- **Export HTML interactif** : Téléchargez un fichier HTML autonome avec design sombre, score en temps réel et explications détaillées.
- **Export CSV robuste** : Séparateur `;`, guillemets systématiques (`QUOTE_ALL`), BOM UTF-8 pour compatibilité Excel.
- **Badges de difficulté** : Chaque question affiche son niveau de difficulté avec un badge coloré (🟢 Facile, 🟡 Moyen, 🔴 Difficile).
- **Vérification IA des réponses** : Le LLM relit le document source et tente de répondre à chaque question. Si le LLM échoue, la question est **reformulée automatiquement** (jusqu'à 3 tentatives), puis **supprimée** si toujours incorrecte.
- **Citations précises** : Les explications incluent une citation exacte du texte source.
- **Attribution des sources** : Document source et numéro de page précis pour chaque question.

### 🧮 Exercices & Problèmes (Maths / Logique / Science)

- **Trois types d'exercices** :
  - **Calcul numérique** : Résolution chiffrée avec vérification automatique par exécution Python.
  - **Questions à trou** : Phrases à compléter avec des blancs (`___`), retour JSON structuré `blanks`. Contexte suffisant pour répondre sans le document.
  - **Cas pratique** : Scénario avec sous-questions numérotées, retour JSON `sub_questions`. Code de vérification Python optionnel pour les calculs.
- **Trois niveaux de difficulté distincts** : 🟢 Facile / 🟡 Moyen / 🔴 Difficile.
- **Prompts réorganisés** : Même structure que les quizz — **persona** modifiable par le formateur, **règles fixes** par type affichées en lecture seule, **instructions par niveau** personnalisables.
- **Exercices autonomes** : L'énoncé fournit toutes les données nécessaires, résolvable sans le document source.
- **Tags de notions** : Chaque exercice indique les notions fondamentales qu'il couvre.
- **Vérification IA pour tous les types** : Boucle vérifier → reformuler (max 3 tentatives) → supprimer, similaire aux QCM. Les exercices à trou et cas pratiques sont aussi vérifiés par le LLM.
- **Vérification pas à pas** (calcul numérique) : Le code Python affiche chaque étape intermédiaire ; auto-correction LLM si le résultat ne correspond pas.
- **Accumulation** : Les générations successives s'ajoutent sans écraser les exercices existants. Bouton "Effacer tout" disponible.
- **Retry automatique JSON** : Si le LLM produit un JSON invalide, le système relance automatiquement l'appel jusqu'à 3 fois.
- **Validation Pydantic** : Les réponses JSON du LLM sont validées par des modèles Pydantic v2 avant traitement.

### 💬 Mode Libre (Génération par conversation IA)

- **Sans document requis** : Générez des quizz et exercices sur **n'importe quel sujet** sans uploader de fichier.
- **Conversation guidée** : L'IA pose des questions pour comprendre le sujet, le niveau et le périmètre souhaités.
- **Génération automatique de notions** : À partir de la conversation, l'IA identifie les notions fondamentales du sujet.
- **Validation interactive** : Revoyez, activez/désactivez ou modifiez les notions proposées avant la génération.
- **Extraction automatique des préférences** : Si vous mentionnez un nombre de questions ou un niveau dans la conversation, le formulaire est **pré-rempli** automatiquement.
- **Session partagée** : Après génération, créez une session partagée directement depuis le mode libre.

### 📚 Notions Fondamentales

- **Détection automatique** : L'IA identifie les concepts clés, définitions, théorèmes et principes des documents.
- **Fusion des notions similaires** : Bouton **"🔗 Regrouper les notions"** — le LLM fusionne automatiquement les notions redondantes.
- **Édition interactive** : Activez/désactivez, supprimez ou ajoutez manuellement des notions.
- **Chat LLM** : Modifiez les notions en langage naturel (ex: *« Ajoute une notion sur les dérivées partielles »*).
- **Comptage par notion** : Après génération, un badge "3 questions ✅" / "0 questions ⚠️" s'affiche à côté de chaque notion.
- **Regroupement par thématique** : Les notions sont groupées par catégorie (ex: "Fondements", "Procédure") extraite lors de la détection.
- **Option mélange de notions** : Toggle pour forcer chaque question à couvrir **une seule notion** (`related_notions` = 1 élément) ou autoriser le mélange.
- **Tagging automatique** : Chaque question/exercice généré est associé aux notions qu'il couvre.

### 🔗 Sessions Partagées & Analytics

- **Partage de quizz** : Après génération, créez une **session partagée** avec un code unique (ex: `K8S42X`).
- **Page participant** : Les participants accèdent au quizz via `/quiz_session?code=...`, saisissent leur nom et répondent aux questions.
- **Questions manquantes** : Les numéros des questions non remplies sont affichés en temps réel ; le bouton de soumission est désactivé tant que tout n'est pas répondu.
- **Scoring côté serveur** : Les bonnes réponses ne sont jamais envoyées au client.
- **Correction détaillée** : Chaque participant voit son score, les bonnes réponses et les explications après soumission.
- **Mode Pool** : Le formateur génère un **pool de questions** (ex: 50). Chaque participant reçoit un **sous-ensemble** (ex: 20 questions) tiré proportionnellement par niveau de difficulté. Si le score est en dessous du seuil, un bouton "🔁 Réessayer avec de nouvelles questions" propose un nouveau sous-ensemble depuis les questions non encore vues.
- **Dashboard Analytics** (onglet dédié) :
  - **Métriques globales** : Nombre de participants, score moyen, score médian.
  - **Taux de réussite par question** : Graphique en barres coloré (vert/orange/rouge).
  - **Taux de réussite par notion** : Graphique radar.
  - **Classement des participants** : Tableau avec podium (🥇🥈🥉).
  - **Recommandations IA** : Bouton pour analyser les résultats via LLM — identifie les notions faibles, questions problématiques, patterns étudiants et recommandations globales.
- **Sessions avec exercices** : Les exercices sont stockés et partagés dans les sessions aux côtés des quizz QCM.
- **Gestion des sessions** : Fermez une session pour empêcher de nouvelles soumissions.

### 🛠️ Ateliers Formateurs (Sessions de travail collaboratives)

- **Brouillon partageable** : Créez un atelier avec un code unique — plusieurs formateurs peuvent co-éditer le même brouillon de quizz et d'exercices.
- **Accès** : Via la barre latérale "🛠️ Ateliers Formateurs" ou en ajoutant `?code=XXXXXX` à l'URL.
- **Interface en 4 onglets** : Questions / Exercices / Notions / Outils pour une navigation claire.
- **Édition complète des questions** : Chaque question est éditable (énoncé, choix, bonnes réponses, explication, difficulté), réordonnable (⬆️/⬇️) et supprimable. Badges de difficulté, notion tags et infos source affichés comme dans l'app principale.
- **Affichage complet des exercices** : Les exercices sont visibles et éditables par type (calcul/trou/cas_pratique) avec énoncé, réponses, sous-questions, code de vérification et correction.
- **Onglet Notions** : Affichage groupé par catégorie/thème, toggle actif/inactif, édition (titre, description, catégorie, source document, pages), ajout manuel.
- **Chat LLM par onglet** : Chaque onglet de contenu (Questions, Exercices, Notions) dispose d'un champ "💬 Modifier avec l'IA" — envoyez une instruction en langage naturel et le LLM modifie la liste complète.
- **Ajout manuel** : Formulaires pour ajouter des questions, exercices et notions à la main.
- **Auto-remplissage du code** : Après création d'un nouvel atelier depuis l'onglet Exports, le code est automatiquement rempli pour permettre l'export direct des exercices.
- **Export vers atelier** : Depuis l'onglet Exports, exportez quiz, exercices ET notions (avec catégorie/thème, source, pages) vers un atelier (nouveau ou existant).
- **Import depuis session** : Importez les questions, exercices et notions d'une session étudiante dans l'atelier (dédoublonnage par titre).
- **Fusion d'ateliers** : Fusionnez le contenu (questions + exercices + notions) de deux ateliers en un seul.
- **Publication** : Publiez l'atelier comme une **session étudiante** (avec code participant) directement depuis l'interface, avec option mode pool.
- **Rafraîchissement** : Bouton "🔃 Rafraîchir" pour récupérer les modifications des collègues.
- **Persistance des documents** : Les fichiers uploadés dans l'app principale sont conservés en cache quand on navigue vers l'atelier et qu'on revient.

### ❓ Guide Formateur

- **Schéma du pipeline** : Diagramme ASCII du flux Document → Notions → Génération → Sessions → Analytics, avec les points d'intervention du formateur.
- **Points d'intervention** : Liste illustrée des moments où le formateur peut agir et quel onglet consulter.
- **FAQ statique** : ~10 questions/réponses fréquentes sur la qualité, les doublons, la sécurité, la vérification IA, etc.
- **Chatbot "Assistant formateur"** : Chat LLM avec un system prompt spécialisé — répond aux questions libres sur l'utilisation de l'outil, les bonnes pratiques pédagogiques et l'interprétation des analytics.

### 📊 Statistiques & Suivi Global

- **Tableau de bord** : Suivi persistant du nombre total de questions générées, documents traités, tokens consommés et **sessions créées**.
- **Interface intégrée** : Métriques affichées dans la barre latérale.

### 👁️ Mode Vision (PDF → Images)

- **Modèle vision** : Utilise `Qwen3-VL-32B-Instruct-FP8` pour analyser les **images des pages PDF** (diagrammes, schémas, formules, tableaux visuels).
- **Optimisation DPI automatique** : Le système calcule le DPI optimal pour respecter le budget de tokens (recherche binaire entre min/max DPI).
- **Pages par chunk configurables** : Slider pour définir le nombre de pages groupées par chunk (1–20), avec estimation des tokens par chunk en temps réel.
- **Fallback automatique** : Les fichiers non-PDF restent traités en mode texte classique.

### ⚡ Traitement par lots (Batch API)

- **API Batch OpenAI** : Soumet toutes les requêtes LLM indépendantes en un seul lot via `/v1/batches`.
- **Opérations batchées** : Génération de quizz, exercices, vérification IA des QCM, génération en mode libre.
- **Retry par requête** : Les requêtes individuelles qui échouent sont retentées automatiquement (max 2 retries, backoff exponentiel).
- **Suivi en temps réel** : Polling avec barre de progression pendant l'attente des résultats.
- **Compatible vision** : Les requêtes batch peuvent inclure des images pour le modèle vision.

### 🧠 Raisonnement IA (enable_thinking)

- **Toggle dans la sidebar** : Active ou désactive le mode "thinking" du modèle Qwen (raisonnement interne avant réponse).
- **Propagé partout** : Le paramètre est passé à toutes les générations (quiz, exercices, notions, vérification, chat).
- **Désactivé par défaut en vision** : Le mode thinking est automatiquement OFF quand le mode vision est activé.

### 🗄️ Cache LLM

- **Cache SHA256** : Les réponses LLM sont mises en cache en mémoire (clé = SHA256 des paramètres).
- **LRU + TTL** : Eviction des entrées les plus anciennes (max 500), expiration après 1h.
- **Persistence optionnelle** : Sauvegarde vers `shared_data/llm_cache.json` pour survivre aux redémarrages.
- **Skip cache** : Paramètre `use_cache=False` pour forcer un appel frais.

### 📊 Suivi des tokens

- **Tracking automatique** : Chaque appel LLM enregistre les tokens d'entrée et de sortie.
- **Stats agrégées** : Résumé total via `get_token_summary()`.

### 🧪 Tests unitaires

- **51 tests** couvrant : cache LLM, token tracker, modèles Pydantic, parsing JSON, sessions SQLite, exports HTML/CSV.
- **Exécution** : `python -m pytest tests/ -v`

### 📦 Export combiné

- **HTML combiné** : Export unique contenant les sections QCM et Exercices avec navigation par onglets.
- **CSV combiné** : Export unique avec séparateurs de sections (`=== QUIZ QCM ===` / `=== EXERCICES ===`).

---

## 🛠️ Installation

### Prérequis

- Python 3.10 ou supérieur.
- [uv](https://github.com/astral-sh/uv) (recommandé pour la gestion d'environnement, sinon pip/conda).
- Accès à une API compatible OpenAI (OpenAI, LocalAI, vLLM, etc.).

### 1. Cloner le projet

```bash
git clone <votre-repo>
cd generateur_de_quizz
```

### 2. Créer l'environnement virtuel et installer les dépendances

**Avec UV (recommandé) :**

```bash
uv venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

uv pip install -r requirements.txt
```

**Avec Pip standard :**

```bash
python -m venv .venv
# Activer l'environnement...
pip install -r requirements.txt
```

### 3. Configuration (.env)

Copiez le fichier `.env.example` vers `.env` et configurez vos accès API :

```bash
cp .env.example .env
```

Éditez `.env` :

```ini
# URL de base de votre API (ex: API locale, OpenAI, vLLM...)
OPENAI_API_BASE=http://votre-serveur:8080/v1

# Clé API (si nécessaire)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx

# Nom du modèle à utiliser
MODEL_NAME=gtp-oss-120b

# Fenêtre de contexte du modèle (en tokens)
MODEL_CONTEXT_WINDOW=32000

# Encodeur tiktoken (cl100k_base pour GPT-4, o200k_base pour GPT-4o)
TIKTOKEN_ENCODING=cl100k_base

# Modèle Vision (optionnel — même endpoint API)
VISION_MODEL_NAME=Qwen3-VL-32B-Instruct-FP8
VISION_CONTEXT_WINDOW=80000

# Base de données SQLite pour les sessions partagées
QUIZ_SESSIONS_DB=shared_data/quiz_sessions.db
```

---

## 🚀 Utilisation

Lancez l'application Streamlit :

```bash
streamlit run app.py
```

L'application s'ouvrira dans votre navigateur par défaut (généralement `http://localhost:8501`).

### Mode Document (depuis un fichier)

1. **Upload** : Chargez un ou **plusieurs fichiers** (PDF, DOCX, ODT...) dans la barre latérale.
2. **Configuration** : Activez les options (batch, vision, thinking) si besoin.
3. **Onglet Notions** : Détectez les notions fondamentales, regroupez les similaires, activez/désactivez, éditez par chat.
4. **Onglet Quizz** :
   - Configurez le nombre de questions par niveau et le mode bonnes réponses (Fixe / Variable).
   - (Optionnel) Personnalisez le persona expert et les instructions par niveau dans **"Personnaliser les Prompts"**.
   - Cliquez sur **"Générer le Quizz"**.
   - Éditez les questions via ✏️, améliorez-les par IA via 🤖, consultez l'historique des modifications.
   - Exportez en HTML ou CSV.
   - (Optionnel) Vérifiez les réponses par l'IA.
   - Créez une session partagée (mode standard ou mode pool) ou exportez vers un Atelier Formateurs.
5. **Onglet Exercices** :
   - Choisissez le type (Calcul numérique / Questions à trou / Cas pratique).
   - Personnalisez le persona et les instructions par niveau.
   - Générez — les exercices de calcul sont auto-vérifiés et auto-corrigés.
6. **Onglet Guide** : Consultez le schéma du pipeline, la FAQ et l'assistant chatbot.

### Ateliers Formateurs

1. Cliquez sur **"🛠️ Ateliers Formateurs"** dans la barre latérale.
2. Créez un nouvel atelier (titre + votre nom) ou entrez un code existant.
3. Partagez le code avec vos collègues.
4. **Onglet Questions** : Éditez les questions (badges, notions, monter/descendre, supprimer) + chat LLM "Modifier avec l'IA".
5. **Onglet Exercices** : Visualisez et éditez les exercices (calcul/trou/cas_pratique) + chat LLM.
6. **Onglet Notions** : Gérez les notions (catégorie/thème, source, toggle actif) + chat LLM.
7. **Onglet Outils** : Importez depuis une session, fusionnez avec un autre atelier (questions + exercices + notions), consultez le diff.
8. Cliquez sur **"📤 Publier"** pour créer une session étudiante depuis le brouillon.

### Sessions Partagées

1. Sélectionnez **"📡 Sessions Partagées"** dans la barre latérale.
2. Choisissez une session dans la liste déroulante.
3. Visualisez les questions et consultez le dashboard analytics.

---

## 🧠 Fonctionnement détaillé

### 📏 Chunking

- **Par blocs de tokens (10 000 par défaut)** : Segments de taille fixe avec chevauchement et marqueurs `[Début Page X] ... [Fin Page X]`. Taille ajustable.

### 🎯 Anti-doublons entre niveaux

Lors de la génération multi-niveaux (Facile → Moyen → Difficile), les questions déjà générées sont injectées dans le prompt du niveau suivant sous forme de liste "À NE PAS DUPLIQUER". Fonctionne aussi en mode batch (traitement séquentiel par niveau).

### 🔢 Nombre de bonnes réponses variable

En mode "Variable", le LLM choisit librement 1 à N-1 bonnes réponses selon la question. Évite les formulations prévisibles comme "Quels sont les 2 profils..." et permet des questions à réponse unique ou multiple selon la pertinence pédagogique.

### 🏊 Mode Pool (sessions étudiantes)

1. Le formateur génère un pool (ex: 50 questions) et définit un sous-ensemble (ex: 20) et un seuil de réussite (ex: 70%).
2. Chaque participant reçoit un sous-ensemble unique, tiré proportionnellement par difficulté depuis les questions non encore vues.
3. En dessous du seuil : bouton "🔁 Réessayer avec de nouvelles questions" → nouveau sous-ensemble depuis les non-vues. Quand tout le pool est épuisé, il se renouvelle.

### 🤖 Amélioration IA des questions

Le module `generation/question_editor.py` envoie la question + l'instruction du formateur au LLM avec un prompt strict : appliquer uniquement le changement demandé, conserver les labels des bonnes réponses, la difficulté, les sources et les notions liées.

### 🔍 Vérification IA des réponses QCM

1. Le LLM relit le document source et répond à chaque question comme un étudiant.
2. Si la réponse est incorrecte : reformulation automatique (jusqu'à 3 fois).
3. Si toujours incorrecte après 3 reformulations : suppression.
4. Toutes les reformulations et suppressions sont ajoutées au journal des modifications.

### 🤖 Vérification & Auto-correction (Exercices calcul)

1. Le LLM génère l'énoncé, la solution et un script Python de vérification avec `print()` par étape.
2. Le script est exécuté dans un **sous-processus isolé** (sandbox, timeout 30s).
3. Si le résultat ne correspond pas : renvoi au LLM pour correction, puis re-vérification.
4. Comparaison numérique robuste : tolère `10` vs `10.0`, virgules françaises (`10,5`), séparateurs de milliers, suffixes d'unités.

---

## 🏛️ Architecture du projet

```text
generateur_de_quizz/
├── app.py                        ← point d'entrée Streamlit (~2700 lignes)
├── pages/
│   ├── quiz_session.py           ← page participant (quizz partagé / pool / questions manquantes)
│   ├── work_session.py           ← page Atelier Formateurs (4 onglets : Questions/Exercices/Notions/Outils, chat LLM)
│   ├── shared_session.py         ← page Sessions Partagées (séparée de app.py)
│   └── admin.py                  ← page admin gestion utilisateurs (désactivé temp.)
├── templates/quiz_template.html  ← template Jinja2 pour export HTML
├── shared_data/                  ← données persistantes (SQLite, stats JSON, cache LLM)
├── core/
│   ├── llm_service.py            ← client LLM (cache, retry, token tracking, enable_thinking)
│   ├── llm_cache.py              ← cache SHA256 avec LRU, TTL et persistence JSON
│   ├── token_tracker.py          ← suivi des tokens LLM par appel
│   ├── models.py                 ← modèles Pydantic v2 (validation JSON LLM)
│   ├── personas.py               ← personas DGFiP par domaine + générique
│   ├── auth.py                   ← auth SQLite PBKDF2 (désactivé temp.)
│   └── stats_manager.py          ← statistiques globales (questions, docs, tokens, sessions)
├── processing/
│   ├── document_processor.py     ← extraction texte multi-format + chunking
│   └── vision_processor.py       ← rendu PDF→images via PyMuPDF, optimisation DPI
├── generation/
│   ├── quiz_generator.py         ← génération QCM (anti-doublons, variable_correct, persona)
│   ├── quiz_verifier.py          ← vérification IA des QCM, reformulation auto
│   ├── exercise_generator.py     ← génération exercices (3 types, persona séparé)
│   ├── exercise_verifier.py      ← vérification IA des exercices trou/cas_pratique
│   ├── question_editor.py        ← amélioration LLM d'une question existante
│   ├── notion_detector.py        ← détection, édition, fusion des notions
│   ├── chat_mode.py              ← machine à états pour le mode libre
│   ├── batch_service.py          ← traitement par lots (ThreadPoolExecutor, retry par requête)
│   └── calc_agent.py             ← exécution Python sandboxée pour vérification calculs
├── export/
│   └── quiz_exporter.py          ← export HTML/CSV (quiz, exercices, combiné)
├── sessions/
│   ├── session_store.py          ← backend SQLite (sessions + exercices + ateliers + pool)
│   └── analytics.py              ← dashboard Plotly + recommandations IA
├── tests/                        ← tests unitaires (pytest, 51 tests)
│   ├── conftest.py               ← fixtures partagées
│   ├── test_llm_cache.py
│   ├── test_llm_service.py
│   ├── test_token_tracker.py
│   ├── test_models.py
│   ├── test_session_store.py
│   └── test_quiz_exporter.py
└── ui/
    └── ui_components.py          ← badges, stat cards, composants réutilisables
```

## 📦 Dépendances principales

- `streamlit` : Interface Web.
- `langchain`, `langgraph`, `langchain-openai`, `langchain-experimental` : Orchestration LLM et Agents.
- `openai` : Client API standard (chat completions + batch API).
- `pdfplumber`, `python-docx`, `odfpy`, `python-pptx` : Extraction multi-format (texte).
- `PyMuPDF` (fitz) : Rendu PDF→images pour le mode vision.
- `Pillow` : Manipulation d'images et encodage base64 JPEG.
- `tiktoken` : Tokenizer OpenAI rapide.
- `jinja2` : Templating HTML.
- `plotly` : Graphiques interactifs pour le dashboard analytics.
- `pydantic` : Validation des données LLM (modèles v2).
- `pytest` : Tests unitaires.

---

## ⚠️ Notes importantes

- **Sécurité** : L'agent de vérification des exercices exécute du code Python généré par le LLM dans un **sous-processus isolé** avec timeout de 30 secondes. Utilisez ce logiciel dans un environnement de confiance.
- **Sessions partagées** : Le scoring est effectué **côté serveur** — les bonnes réponses ne sont jamais envoyées au navigateur des participants. La base SQLite est stockée dans `shared_data/`.
- **Ateliers Formateurs** : Le modèle de concurrence est "dernier à sauvegarder gagne" — pour une collaboration simultanée intensive, rafraîchissez avant d'éditer.
- **max_tokens** : Aucune limite de tokens de réponse n'est envoyée à l'API par défaut, permettant des réponses longues sans troncature.
- **Qualité du contenu généré** : Tout contenu généré doit être relu et validé par un formateur avant utilisation pédagogique.
- **Batch API** : Le toggle "Traitement par lots" nécessite que votre serveur supporte la route `/v1/batches`.

---

## 📋 Changelog

### v3.2

- Onglet Notions dans l'Atelier Formateur : affichage groupé par catégorie/thème, édition, toggle actif/inactif, ajout manuel
- Chat LLM "Modifier avec l'IA" dans les 3 onglets de contenu de l'Atelier (Questions, Exercices, Notions)
- Export notions enrichi vers atelier (catégorie, source document, pages) + bouton d'export dédié
- Import/fusion : récupère aussi les notions (dédoublonnage par titre)

### v3.1

- Auto-remplissage du code atelier après création (export exercices direct)
- Atelier Formateur refondu : 3 onglets (Questions/Exercices/Outils), affichage complet exercices, badges, notions, sources, édition inline
- Persistance des documents uploadés entre les pages (cache session_state)
- Quiz session : affichage des questions non remplies avec numéros, soumission bloquée si incomplet

### v3.0

- Génération cumulative des quiz et exercices (les questions s'ajoutent sans écraser)
- Personas par domaine DGFiP (contrôle fiscal, contentieux, recouvrement, etc.)
- Bouton Humour (réponse décalée)
- Ajout/suppression manuelle de questions
- Onglet Exports unifié (téléchargements + sessions + ateliers)
- Sessions Partagées : page dédiée `/shared_session`
- Analytics : fond blanc, sélection par nom ou code, recommandations IA
- Système de login Admin/Formateur/Utilisateur (désactivé temp.)
- Notions non couvertes mises en avant
- Documentation du pipeline (Guide Formateur + assistant chatbot)
- Suggestions par trou (1 à N indices IA)
- Export combiné Quiz + Exercices (HTML + CSV)
- Regroupement des exercices par type avec onglets
- Historique des modifications (avant/après, reformulations IA)
- Compteur de sessions dans les stats globales

### v2

- Mode Vision (Qwen3-VL) avec optimisation DPI automatique
- 3 types d'exercices : Calcul / Trou / Cas pratique
- Sessions pool avec sous-ensemble aléatoire et seuil de réussite
- Ateliers Formateurs collaboratifs
- Vérification IA des QCM et exercices (reformulation auto, max 3 tentatives)
- Cache LLM SHA256 avec LRU + TTL + persistence JSON
- Token tracking automatique
- Traitement par lots (batch API) avec retry par requête
- Raisonnement IA (enable_thinking) configurable
- Validation Pydantic v2 des réponses JSON LLM
- Agent de calcul scientifique pour auto-correction
- Pages par chunk configurables en mode vision
- Tests unitaires (51 tests)

### v1

- Extraction multi-format (PDF, DOCX, ODT, PPTX, TXT)
- Génération QCM multi-niveaux avec anti-doublons
- Export HTML interactif et CSV
- Chunking par blocs de tokens
- Mode libre (conversation IA sans document)
- Détection et édition des notions fondamentales

## 📄 Licence

MIT License — Voir le fichier [LICENSE](LICENSE) pour plus de détails.
