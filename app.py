"""
app.py — Interface Streamlit principale pour le générateur de quizz et exercices.
"""

import json
import streamlit as st
import time

from document_processor import extract_and_chunk_multiple, get_text_stats_multiple, count_tokens
from llm_service import get_model_info, list_models
from quiz_generator import generate_quiz, Quiz, DIFFICULTY_PROMPTS
from exercise_generator import generate_exercises
from quiz_exporter import export_quiz_html, export_quiz_csv, export_exercises_csv, export_exercises_html
from notion_detector import detect_notions, edit_notions_with_llm, Notion
from ui_components import render_stat_card, render_source_info, render_difficulty_badge

# ─── Configuration de la page ───────────────────────────────────────────────────

st.set_page_config(
    page_title="📝 Générateur de Quizz & Exercices",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS personnalisé ───────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        text-align: center;
        padding: 1.5rem 0;
        margin-bottom: 1rem;
    }

    .main-header h1 {
        background: linear-gradient(135deg, #6c63ff 0%, #3f51b5 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem;
        font-weight: 700;
    }

    .stat-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #2a2a40;
        text-align: center;
    }

    .stat-card .stat-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #6c63ff;
    }

    .stat-card .stat-label {
        font-size: 0.85rem;
        color: #a0a0b8;
        margin-top: 0.3rem;
    }

    .question-box {
        background: #16213e;
        border: 1px solid #2a2a40;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    .exercise-box {
        background: #16213e;
        border: 1px solid #2a2a40;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    .verified-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .verified-ok {
        background: rgba(0, 200, 83, 0.15);
        color: #00c853;
        border: 1px solid rgba(0, 200, 83, 0.3);
    }

    .verified-fail {
        background: rgba(255, 23, 68, 0.15);
        color: #ff1744;
        border: 1px solid rgba(255, 23, 68, 0.3);
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
    }
</style>
""", unsafe_allow_html=True)

# ─── Header ─────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="main-header">
    <h1>📝 Générateur de Quizz & Exercices</h1>
    <p style="color: #a0a0b8;">Uploadez un document (PDF, DOCX, ODT...) et générez automatiquement des quizz QCM et exercices avec IA</p>
</div>
""", unsafe_allow_html=True)

# ─── Session state ──────────────────────────────────────────────────────────────

if "quiz" not in st.session_state:
    st.session_state.quiz = None
if "exercises" not in st.session_state:
    st.session_state.exercises = None
if "chunks" not in st.session_state:
    st.session_state.chunks = None
if "pdf_stats" not in st.session_state:
    st.session_state.pdf_stats = None
if "difficulty_prompts" not in st.session_state:
    st.session_state.difficulty_prompts = DIFFICULTY_PROMPTS.copy()
if "notions" not in st.session_state:
    st.session_state.notions = None

