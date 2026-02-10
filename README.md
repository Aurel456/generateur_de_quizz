# 📝 Générateur de Quizz & Exercices IA (Streamlit + LangGraph)

Application Streamlit permettant de générer automatiquement des **Quizz QCM** et des **Exercices mathématiques/logiques** à partir de documents PDF, en utilisant des modèles LLM via l'API OpenAI (ou compatible).

## ✨ Fonctionnalités

### 🎯 Quizz QCM
- **Extraction intelligente** du texte depuis un PDF (modes Paragraphe / Global / Hybride).
- **Génération personnalisable** :
  - Difficulté : Facile, Moyen, Difficile.
  - Nombre de questions (3 à 30).
  - Nombre de choix de réponses (A, B, C, D... jusqu'à G).
  - Nombre de bonnes réponses (choix multiple possible).
- **Export HTML interactif** : Téléchargez un fichier HTML autonome avec design sombre, score en temps réel et explications détaillées.

### 🧮 Exercices & Problèmes (Maths / Logique / Science)
- **Génération d'exercices complexes** nécessitant calcul et raisonnement.
- **Vérification automatique par Agent IA** : Un agent LangGraph exécute du code Python pour vérifier la validité de la réponse et de la correction proposée par le LLM.
- **Affichage complet** : Énoncé, Réponse attendue, Étapes de résolution détaillées, Code de vérification Python.

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
```

---

## 🚀 Utilisation

Lancez l'application Streamlit :

```bash
streamlit run app.py
```

L'application s'ouvrira dans votre navigateur par défaut (généralement `http://localhost:8501`).

1.  **Upload** : Chargez votre fichier PDF dans la barre latérale.
2.  **Configuration** : Ajustez le mode de lecture (recommandé : "Hybride") et la taille des chunks.
3.  **Onglet Quizz** :
    *   Choisissez la difficulté et les paramètres.
    *   Cliquez sur **"Générer le Quizz"**.
    *   Visualisez les questions et téléchargez le fichier HTML.
4.  **Onglet Exercices** :
    *   Choisissez le nombre d'exercices.
    *   Cliquez sur **"Générer les Exercices"**.
    *   L'agent IA va générer et *vérifier* chaque exercice via l'exécution de code Python.

---

## 🏗️ Architecture du projet

- `app.py` : Interface utilisateur principale (Streamlit).
- `pdf_processor.py` : Extraction de texte (pdfplumber) et découpage intelligent (tiktoken).
- `llm_service.py` : Client API OpenAI, gestion des tokens et retry logic.
- `quiz_generator.py` : Logique de création des QCM (prompts, parsing JSON).
- `exercise_generator.py` : Création d'exercices et **Vérification Agentique** (LangGraph + PythonREPLTool).
- `quiz_exporter.py` : Moteur de rendu HTML (Jinja2).
- `templates/quiz_template.html` : Template HTML/CSS/JS pour l'export des quizz.

## 📦 Dépendances principales

- `streamlit` : Interface Web.
- `langchain`, `langgraph`, `langchain-openai`, `langchain-experimental` : Orchestration LLM et Agents.
- `openai` : Client API standard.
- `pdfplumber` : Extraction PDF robuste.
- `tiktoken` : Tokenizer OpenAI rapide.
- `jinja2` : Templating HTML.

---

## ⚠️ Notes importantes

- **Sécurité** : L'agent de vérification des exercices exécute du code Python généré par le LLM **localement**. Bien que `PythonREPLTool` soit utilisé, il n'y a pas de sandbox Docker par défaut. Utilisez ce logiciel dans un environnement de confiance ou configurez un environnement d'exécution isolé si nécessaire pour la production.
- **Modèles** : Testé avec `gtp-oss-120b` (contexte 32k). Ajustez `MODEL_CONTEXT_WINDOW` dans le `.env` si vous utilisez un modèle différent.
- **Chunking** : Si le PDF est très long, le mode "Global" peut dépasser la fenêtre de contexte. Préférez le mode "Paragraphe" ou "Hybride" avec une taille de chunk raisonnable (2000-4000 tokens).

## 📄 Licence

Projet personnel / interne.