# ─── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📄 Documents")
    uploaded_files = st.file_uploader(
        "Choisir un ou plusieurs fichiers",
        type=["pdf", "docx", "odt", "odp", "pptx", "txt"],
        accept_multiple_files=True,
        help="Uploadez les documents à partir desquels générer les questions."
    )

    st.divider()

    st.markdown("## ⚙️ Paramètres de lecture")
    read_mode = st.selectbox(
        "Mode de lecture",
        options=["page", "token"],
        format_func=lambda x: {
            "page": "📄 Par page / slide / section",
            "token": "🏷️ Par blocs de tokens"
        }[x],
        index=1,
        help=(
            "**Par page/slide** : Chaque page (PDF) ou slide (PPTX) devient un chunk indépendant.\n\n"
            "**Par blocs de tokens** : Découpe le texte en segments de taille fixe. Idéal pour une vision globale."
        )
    )

    max_chunk_tokens = 10000  # Valeur par défaut
    if read_mode == "token":
        max_chunk_tokens = st.slider(
            "Taille max des chunks (tokens)",
            min_value=1000,
            max_value=15000,
            value=10000,
            step=500,
            help="Nombre de tokens par segment (uniquement pour le mode 'Par blocs de tokens')."
        )

    st.divider()

    # Sélection du modèle
    st.markdown("## 🤖 Modèle LLM")
    available_models = list_models()
    model_options = [m.id for m in available_models] if available_models else ["gtp-oss-120b"]
    
    selected_model = st.selectbox(
        "Modèle LLM à sélectionner",
        options=model_options,
        index=5,
        help="Choisissez le modèle IA à utiliser pour la génération."
    )
    
    model_info = get_model_info(selected_model)
    st.caption(f"**Contexte** : {model_info['context_window']:,} tokens")
    st.caption(f"**API** : `{model_info['api_base']}`")

    # ─── Sauvegarde / Chargement de session ─────────────────────────────────
    st.divider()
    st.markdown("## 💾 Session")

    # Sauvegarder
    session_data = {}
    has_data = False
    if st.session_state.quiz is not None:
        quiz = st.session_state.quiz
        session_data["quiz"] = {
            "title": quiz.title,
            "difficulty": quiz.difficulty,
            "questions": [
                {
                    "question": q.question, "choices": q.choices,
                    "correct_answers": q.correct_answers, "explanation": q.explanation,
                    "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                    "source_document": q.source_document, "citation": q.citation,
                } for q in quiz.questions
            ],
        }
        has_data = True
    if st.session_state.exercises is not None:
        session_data["exercises"] = [
            {
                "statement": ex.statement, "expected_answer": ex.expected_answer,
                "steps": ex.steps, "num_steps": ex.num_steps, "correction": ex.correction,
                "verification_code": ex.verification_code, "verified": ex.verified,
                "verification_output": ex.verification_output,
                "source_pages": ex.source_pages, "source_document": ex.source_document,
                "citation": ex.citation,
            } for ex in st.session_state.exercises
        ]
        has_data = True
    if st.session_state.notions is not None:
        session_data["notions"] = [
            {
                "title": n.title, "description": n.description,
                "source_document": n.source_document, "source_pages": n.source_pages,
                "enabled": n.enabled,
            } for n in st.session_state.notions
        ]
        has_data = True

    if has_data:
        st.download_button(
            label="💾 Sauvegarder la session",
            data=json.dumps(session_data, ensure_ascii=False, indent=2),
            file_name="session_quizz.json",
            mime="application/json",
            use_container_width=True,
        )

    # Charger
    uploaded_session = st.file_uploader(
        "📂 Charger une session", type=["json"], key="session_loader",
        help="Restaurez une session précédemment sauvegardée."
    )
    if uploaded_session is not None:
        try:
            data = json.loads(uploaded_session.read().decode("utf-8"))
            if "quiz" in data:
                from quiz_generator import QuizQuestion
                questions = [QuizQuestion(**q) for q in data["quiz"]["questions"]]
                st.session_state.quiz = Quiz(
                    title=data["quiz"].get("title", "Quizz restauré"),
                    difficulty=data["quiz"].get("difficulty", "moyen"),
                    questions=questions,
                )
            if "exercises" in data:
                from exercise_generator import Exercise
                st.session_state.exercises = [Exercise(**ex) for ex in data["exercises"]]
            if "notions" in data:
                st.session_state.notions = [Notion(**n) for n in data["notions"]]
            st.success("✅ Session restaurée !")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erreur : {e}")

# ─── Traitement du PDF ──────────────────────────────────────────────────────────

if uploaded_files:
    # Extraire les stats et chunks
    # Identifier si les paramètres ont changé
    files_key = "_".join(sorted(f.name for f in uploaded_files))
    current_params = f"{files_key}_{read_mode}_{max_chunk_tokens}"
    
    if st.session_state.pdf_stats is None or st.session_state.get("_last_params") != current_params:
        with st.spinner("📄 Analyse et découpage des documents en cours..."):
            # Si les fichiers ont changé, on recalcule les stats
            if st.session_state.get("_last_files_key") != files_key:
                st.session_state.pdf_stats = get_text_stats_multiple(uploaded_files)
            
            # Recalculer les chunks (changement de fichier OU de mode)
            st.session_state.chunks = extract_and_chunk_multiple(
                uploaded_files, mode=read_mode, max_tokens=max_chunk_tokens
            )
            
            st.session_state._last_files_key = files_key
            st.session_state._last_params = current_params
            
            # Reset les résultats précédents
            st.session_state.quiz = None
            st.session_state.exercises = None

    stats = st.session_state.pdf_stats
    chunks = st.session_state.chunks

    # Afficher les statistiques
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_stat_card(stats.get('num_documents', 1), "Documents")
    with col2:
        render_stat_card(stats['num_pages'], "Pages / Slides")
    with col3:
        render_stat_card(f"{stats['total_tokens']:,}", "Tokens total")
    with col4:
        render_stat_card(len(chunks), "Chunks")
    with col5:
        render_stat_card(stats['avg_tokens_per_page'], "Tokens / page-slide")

    # Détails par document (repliable)
    if stats.get('per_document'):
        with st.expander(f"📊 Détails par document ({stats['num_documents']} documents)"):
            for doc_stats in stats['per_document']:
                st.markdown(
                    f"**📄 {doc_stats['name']}** — "
                    f"{doc_stats['num_pages']} pages, "
                    f"{doc_stats['total_tokens']:,} tokens"
                )

    st.divider()

    # ─── Onglets Quizz / Exercices ──────────────────────────────────────────────

    tab_notions, tab_quiz, tab_exercises, tab_preview = st.tabs(["📚 Notions Fondamentales", "🎯 Quizz QCM", "🧮 Exercices", "👁️ Aperçu texte"])

    # ═══ ONGLET NOTIONS FONDAMENTALES ════════════════════════════════════════════

    with tab_notions:
        st.markdown("### 📚 Notions Fondamentales")
        st.caption("Identifiez les concepts clés des documents. Ces notions guideront la génération des quizz et exercices.")

        # Bouton de détection
        if st.button("🔍 Détecter les notions fondamentales", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="🧠 Analyse chunk par chunk...")
            try:
                def notion_progress(current, total):
                    if total > 0:
                        progress_bar.progress(
                            current / total,
                            text=f"🧠 Analyse chunk {current + 1}/{total}..."
                        )

                notions = detect_notions(chunks, model=selected_model, progress_callback=notion_progress)
                st.session_state.notions = notions
                progress_bar.progress(1.0, text="✅ Notions détectées !")
                time.sleep(0.5)
                progress_bar.empty()
                st.rerun()
            except Exception as e:
                progress_bar.empty()
                st.error(f"❌ Erreur lors de la détection : {str(e)}")

        # Affichage et édition des notions
        if st.session_state.notions is not None:
            notions = st.session_state.notions
            active_count = sum(1 for n in notions if n.enabled)
            st.markdown(f"**{len(notions)} notion(s) détectée(s)** — {active_count} active(s)")

            st.divider()

            # Checklist des notions
            for idx, notion in enumerate(notions):
                col_check, col_text, col_del = st.columns([0.5, 8, 1])
                with col_check:
                    new_enabled = st.checkbox(
                        "act", value=notion.enabled, key=f"notion_check_{idx}", label_visibility="collapsed"
                    )
                    if new_enabled != notion.enabled:
                        st.session_state.notions[idx].enabled = new_enabled
                with col_text:
                    style = "" if notion.enabled else "opacity: 0.5;"
                    source_info = ""
                    if notion.source_document:
                        source_info += f" — 📄 {notion.source_document}"
                    if notion.source_pages:
                        source_info += f", p. {', '.join(map(str, notion.source_pages))}"
                    st.markdown(
                        f"<div style='{style}'><strong>{notion.title}</strong><br/>"
                        f"<span style='color: #a0a0b8; font-size: 0.85em;'>{notion.description}{source_info}</span></div>",
                        unsafe_allow_html=True
                    )
                with col_del:
                    if st.button("🗑️", key=f"notion_del_{idx}", help="Supprimer cette notion"):
                        st.session_state.notions.pop(idx)
                        st.rerun()

            st.divider()

            # Ajout manuel
            with st.expander("➕ Ajouter une notion manuellement"):
                new_title = st.text_input("Titre de la notion", key="new_notion_title")
                new_desc = st.text_area("Description", key="new_notion_desc", height=80)
                if st.button("Ajouter", key="add_notion_btn") and new_title:
                    st.session_state.notions.append(Notion(
                        title=new_title, description=new_desc, enabled=True
                    ))
                    st.rerun()

            # Chat LLM pour éditer les notions
            st.divider()
            st.markdown("#### 💬 Modifier les notions avec l'IA")
            st.caption("Ex: *'Ajoute une notion sur les dérivées partielles'*, *'Fusionne les notions 2 et 3'*, *'Reformule la notion 1'*")
            llm_instruction = st.text_input("Votre instruction", key="notion_llm_input", placeholder="Décrivez la modification...")
            if st.button("💬 Envoyer au LLM", key="notion_llm_btn") and llm_instruction:
                with st.spinner("🧠 Modification en cours..."):
                    try:
                        updated_notions, explanation = edit_notions_with_llm(
                            st.session_state.notions, llm_instruction, model=selected_model
                        )
                        st.session_state.notions = updated_notions
                        st.success(f"✅ {explanation}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur : {str(e)}")

        else:
            st.info("👆 Cliquez sur le bouton ci-dessus pour détecter automatiquement les notions fondamentales de vos documents.")

    # ═══ ONGLET QUIZZ ═══════════════════════════════════════════════════════════

    with tab_quiz:
        st.markdown("### ⚙️ Configuration du Quizz")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### 📊 Nombre de questions par niveau")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                num_facile = st.number_input("Facile", min_value=0, max_value=50, value=0)
            with c2:
                num_moyen = st.number_input("Moyen", min_value=0, max_value=50, value=10)
            with c3:
                num_difficile = st.number_input("Difficile", min_value=0, max_value=50, value=0)
            
            difficulty_counts = {
                "facile": num_facile,
                "moyen": num_moyen,
                "difficile": num_difficile
            }
            
            total_questions = sum(difficulty_counts.values())
            if total_questions == 0:
                st.warning("⚠️ Sélectionnez au moins une question.")

        with col_b:
            num_choices = st.slider(
                "Nombre de choix (A, B, C, ...)",
                min_value=4,
                max_value=7,
                value=4,
                help="Nombre de réponses proposées par question (A à G)."
            )

            num_correct = st.slider(
                "Nombre de bonnes réponses par question",
                min_value=1,
                max_value=num_choices - 1,
                value=1,
                help="Combien de réponses correctes parmi les choix."
            )

        # 📝 Édition des prompts
        with st.expander("📝 Personnaliser les Prompts de Difficulté"):
            st.info("Modifiez les instructions envoyées à l'IA pour chaque niveau de difficulté.")
            st.session_state.difficulty_prompts["facile"] = st.text_area(
                "Prompt Facile", 
                value=st.session_state.difficulty_prompts["facile"],
                height=100
            )
            st.session_state.difficulty_prompts["moyen"] = st.text_area(
                "Prompt Moyen", 
                value=st.session_state.difficulty_prompts["moyen"],
                height=100
            )
            st.session_state.difficulty_prompts["difficile"] = st.text_area(
                "Prompt Difficile", 
                value=st.session_state.difficulty_prompts["difficile"],
                height=100
            )

        # Bouton de génération
        if st.button("🚀 Générer le Quizz", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="Génération en cours...")
            status_text = st.empty()

            def quiz_progress(current, total):
                if total > 0:
                    progress_bar.progress(
                        current / total,
                        text=f"Traitement du chunk {current + 1}/{total}..."
                    )

            try:
                # Récupérer les notions activées
                active_notions = None
                if st.session_state.notions:
                    active_notions = [n for n in st.session_state.notions if n.enabled]

                quiz = generate_quiz(
                    chunks=chunks,
                    difficulty_counts=difficulty_counts,
                    num_choices=num_choices,
                    num_correct=num_correct,
                    difficulty_prompts=st.session_state.difficulty_prompts,
                    model=selected_model,
                    progress_callback=quiz_progress,
                    notions=active_notions
                )
                st.session_state.quiz = quiz
                progress_bar.progress(1.0, text="✅ Quizz généré !")
                time.sleep(0.5)
                progress_bar.empty()
                status_text.empty()
                st.rerun()

            except Exception as e:
                progress_bar.empty()
                st.error(f"❌ Erreur lors de la génération : {str(e)}")

        # Affichage du quizz
        if st.session_state.quiz is not None:
            quiz = st.session_state.quiz

            st.markdown(f"### 📋 Résultat : {len(quiz.questions)} questions générées")

            for i, q in enumerate(quiz.questions):
                # Badge difficulté
                diff_label = q.difficulty_level or "moyen"
                diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                expander_title = f"{diff_emoji} **Q{i+1}.** {q.question}"

                with st.expander(expander_title, expanded=(i < 3)):
                    # Badge difficulté en haut
                    render_difficulty_badge(diff_label)

                    for label, text in q.choices.items():
                        is_correct = label in q.correct_answers
                        icon = "✅" if is_correct else "⬜"
                        st.markdown(f"**{icon} {label}.** {text}")

                    if q.explanation:
                        st.info(f"💡 **Explication :** {q.explanation}")

                    if q.citation:
                        st.markdown(f"📝 **Citation :** *\"{q.citation}\"*")

                    # Source enrichie
                    render_source_info(q.source_document, q.source_pages)

            # Boutons de téléchargement
            st.divider()
            col_down1, col_down2 = st.columns(2)
            
            try:
                with col_down1:
                    html_content = export_quiz_html(quiz)
                    st.download_button(
                        label="📥 Télécharger le Quizz sous format HTML Interactif",
                        data=html_content,
                        file_name="quizz_interactif.html",
                        mime="text/html",
                        type="primary",
                        use_container_width=True
                    )
                
                with col_down2:
                    csv_content = export_quiz_csv(quiz)
                    st.download_button(
                        label="📊 Télécharger le Quizz sous format CSV",
                        data=csv_content,
                        file_name="quizz.csv",
                        mime="text/csv",
                        type="secondary",
                        use_container_width=True
                    )
                
                st.caption("Le fichier HTML est standalone — ouvrez-le dans n'importe quel navigateur. Le fichier CSV est idéal pour Excel.")
            except Exception as e:
                st.error(f"Erreur lors de l'export : {e}")

    # ═══ ONGLET EXERCICES ════════════════════════════════════════════════════════

    with tab_exercises:
        st.markdown("### ⚙️ Configuration des Exercices")

        num_exercises = st.slider(
            "Nombre d'exercices",
            min_value=1,
            max_value=10,
            value=3,
            help="Nombre d'exercices à générer (niveau moyen-difficile)."
        )

        st.info(
            "🔬 Les exercices sont de niveau **moyen à difficile** avec des réponses numériques. "
            "Chaque exercice est **vérifié par un agent IA** qui exécute du code Python pour "
            "confirmer que la réponse est correcte."
        )

        if st.button("🧮 Générer les Exercices", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="Génération et vérification en cours...")

            def exercise_progress(current, total):
                if total > 0:
                    progress_bar.progress(
                        current / total,
                        text=f"Chunk {current + 1}/{total} — Génération + vérification..."
                    )

            try:
                # Récupérer les notions activées
                active_notions = None
                if st.session_state.notions:
                    active_notions = [n for n in st.session_state.notions if n.enabled]

                exercises = generate_exercises(
                    chunks=chunks,
                    num_exercises=num_exercises,
                    model=selected_model,
                    progress_callback=exercise_progress,
                    notions=active_notions
                )
                st.session_state.exercises = exercises
                progress_bar.progress(1.0, text="✅ Exercices générés et vérifiés !")
                time.sleep(0.5)
                progress_bar.empty()
                st.rerun()

            except Exception as e:
                progress_bar.empty()
                st.error(f"❌ Erreur lors de la génération : {str(e)}")

        # Affichage des exercices
        if st.session_state.exercises is not None:
            exercises = st.session_state.exercises

            st.markdown(f"### 📋 {len(exercises)} exercice(s) généré(s)")

            for i, ex in enumerate(exercises):
                with st.expander(
                    f"**Exercice {i+1}** — {'✅ Vérifié' if ex.verified else '⚠️ Non vérifié'}",
                    expanded=True
                ):
                    # Statut de vérification
                    if ex.verified:
                        st.success("✅ Réponse vérifiée par exécution de code")
                    else:
                        st.warning("⚠️ La vérification automatique n'a pas pu confirmer la réponse")

                    # Énoncé
                    st.markdown("#### 📝 Énoncé")
                    st.markdown(ex.statement)

                    # Réponse
                    st.markdown(f"#### 🎯 Réponse attendue : `{ex.expected_answer}`")

                    # Étapes de résolution
                    if ex.steps:
                        st.markdown(f"#### 📊 Résolution ({ex.num_steps} étapes)")
                        for j, step in enumerate(ex.steps):
                            st.markdown(f"**{j+1}.** {step}")

                    # Correction IA
                    if ex.correction:
                        st.markdown("#### 🤖 Correction IA")
                        st.markdown(ex.correction)

                    # Code de vérification
                    if ex.verification_code:
                        with st.popover("🔍 Code de vérification"):
                            st.code(ex.verification_code, language="python")

                    # Output de vérification
                    if ex.verification_output:
                        with st.popover("📋 Détails de la vérification"):
                            st.text(ex.verification_output)

                    # Source enrichie
                    render_source_info(ex.source_document, ex.source_pages)

                    if ex.citation:
                        st.markdown(f"📝 **Citation :** *\"{ex.citation}\"*")
            # Boutons de téléchargement pour les exercices
            st.divider()
            col_ex1, col_ex2 = st.columns(2)
            try:
                with col_ex1:
                    html_exercises = export_exercises_html(exercises)
                    st.download_button(
                        label="📥 Télécharger les Exercices (HTML)",
                        data=html_exercises,
                        file_name="exercices.html",
                        mime="text/html",
                        type="primary",
                        use_container_width=True
                    )
                with col_ex2:
                    csv_exercises = export_exercises_csv(exercises)
                    st.download_button(
                        label="📊 Télécharger les Exercices (CSV)",
                        data=csv_exercises,
                        file_name="exercices.csv",
                        mime="text/csv",
                        type="secondary",
                        use_container_width=True
                    )
                st.caption("Le fichier HTML est standalone — ouvrez-le dans n'importe quel navigateur. Le fichier CSV est idéal pour Excel.")
            except Exception as e:
                st.error(f"Erreur lors de l'export : {e}")

    # ═══ ONGLET APERÇU TEXTE ════════════════════════════════════════════════════

    with tab_preview:
        st.markdown("### 👁️ Aperçu du texte extrait")
        st.caption(f"Mode de lecture : **{read_mode}** — {len(chunks)} chunks créés")

        # Pagination de l'aperçu
        CHUNKS_PER_PAGE = 20
        total_pages_preview = max(1, (len(chunks) + CHUNKS_PER_PAGE - 1) // CHUNKS_PER_PAGE)
        
        if total_pages_preview > 1:
            preview_page = st.number_input(
                "Page", min_value=1, max_value=total_pages_preview, value=1,
                key="preview_page",
                help=f"{total_pages_preview} page(s) de {CHUNKS_PER_PAGE} chunks"
            )
        else:
            preview_page = 1
        
        start_idx = (preview_page - 1) * CHUNKS_PER_PAGE
        end_idx = min(start_idx + CHUNKS_PER_PAGE, len(chunks))
        
        for i in range(start_idx, end_idx):
            chunk = chunks[i]
            doc_label = f"📄 {chunk.source_document} — " if chunk.source_document else ""
            with st.expander(
                f"{doc_label}Chunk {i+1} — {chunk.token_count} tokens — "
                f"Pages {', '.join(map(str, chunk.source_pages))}",
                expanded=(i == start_idx)
            ):
                st.text(chunk.text[:2000] + ("..." if len(chunk.text) > 2000 else ""))
        
        if total_pages_preview > 1:
            st.caption(f"Affichage des chunks {start_idx + 1} à {end_idx} sur {len(chunks)}")

else:
    # Message quand aucun document n'est uploadé
    st.markdown("""
    <div style="text-align: center; padding: 4rem 2rem;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📄</div>
        <h2 style="color: #6c63ff; margin-bottom: 0.5rem;">Aucun document uploadé</h2>
        <p style="color: #a0a0b8; max-width: 500px; margin: 0 auto;">
            Uploadez un ou plusieurs fichiers (PDF, DOCX, ODT...) dans la barre latérale pour commencer à 
            générer des quizz et exercices automatiquement avec l'IA.
        </p>
    </div>
    """, unsafe_allow_html=True)
