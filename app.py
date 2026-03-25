"""
app.py — Interface Streamlit principale pour le générateur de quizz et exercices.
"""

import json
import streamlit as st
import time

from processing.document_processor import (
    extract_and_chunk_multiple, extract_and_chunk_multiple_vision,
    extract_and_chunk_multiple_vision_text,
    get_text_stats_multiple, count_tokens,
    TextChunk
)
try:
    from processing.vision_processor import analyze_pdf_dpi, render_page_preview, estimate_tokens_for_dpi, convert_office_to_pdf, OFFICE_EXTENSIONS
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False
from core.llm_service import VISION_MODEL_NAME, VISION_CONTEXT_WINDOW, call_llm_chat
from generation.quiz_generator import generate_quiz, Quiz, QuizQuestion, DIFFICULTY_PROMPTS, QUIZ_DEFAULT_PERSONA, QUIZ_FIXED_RULES_DISPLAY
from generation.exercise_generator import (
    generate_exercises, Exercise, DEFAULT_EXERCISE_PROMPTS,
    DEFAULT_EXERCISE_PROMPTS_TROU, DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE,
    EXERCISE_DEFAULT_PERSONA, EXERCISE_FIXED_RULES_BY_TYPE,
)
from export.quiz_exporter import export_quiz_html, export_quiz_csv, export_exercises_csv, export_exercises_html
from generation.notion_detector import detect_notions, edit_notions_with_llm, merge_similar_notions, Notion
from ui.ui_components import render_stat_card, render_source_info, render_difficulty_badge
from core.stats_manager import load_stats, increment_stats
from generation.chat_mode import (
    ChatSession, ChatState, init_session, process_user_message,
    extract_generation_config, generate_quiz_direct, generate_exercises_direct,
)
from sessions.session_store import (
    create_session as create_quiz_session, create_pool_session,
    create_work_session, get_work_session, update_work_session_draft,
    deactivate_session, list_sessions, get_session as get_quiz_session,
)
from sessions.analytics import render_analytics_dashboard, render_session_selector
from generation.quiz_verifier import verify_quiz, QuestionVerificationResult
from generation.question_editor import improve_question_with_llm

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

with st.expander("ℹ️ Comment fonctionne cet outil ?", expanded=False):
    st.markdown("""
**En 5 étapes :**
1. **Uploadez** vos documents (PDF, DOCX, ODT, PPTX, TXT)
2. **Notions** — l'IA identifie les concepts clés du cours. Activez/désactivez ceux à cibler.
3. **Générez** des QCM (onglet Quizz) ou des exercices (Calcul / Trou / Cas pratique)
4. **Vérifiez** (optionnel) — l'IA relit le document et reformule les questions ambiguës
5. **Exportez** en HTML interactif ou CSV, ou partagez via une session en ligne

**Types d'exercices :**
- **Calcul** — réponse numérique, vérifiée automatiquement par code Python
- **Questions à trou** — phrases à compléter avec les termes clés
- **Cas pratique** — scénario réaliste avec sous-questions progressives

**Personnalisation :** Vous pouvez modifier le *persona* de l'expert (ex: "expert en droit fiscal"), les instructions par niveau de difficulté, et activer le nombre variable de bonnes réponses.

**Mode pool :** Générez un grand nombre de questions, puis partagez un sous-ensemble aléatoire par participant avec seuil de réussite et relance automatique.

**Ateliers formateurs :** Co-éditez un brouillon de quizz entre collègues avant publication.

---

**⚠️ Qualité :** L'IA peut produire des erreurs. La qualité dépend du document et du domaine. Le modèle texte ne perçoit pas les images (activez le Mode Vision pour les PDF visuels). **Relisez toujours le contenu avant utilisation.**
    """)

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
if "quiz_persona" not in st.session_state:
    st.session_state.quiz_persona = QUIZ_DEFAULT_PERSONA
if "notions" not in st.session_state:
    st.session_state.notions = None
if "exercise_prompts" not in st.session_state:
    st.session_state.exercise_prompts = {k: v for k, v in DEFAULT_EXERCISE_PROMPTS.items()}
if "exercise_prompts_trou" not in st.session_state:
    st.session_state.exercise_prompts_trou = {k: v for k, v in DEFAULT_EXERCISE_PROMPTS_TROU.items()}
if "exercise_prompts_cas_pratique" not in st.session_state:
    st.session_state.exercise_prompts_cas_pratique = {k: v for k, v in DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE.items()}
if "exercise_persona" not in st.session_state:
    st.session_state.exercise_persona = EXERCISE_DEFAULT_PERSONA
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "verification_results" not in st.session_state:
    st.session_state.verification_results = None
if "_download_cache" not in st.session_state:
    st.session_state._download_cache = {}
if "_show_sessions" not in st.session_state:
    st.session_state._show_sessions = False
if "guide_chat_messages" not in st.session_state:
    st.session_state.guide_chat_messages = []
if "_editing_question_idx" not in st.session_state:
    st.session_state._editing_question_idx = None
if "_ai_assist_instruction" not in st.session_state:
    st.session_state._ai_assist_instruction = {}
if "_quiz_changelog" not in st.session_state:
    st.session_state._quiz_changelog = []  # List of {"type", "index", "before", "after", "action"}
if "_quiz_original_snapshot" not in st.session_state:
    st.session_state._quiz_original_snapshot = None  # Snapshot after generation, before any edits


def _invalidate_download_cache():
    """Vide le cache des exports pour forcer leur recalcul."""
    st.session_state._download_cache = {}


def _get_cached(key: str, fn, *args):
    """Retourne le résultat mis en cache, ou le calcule et le stocke."""
    cache = st.session_state._download_cache
    if key not in cache:
        cache[key] = fn(*args)
    return cache[key]

# ─── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    sessions_label = "📡 Fermer Sessions" if st.session_state._show_sessions else "📡 Sessions Partagées"
    if st.button(sessions_label, width='stretch', key="sessions_top_btn"):
        st.session_state._show_sessions = not st.session_state._show_sessions
        st.rerun()

    st.page_link("pages/work_session.py", label="🛠️ Ateliers Formateurs", icon=None)

    st.divider()
    st.markdown("## 🎯 Mode")
    _radio_mode = st.radio(
        "Choisir le mode",
        ["📄 Depuis un document", "💬 Mode libre (IA)"],
        horizontal=False,
        label_visibility="collapsed",
        help="Mode document : uploadez des fichiers. Mode libre : conversez avec l'IA.",
        key="_radio_app_mode",
    )
    # Désactiver sessions si le radio change
    if st.session_state.get("_last_radio_mode") != _radio_mode:
        st.session_state._show_sessions = False
        st.session_state._last_radio_mode = _radio_mode

    app_mode = "📡 Sessions Partagées" if st.session_state._show_sessions else _radio_mode

    st.divider()

    uploaded_files = []
    if app_mode == "📄 Depuis un document":
        st.markdown("## 📄 Documents")
        uploaded_files = st.file_uploader(
            "Choisir un ou plusieurs fichiers",
            type=["pdf", "docx", "odt", "odp", "pptx", "txt"],
            accept_multiple_files=True,
            help="Uploadez les documents à partir desquels générer les questions."
        )

        st.divider()

    read_mode = "token"
    max_chunk_tokens = 10000
    if app_mode == "📄 Depuis un document":
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

        if read_mode == "token":
            max_chunk_tokens = st.slider(
                "Taille max des chunks (tokens)",
                min_value=5000,
                max_value=25000,
                value=10000,
                step=1000,
                help="Nombre de tokens par segment (uniquement pour le mode 'Par blocs de tokens')."
            )

        st.divider()

    # ─── Options avancées (Batch + Vision) — avant le sélecteur de modèle ───
    batch_mode = False
    vision_enabled = False
    vision_text_mode = False
    if app_mode != "📡 Sessions Partagées":
        st.markdown("## Options avancees")

        batch_mode = st.toggle(
            "Traitement parallele",
            value=False,
            help="Execute les requetes LLM independantes en parallele. Plus rapide pour les gros quizz."
        )

        vision_enabled = st.toggle(
            "Mode Vision",
            value=False,
            help="Analyse les pages du document comme images avec Qwen3-VL."
        )

        if vision_enabled:
            vision_sub = st.radio(
                "Sous-mode vision",
                ["Images seules", "Images + Texte"],
                horizontal=True,
                label_visibility="collapsed",
                help=(
                    "**Images seules** : envoie uniquement les images au modele vision.\n\n"
                    "**Images + Texte** : envoie les images ET le texte extrait de chaque page."
                ),
            )
            vision_text_mode = vision_sub == "Images + Texte"

        st.divider()

    # ─── Modèle LLM (auto-switché si vision activé) ──────────────────────────
    selected_model = None
    if app_mode != "📡 Sessions Partagées":
        st.markdown("## 🤖 Modèle LLM")
        if vision_enabled:
            selected_model = VISION_MODEL_NAME
            st.info(f"Modele vision actif :\n`{VISION_MODEL_NAME}`")
        else:
            model_options = ["Gpt-oss-120b","Gpt-oss-20b", "Qwen3-VL-32B-Instruct-FP8", "Qwen3-Coder-Next-FP8"]
            selected_model = st.selectbox(
                "Modèle LLM à sélectionner",
                options=model_options,
                index=0,
                help="Choisissez le modèle IA à utiliser pour la génération."
            )

    # ─── Sauvegarde / Chargement de session ─────────────────────────────────
    if app_mode != "📡 Sessions Partagées":
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
                        "related_notions": q.related_notions,
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
                    "citation": ex.citation, "difficulty_level": ex.difficulty_level,
                    "related_notions": ex.related_notions,
                } for ex in st.session_state.exercises
            ]
            has_data = True
        if st.session_state.notions is not None:
            session_data["notions"] = [
                {
                    "title": n.title, "description": n.description,
                    "source_document": n.source_document, "source_pages": n.source_pages,
                    "enabled": n.enabled, "category": n.category,
                } for n in st.session_state.notions
            ]
            has_data = True

        if has_data:
            session_json = _get_cached(
                "session_json",
                lambda d: json.dumps(d, ensure_ascii=False, indent=2),
                session_data,
            )
            st.download_button(
                label="💾 Sauvegarder la session",
                data=session_json,
                file_name="session_quizz.json",
                mime="application/json",
                width='stretch',
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
                    questions = [QuizQuestion(**q) for q in data["quiz"]["questions"]]
                    st.session_state.quiz = Quiz(
                        title=data["quiz"].get("title", "Quizz restauré"),
                        difficulty=data["quiz"].get("difficulty", "moyen"),
                        questions=questions,
                    )
                if "exercises" in data:
                    st.session_state.exercises = [Exercise(**ex) for ex in data["exercises"]]
                if "notions" in data:
                    st.session_state.notions = [Notion(**n) for n in data["notions"]]
                _invalidate_download_cache()
                st.success("✅ Session restaurée !")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur : {e}")

    st.divider()
    st.markdown("## 🌍 Statistiques Globales")
    global_stats = load_stats()
    st.metric("Questions & Ex. générés", global_stats["total_questions"])
    st.metric("Documents traités", global_stats["total_documents"])
    st.metric("Sessions créées", global_stats.get("total_sessions", 0))
    st.metric("Tokens générés (IA)", f"{global_stats['total_tokens']:,}")


# ─── Traitement du PDF ──────────────────────────────────────────────────────────

if uploaded_files:
    # ─── Panneau Vision DPI ──────────────────────────────────────────────────
    vision_dpi_override = None
    if vision_enabled and _VISION_AVAILABLE:
        # Trouver le premier fichier compatible vision (PDF ou Office)
        vision_extensions = {".pdf"} | OFFICE_EXTENSIONS
        vision_files = [
            f for f in uploaded_files
            if any(getattr(f, "name", "").lower().endswith(ext) for ext in vision_extensions)
        ]
        if vision_files:
            first_file = vision_files[0]
            first_name = getattr(first_file, "name", "")

            # Convertir en PDF si nécessaire (cache le résultat)
            pdf_cache_key = f"_vision_pdf_bytes_{first_name}"
            if st.session_state.get(pdf_cache_key) is None:
                if first_name.lower().endswith(".pdf"):
                    first_file.seek(0)
                    st.session_state[pdf_cache_key] = first_file.read()
                    first_file.seek(0)
                else:
                    first_file.seek(0)
                    raw = first_file.read()
                    first_file.seek(0)
                    converted = convert_office_to_pdf(raw, first_name)
                    if converted:
                        st.session_state[pdf_cache_key] = converted
                    else:
                        st.session_state[pdf_cache_key] = None
                        st.warning(
                            f"Conversion vision impossible pour **{first_name}**. "
                            f"Installez LibreOffice ou utilisez un PDF."
                        )

            pdf_bytes = st.session_state.get(pdf_cache_key)
            if pdf_bytes:
                import io as _io
                pdf_io = _io.BytesIO(pdf_bytes)

                # Analyse DPI (cache)
                dpi_cache_key = f"_dpi_analysis_{first_name}"
                if st.session_state.get(dpi_cache_key) is None:
                    st.session_state[dpi_cache_key] = analyze_pdf_dpi(pdf_io)

                dpi_info = st.session_state[dpi_cache_key]

                if dpi_info:
                    with st.expander("🔍 Parametres Vision (DPI & Apercu)", expanded=True):
                        col_info, col_preview = st.columns([1, 1])

                        with col_info:
                            if not first_name.lower().endswith(".pdf"):
                                st.info(f"📄 **{first_name}** converti en PDF pour le mode vision.")
                            st.markdown(f"**DPI selectionne (auto) :** `{dpi_info['auto_dpi']}`")
                            st.markdown(
                                f"**Pages traitees :** {dpi_info['pages_processed']} / {dpi_info['num_pages']}"
                            )
                            st.markdown(f"**Tokens estimes (auto) :** `{dpi_info['total_tokens']:,}`")

                            st.markdown("---")
                            col_p1, col_p2, col_p3 = st.columns(3)
                            with col_p1:
                                if st.button("Rapide (50 DPI)", width='stretch', key="dpi_preset_50"):
                                    st.session_state["vision_dpi_slider"] = 50
                            with col_p2:
                                if st.button("Standard (65 DPI)", width='stretch', key="dpi_preset_65"):
                                    st.session_state["vision_dpi_slider"] = 65
                            with col_p3:
                                if st.button("Haute res (80 DPI)", width='stretch', key="dpi_preset_80"):
                                    st.session_state["vision_dpi_slider"] = 80

                            user_dpi = st.slider(
                                "Ajuster le DPI",
                                min_value=40,
                                max_value=90,
                                value=st.session_state.get("vision_dpi_slider", dpi_info["auto_dpi"]),
                                step=1,
                                key="vision_dpi_slider",
                                help="Standard 65 DPI (~450 tokens/page). Haute resolution 80 DPI (schemas complexes).",
                            )

                            # Estimer les tokens pour le DPI choisi
                            user_tokens = estimate_tokens_for_dpi(
                                dpi_info["page_sizes_pt"], user_dpi
                            )
                            budget = VISION_CONTEXT_WINDOW - 2000  # text_token_buffer

                            if user_tokens > budget:
                                st.warning(
                                    f"Tokens estimes : **{user_tokens:,}** (budget : {budget:,}). "
                                    f"Certaines pages seront tronquees."
                                )
                            else:
                                st.success(f"Tokens estimes : **{user_tokens:,}** / {budget:,}")

                            if user_dpi != dpi_info["auto_dpi"]:
                                vision_dpi_override = user_dpi

                        with col_preview:
                            preview_dpi = user_dpi
                            preview_page = 0
                            if dpi_info["num_pages"] > 1:
                                preview_page = st.number_input(
                                    "Page a previsualiser",
                                    min_value=1,
                                    max_value=dpi_info["num_pages"],
                                    value=1,
                                    key="vision_preview_page",
                                ) - 1

                            pdf_io.seek(0)
                            preview_img = render_page_preview(pdf_io, page_num=preview_page, dpi=preview_dpi)
                            if preview_img:
                                st.image(
                                    preview_img,
                                    caption=f"Page {preview_page + 1} — {preview_dpi} DPI ({preview_img.width}x{preview_img.height} px)",
                                    width='stretch',
                                )
                            else:
                                st.info("Apercu non disponible pour cette page.")

    # ─── Extraire les stats et chunks ────────────────────────────────────────
    files_key = "_".join(sorted(f.name for f in uploaded_files))
    vision_dpi_param = vision_dpi_override or "auto"
    current_params = f"{files_key}_{read_mode}_{max_chunk_tokens}_{vision_enabled}_{vision_text_mode}_{vision_dpi_param}"

    if st.session_state.pdf_stats is None or st.session_state.get("_last_params") != current_params:
        with st.spinner("📄 Analyse et découpage des documents en cours..."):
            # Si les fichiers ont changé, on recalcule les stats
            if st.session_state.get("_last_files_key") != files_key:
                st.session_state.pdf_stats = get_text_stats_multiple(uploaded_files)
                increment_stats(documents=st.session_state.pdf_stats.get('num_documents', 1))

            # Recalculer les chunks (changement de fichier OU de mode)
            if vision_enabled:
                vision_kwargs = {}
                if vision_dpi_override:
                    vision_kwargs["min_dpi"] = vision_dpi_override
                    vision_kwargs["max_dpi"] = vision_dpi_override
                if vision_text_mode:
                    st.session_state.chunks = extract_and_chunk_multiple_vision_text(
                        uploaded_files, **vision_kwargs
                    )
                else:
                    st.session_state.chunks = extract_and_chunk_multiple_vision(
                        uploaded_files, **vision_kwargs
                    )
            else:
                st.session_state.chunks = extract_and_chunk_multiple(
                    uploaded_files, mode=read_mode, max_tokens=max_chunk_tokens
                )

            st.session_state._last_files_key = files_key
            st.session_state._last_params = current_params

            # Reset les résultats précédents
            st.session_state.quiz = None
            st.session_state.exercises = None
            _invalidate_download_cache()

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

    # ─── Helper pour afficher une ligne de notion ───────────────────────────────

    def _render_notion_row(idx, notion, question_counts=None):
        col_check, col_text, col_count, col_del = st.columns([0.5, 7.5, 1.5, 1])
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
        with col_count:
            if question_counts is not None:
                count = question_counts.get(notion.title, 0)
                if count == 0:
                    st.markdown(
                        "<span style='color:#e07b39; font-size:0.8em;'>0 questions ⚠️</span>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<span style='color:#4caf50; font-size:0.8em;'>{count} question{'s' if count > 1 else ''} ✅</span>",
                        unsafe_allow_html=True
                    )
        with col_del:
            if st.button("🗑️", key=f"notion_del_{idx}", help="Supprimer cette notion"):
                st.session_state.notions.pop(idx)
                st.rerun()

    # ─── Onglets Quizz / Exercices ──────────────────────────────────────────────

    tab_notions, tab_quiz, tab_exercises, tab_preview, tab_guide = st.tabs(["📚 Notions Fondamentales", "🎯 Quizz QCM", "🧮 Exercices", "👁️ Aperçu texte", "❓ Guide"])

    # ═══ ONGLET NOTIONS FONDAMENTALES ════════════════════════════════════════════

    with tab_notions:
        st.markdown("### 📚 Notions Fondamentales")
        st.caption("Identifiez les concepts clés des documents. Ces notions guideront la génération des quizz et exercices.")

        # Bouton de détection
        if st.button("🔍 Détecter les notions fondamentales", type="primary", width='stretch'):
            progress_bar = st.progress(0, text="🧠 Démarrage...")
            try:
                _notion_start = time.time()
                def notion_progress(current, total):
                    if total > 0:
                        pct = current / total
                        elapsed = time.time() - _notion_start
                        if pct > 0.01:
                            eta = int(elapsed / pct - elapsed)
                            eta_str = f" — ~{eta}s restantes"
                        else:
                            eta_str = ""
                        progress_bar.progress(
                            pct,
                            text=f"🧠 Chunk {min(current + 1, total)}/{total}{eta_str}"
                        )

                notions = detect_notions(chunks, model=selected_model, progress_callback=notion_progress, vision_mode=vision_enabled)
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
            col_meta, col_group = st.columns([4, 1])
            with col_meta:
                st.markdown(f"**{len(notions)} notion(s) détectée(s)** — {active_count} active(s)")
            with col_group:
                if st.button("🔗 Regrouper les notions", width='stretch',
                             help="Fusionne les notions similaires ou redondantes entre elles"):
                    with st.spinner("🧠 Fusion des notions en cours..."):
                        try:
                            merged, summary = merge_similar_notions(
                                st.session_state.notions, model=selected_model
                            )
                            st.session_state.notions = merged
                            st.success(f"✅ {summary}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur : {str(e)}")

            st.divider()

            # Calculer le comptage de questions par notion
            notion_question_counts = {}
            _current_quiz = st.session_state.get("quiz")
            if _current_quiz is not None and _current_quiz.questions:
                for q in _current_quiz.questions:
                    for n_title in q.related_notions:
                        notion_question_counts[n_title] = notion_question_counts.get(n_title, 0) + 1
            show_counts = bool(notion_question_counts)

            if show_counts:
                uncovered = sum(1 for n in notions if n.enabled and notion_question_counts.get(n.title, 0) == 0)
                if uncovered:
                    st.warning(f"⚠️ {uncovered} notion(s) active(s) sans questions générées.")

            # Affichage groupé par catégorie
            from collections import defaultdict
            notions_by_cat = defaultdict(list)
            for idx, notion in enumerate(notions):
                cat = notion.category or "Général"
                notions_by_cat[cat].append((idx, notion))

            if len(notions_by_cat) > 1:
                for cat, cat_notions in notions_by_cat.items():
                    st.markdown(f"**{cat}**")
                    for idx, notion in cat_notions:
                        _render_notion_row(idx, notion, notion_question_counts if show_counts else None)
            else:
                for idx, notion in enumerate(notions):
                    _render_notion_row(idx, notion, notion_question_counts if show_counts else None)

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

            correct_mode = st.radio(
                "Nombre de bonnes réponses",
                ["Fixe", "Variable (1 à N)"],
                horizontal=True,
                help="Fixe : même nombre pour toutes les questions. Variable : le LLM choisit entre 1 et N-1 bonnes réponses par question.",
            )
            variable_correct = correct_mode == "Variable (1 à N)"
            if not variable_correct:
                num_correct = st.slider(
                    "Nombre exact de bonnes réponses",
                    min_value=1,
                    max_value=num_choices - 1,
                    value=1,
                    help="Combien de réponses correctes parmi les choix."
                )
            else:
                num_correct = 1  # valeur par défaut ignorée en mode variable

            notion_mixing = st.toggle(
                "Mélanger plusieurs notions par question",
                value=True,
                help="Activé : le LLM peut combiner plusieurs notions dans une même question. Désactivé : chaque question porte sur une seule notion.",
            )

        # 📝 Édition des prompts
        with st.expander("📝 Personnaliser les Prompts"):
            st.markdown("**1️⃣ Personnalité de l'expert** *(modifiable)*")
            st.caption("Définit le rôle et le style de l'IA pour toutes les questions.")
            col_persona, col_reset = st.columns([5, 1])
            with col_persona:
                st.session_state.quiz_persona = st.text_area(
                    "Persona",
                    value=st.session_state.quiz_persona,
                    height=80,
                    label_visibility="collapsed",
                )
            with col_reset:
                if st.button("↺ Reset", key="reset_persona", help="Restaurer le persona par défaut"):
                    st.session_state.quiz_persona = QUIZ_DEFAULT_PERSONA
                    st.rerun()

            st.markdown("**2️⃣ Instructions par niveau de difficulté** *(modifiable)*")
            st.caption("Ces instructions précisent à l'IA le type de questions à générer pour chaque niveau.")
            st.session_state.difficulty_prompts["facile"] = st.text_area(
                "🟢 Facile",
                value=st.session_state.difficulty_prompts["facile"],
                height=100
            )
            st.session_state.difficulty_prompts["moyen"] = st.text_area(
                "🟡 Moyen",
                value=st.session_state.difficulty_prompts["moyen"],
                height=100
            )
            st.session_state.difficulty_prompts["difficile"] = st.text_area(
                "🔴 Difficile",
                value=st.session_state.difficulty_prompts["difficile"],
                height=100
            )

            st.markdown("**3️⃣ Règles fixes** 🔒 *(non modifiables — garantissent la qualité et le parsing)*")
            st.code(QUIZ_FIXED_RULES_DISPLAY, language=None)

        # Bouton de génération
        if st.button("🚀 Générer le Quizz", type="primary", width='stretch'):
            progress_bar = st.progress(0, text="Démarrage...")
            status_text = st.empty()
            _quiz_start = time.time()

            def quiz_progress(current, total):
                if total > 0:
                    pct = current / total
                    elapsed = time.time() - _quiz_start
                    if pct > 0.01:
                        eta = int(elapsed / pct - elapsed)
                        eta_str = f" — ~{eta}s restantes"
                    else:
                        eta_str = ""
                    progress_bar.progress(
                        pct,
                        text=f"Chunk {min(current, total)}/{total}{eta_str}"
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
                    notions=active_notions,
                    batch_mode=batch_mode,
                    vision_mode=vision_enabled,
                    variable_correct=variable_correct,
                    persona=st.session_state.quiz_persona,
                    notion_mixing=notion_mixing,
                )
                st.session_state.quiz = quiz
                st.session_state.verification_results = None
                st.session_state._quiz_changelog = []
                st.session_state._quiz_original_snapshot = len(quiz.questions)
                _invalidate_download_cache()
                increment_stats(questions=len(quiz.questions))
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
                is_editing = (st.session_state._editing_question_idx == i)

                with st.expander(expander_title, expanded=(i < 3 or is_editing)):
                    if is_editing:
                        # ── Mode édition ────────────────────────────────────
                        st.markdown("#### ✏️ Édition de la question")

                        edit_question = st.text_area(
                            "Énoncé", value=q.question, key=f"edit_q_{i}", height=80,
                        )
                        st.markdown("**Choix de réponse**")
                        edit_choices = {}
                        for label, text in q.choices.items():
                            edit_choices[label] = st.text_input(
                                f"Choix {label}", value=text, key=f"edit_choice_{i}_{label}",
                            )
                        edit_correct = st.multiselect(
                            "Bonne(s) réponse(s)",
                            options=list(q.choices.keys()),
                            default=q.correct_answers,
                            key=f"edit_correct_{i}",
                        )
                        edit_explanation = st.text_area(
                            "Explication", value=q.explanation, key=f"edit_exp_{i}", height=80,
                        )
                        edit_citation = st.text_input(
                            "Citation source", value=q.citation, key=f"edit_cit_{i}",
                        )

                        col_save, col_cancel, col_delete = st.columns([2, 2, 1])
                        with col_save:
                            if st.button("💾 Sauvegarder", key=f"save_q_{i}", type="primary"):
                                from dataclasses import replace as dc_replace
                                before_q = {"question": q.question, "choices": dict(q.choices), "correct_answers": list(q.correct_answers), "explanation": q.explanation}
                                new_q = dc_replace(
                                    q,
                                    question=edit_question,
                                    choices=edit_choices,
                                    correct_answers=edit_correct,
                                    explanation=edit_explanation,
                                    citation=edit_citation,
                                )
                                quiz.questions[i] = new_q
                                after_q = {"question": edit_question, "choices": edit_choices, "correct_answers": edit_correct, "explanation": edit_explanation}
                                st.session_state._quiz_changelog.append({"action": "✏️ Édition manuelle", "index": i + 1, "before": before_q, "after": after_q})
                                st.session_state._editing_question_idx = None
                                _invalidate_download_cache()
                                st.rerun()
                        with col_cancel:
                            if st.button("✖️ Annuler", key=f"cancel_q_{i}"):
                                st.session_state._editing_question_idx = None
                                st.rerun()
                        with col_delete:
                            if st.button("🗑️", key=f"delete_q_{i}", help="Supprimer cette question"):
                                deleted_q = quiz.questions.pop(i)
                                st.session_state._quiz_changelog.append({"action": "🗑️ Supprimée", "index": i + 1, "before": {"question": deleted_q.question, "correct_answers": list(deleted_q.correct_answers)}, "after": None})
                                st.session_state._editing_question_idx = None
                                _invalidate_download_cache()
                                st.rerun()

                        st.divider()
                        st.markdown("**🤖 Assistance IA**")
                        ai_instr = st.text_input(
                            "Instruction pour l'IA",
                            placeholder="Ex: Rends l'explication plus concise, ajoute un distracteur plausible…",
                            key=f"ai_instr_{i}",
                        )
                        if st.button("🤖 Améliorer par IA", key=f"ai_improve_{i}", disabled=not ai_instr):
                            with st.spinner("L'IA améliore la question…"):
                                # Chercher le texte source dans les chunks
                                src_text = ""
                                if st.session_state.chunks:
                                    for chunk in st.session_state.chunks:
                                        if q.source_pages and chunk.source_pages and set(q.source_pages) & set(chunk.source_pages):
                                            src_text = chunk.text
                                            break
                                try:
                                    before_q = {"question": q.question, "choices": dict(q.choices), "correct_answers": list(q.correct_answers), "explanation": q.explanation}
                                    improved = improve_question_with_llm(
                                        quiz.questions[i], ai_instr, source_text=src_text,
                                    )
                                    quiz.questions[i] = improved
                                    after_q = {"question": improved.question, "choices": dict(improved.choices), "correct_answers": list(improved.correct_answers), "explanation": improved.explanation}
                                    st.session_state._quiz_changelog.append({"action": f"🤖 Amélioration IA ({ai_instr[:50]})", "index": i + 1, "before": before_q, "after": after_q})
                                    st.session_state._editing_question_idx = None
                                    _invalidate_download_cache()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur IA : {e}")
                    else:
                        # ── Mode lecture ─────────────────────────────────────
                        render_difficulty_badge(diff_label)

                        if q.related_notions:
                            tags_html = " ".join(
                                f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                                f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                                f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                                for n in q.related_notions
                            )
                            st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

                        for label, text in q.choices.items():
                            is_correct = label in q.correct_answers
                            icon = "✅" if is_correct else "⬜"
                            st.markdown(f"**{icon} {label}.** {text}")

                        if q.explanation:
                            st.info(f"💡 **Explication :** {q.explanation}")

                        if q.citation:
                            st.markdown(f"📝 **Citation :** *\"{q.citation}\"*")

                        render_source_info(q.source_document, q.source_pages)

                        if st.button("✏️ Éditer", key=f"edit_btn_{i}"):
                            st.session_state._editing_question_idx = i
                            st.rerun()

            # ─── Vérification IA des réponses ──────────────────────────────
            st.divider()
            st.markdown("### 🔍 Vérification IA des réponses")
            st.caption(
                "Le LLM relit le document source et tente de répondre aux questions comme un étudiant. "
                "Si il échoue, la question est reformulée (jusqu'à 3 fois) ou supprimée."
            )

            # Afficher les résultats de vérification existants
            if st.session_state.verification_results is not None:
                vr_list = st.session_state.verification_results
                n_verified = sum(1 for r in vr_list if r.status == "verified")
                n_reformulated = sum(1 for r in vr_list if r.status == "reformulated")
                n_deleted = sum(1 for r in vr_list if r.status == "deleted")

                col_v1, col_v2, col_v3 = st.columns(3)
                col_v1.metric("✅ Vérifiées", n_verified)
                col_v2.metric("🔄 Reformulées", n_reformulated)
                col_v3.metric("🗑️ Supprimées", n_deleted)

                if n_deleted > 0:
                    st.warning(
                        f"{n_deleted} question(s) supprimée(s) car le LLM n'a pas pu trouver "
                        "la bonne réponse après 3 reformulations."
                    )
                if n_reformulated > 0:
                    st.info(
                        f"{n_reformulated} question(s) reformulée(s) pour améliorer la clarté."
                    )

                with st.expander("📋 Détails des vérifications", expanded=False):
                    for r in vr_list:
                        icon = {"verified": "✅", "reformulated": "🔄", "deleted": "🗑️"}.get(r.status, "❓")
                        status_label = {"verified": "Vérifiée", "reformulated": "Reformulée", "deleted": "Supprimée"}.get(r.status, r.status)
                        st.markdown(f"**{icon} Q{r.question_index + 1}** — {status_label}")
                        for a in r.attempts:
                            attempt_icon = "✅" if a.is_correct else "❌"
                            reformulated_tag = " *(après reformulation)*" if a.was_reformulated else ""
                            st.markdown(
                                f"&nbsp;&nbsp;&nbsp;&nbsp;Tentative {a.attempt_num + 1} : "
                                f"LLM → `{a.llm_answers}` vs attendu `{a.expected_answers}` "
                                f"{attempt_icon}{reformulated_tag}"
                            )
                            if a.reasoning:
                                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;💬 {a.reasoning[:300]}")
                        st.markdown("---")

            if st.button(
                "🔍 Vérifier les réponses par l'IA",
                type="secondary",
                width='stretch',
                key="verify_quiz_btn",
            ):
                verify_bar = st.progress(0, text="Vérification en cours...")
                _verify_start = time.time()

                def verify_progress(current, total):
                    if total > 0:
                        pct = current / total
                        elapsed = time.time() - _verify_start
                        if pct > 0.01:
                            eta = int(elapsed / pct - elapsed)
                            eta_str = f" — ~{eta}s restantes"
                        else:
                            eta_str = ""
                        verify_bar.progress(
                            max(0.01, pct),
                            text=f"Question {min(current + 1, total)}/{total}{eta_str}",
                        )

                try:
                    verified_quiz, vr_results = verify_quiz(
                        quiz=quiz,
                        chunks=chunks,
                        model=selected_model,
                        max_reformulations=3,
                        progress_callback=verify_progress,
                        batch_mode=batch_mode,
                    )
                    st.session_state.quiz = verified_quiz
                    st.session_state.verification_results = vr_results
                    # Ajouter au changelog les questions reformulées/supprimées
                    for vr in vr_results:
                        if vr.status == "reformulated" and vr.final_question:
                            st.session_state._quiz_changelog.append({
                                "action": "🔄 Reformulée (vérification IA)",
                                "index": vr.question_index + 1,
                                "before": {"question": vr.original_question.question, "choices": dict(vr.original_question.choices), "correct_answers": list(vr.original_question.correct_answers), "explanation": vr.original_question.explanation},
                                "after": {"question": vr.final_question.question, "choices": dict(vr.final_question.choices), "correct_answers": list(vr.final_question.correct_answers), "explanation": vr.final_question.explanation},
                            })
                        elif vr.status == "deleted":
                            st.session_state._quiz_changelog.append({
                                "action": "🗑️ Supprimée (vérification IA)",
                                "index": vr.question_index + 1,
                                "before": {"question": vr.original_question.question, "correct_answers": list(vr.original_question.correct_answers)},
                                "after": None,
                            })
                    _invalidate_download_cache()
                    verify_bar.progress(1.0, text="✅ Vérification terminée !")
                    time.sleep(0.5)
                    verify_bar.empty()
                    st.rerun()
                except Exception as e:
                    verify_bar.empty()
                    st.error(f"❌ Erreur lors de la vérification : {str(e)}")

            # ─── Historique des modifications ─────────────────────────────
            if st.session_state._quiz_changelog:
                st.divider()
                changelog = st.session_state._quiz_changelog
                original_count = st.session_state._quiz_original_snapshot or "?"
                n_edits = sum(1 for c in changelog if "Édition" in c["action"] or "Amélioration" in c["action"])
                n_reformulated = sum(1 for c in changelog if "Reformulée" in c["action"])
                n_deleted = sum(1 for c in changelog if "Supprimée" in c["action"])

                st.markdown(f"### 📜 Historique des modifications")
                st.caption(f"Questions initiales : **{original_count}** → Actuelles : **{len(quiz.questions)}** · {n_edits} édition(s) · {n_reformulated} reformulation(s) · {n_deleted} suppression(s)")

                with st.expander(f"📋 Voir les {len(changelog)} modification(s)", expanded=False):
                    for idx, entry in enumerate(reversed(changelog)):
                        action = entry["action"]
                        q_num = entry["index"]
                        before = entry.get("before", {})
                        after = entry.get("after")

                        st.markdown(f"**{action}** — Question {q_num}")

                        if after is None:
                            # Supprimée
                            st.markdown(f"> ~~{before.get('question', '')}~~")
                        else:
                            before_text = before.get("question", "")
                            after_text = after.get("question", "")
                            if before_text != after_text:
                                st.markdown(f"**Avant :** {before_text}")
                                st.markdown(f"**Après :** {after_text}")
                            else:
                                st.markdown(f"> {after_text}")

                            # Montrer les changements de réponses
                            before_ans = before.get("correct_answers", [])
                            after_ans = after.get("correct_answers", [])
                            if before_ans != after_ans:
                                st.markdown(f"Réponses : `{before_ans}` → `{after_ans}`")

                            # Montrer les changements d'explication
                            before_exp = before.get("explanation", "")
                            after_exp = after.get("explanation", "")
                            if before_exp != after_exp and after_exp:
                                st.caption(f"💡 Explication mise à jour")

                        if idx < len(changelog) - 1:
                            st.markdown("---")

            # Boutons de téléchargement
            st.divider()
            col_down1, col_down2 = st.columns(2)

            try:
                with col_down1:
                    html_content = _get_cached("quiz_html", export_quiz_html, quiz)
                    st.download_button(
                        label="📥 Télécharger le Quizz sous format HTML Interactif",
                        data=html_content,
                        file_name="quizz_interactif.html",
                        mime="text/html",
                        type="primary",
                        width='stretch'
                    )

                with col_down2:
                    csv_content = _get_cached("quiz_csv", export_quiz_csv, quiz)
                    st.download_button(
                        label="📊 Télécharger le Quizz sous format CSV",
                        data=csv_content,
                        file_name="quizz.csv",
                        mime="text/csv",
                        type="secondary",
                        width='stretch'
                    )
                
                st.caption("Le fichier HTML est standalone — ouvrez-le dans n'importe quel navigateur. Le fichier CSV est idéal pour Excel.")
            except Exception as e:
                st.error(f"Erreur lors de l'export : {e}")

            # Section partage
            st.divider()
            st.markdown("### 🔗 Partager ce quizz")
            share_title = st.text_input(
                "Titre de la session partagée",
                value=quiz.title,
                key="share_quiz_title",
            )

            total_q = len(quiz.questions)
            use_pool = st.toggle(
                "Mode pool (sous-ensemble par participant)",
                value=False,
                key="share_use_pool",
                help=f"Le pool complet contient {total_q} questions. Chaque participant en voit un sous-ensemble tiré aléatoirement.",
            )
            if use_pool and total_q > 1:
                pool_col1, pool_col2 = st.columns(2)
                with pool_col1:
                    subset_size = st.number_input(
                        "Questions par passage",
                        min_value=1, max_value=total_q, value=min(20, total_q),
                        key="share_subset_size",
                        help="Nombre de questions présentées à chaque participant à chaque passage.",
                    )
                with pool_col2:
                    pass_threshold_pct = st.slider(
                        "Seuil de réussite (%)",
                        min_value=0, max_value=100, value=70, step=5,
                        key="share_pass_threshold",
                        help="Score minimum pour valider la session. En dessous, le participant peut réessayer avec de nouvelles questions.",
                    )
                st.caption(f"Pool : {total_q} questions — Passage : {subset_size} questions — Seuil : {pass_threshold_pct}%")

            if st.button("📤 Créer une session partagée", type="secondary", width='stretch'):
                try:
                    quiz_data = {
                        "title": quiz.title,
                        "difficulty": quiz.difficulty,
                        "questions": [
                            {
                                "question": q.question, "choices": q.choices,
                                "correct_answers": q.correct_answers, "explanation": q.explanation,
                                "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                                "source_document": q.source_document, "citation": q.citation,
                                "related_notions": q.related_notions,
                            } for q in quiz.questions
                        ],
                    }
                    notions_data = []
                    if st.session_state.notions:
                        notions_data = [
                            {"title": n.title, "description": n.description, "enabled": n.enabled}
                            for n in st.session_state.notions
                        ]
                    if use_pool and total_q > 1:
                        session_obj = create_pool_session(
                            quiz_data, notions_data, share_title,
                            subset_size=int(st.session_state.get("share_subset_size", min(20, total_q))),
                            pass_threshold=st.session_state.get("share_pass_threshold", 70) / 100,
                        )
                        st.success(f"Session pool créée ! Code : **{session_obj.session_code}**")
                        st.caption(f"Chaque participant verra {session_obj.subset_size} questions sur {total_q}.")
                    else:
                        session_obj = create_quiz_session(quiz_data, notions_data, share_title)
                        st.success(f"Session créée ! Code : **{session_obj.session_code}**")
                    st.code(f"Code de session : {session_obj.session_code}", language=None)
                    st.caption("Les participants accèdent au quizz via la page quiz_session avec `?code=" + session_obj.session_code + "`.")
                    increment_stats(sessions=1)
                except Exception as e:
                    st.error(f"Erreur : {e}")

            # Export vers un atelier formateur
            st.divider()
            st.markdown("### 🛠️ Exporter vers un atelier formateur")
            ws_target = st.text_input(
                "Code de l'atelier (vide = créer un nouvel atelier)",
                key="export_ws_code", placeholder="Ex: K8S42X",
            )
            ws_owner = st.text_input("Votre nom", key="export_ws_owner", placeholder="Formateur")
            if st.button("🛠️ Exporter vers l'atelier", key="export_to_ws"):
                quiz_data_export = {
                    "title": quiz.title,
                    "difficulty": quiz.difficulty,
                    "questions": [
                        {
                            "question": q.question, "choices": q.choices,
                            "correct_answers": q.correct_answers, "explanation": q.explanation,
                            "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                            "source_document": q.source_document, "citation": q.citation,
                            "related_notions": q.related_notions,
                        } for q in quiz.questions
                    ],
                }
                notions_export = []
                if st.session_state.notions:
                    notions_export = [
                        {"title": n.title, "description": n.description, "enabled": n.enabled}
                        for n in st.session_state.notions
                    ]
                try:
                    if ws_target.strip():
                        # Fusionner dans un atelier existant
                        existing_ws = get_work_session(ws_target.strip().upper())
                        if existing_ws is None:
                            st.error(f"Atelier introuvable : {ws_target}")
                        else:
                            import json as _json
                            existing_data = _json.loads(existing_ws.draft_quiz_json)
                            existing_qs = existing_data.get("questions", [])
                            existing_qs.extend(quiz_data_export["questions"])
                            existing_data["questions"] = existing_qs
                            update_work_session_draft(ws_target.strip().upper(), existing_data, ws_owner or "?", notions_export)
                            st.success(f"✅ {len(quiz.questions)} question(s) ajoutées à l'atelier **{ws_target.strip().upper()}** ({len(existing_qs)} total)")
                    else:
                        # Créer un nouvel atelier
                        ws_obj = create_work_session(quiz_data_export, notions_export, quiz.title, owner_name=ws_owner or "?")
                        st.success(f"Atelier créé ! Code : **{ws_obj.work_code}**")
                        st.code(f"Code atelier : {ws_obj.work_code}", language=None)
                except Exception as e:
                    st.error(f"Erreur : {e}")

    # ═══ ONGLET EXERCICES ════════════════════════════════════════════════════════

    with tab_exercises:
        st.markdown("### ⚙️ Configuration des Exercices")

        st.markdown("#### 📊 Nombre d'exercices par niveau")
        ex_c1, ex_c2, ex_c3 = st.columns(3)
        with ex_c1:
            num_ex_facile = st.number_input("🟢 Facile", min_value=0, max_value=20, value=0,
                help="Application numérique directe, une étape.")
        with ex_c2:
            num_ex_moyen = st.number_input("🟡 Moyen", min_value=0, max_value=20, value=3,
                help="Raisonnement multi-étapes.")
        with ex_c3:
            num_ex_difficile = st.number_input("🔴 Difficile", min_value=0, max_value=20, value=0,
                help="Résolution complexe, niveau études supérieures.")

        difficulty_counts_ex = {
            "facile": num_ex_facile,
            "moyen": num_ex_moyen,
            "difficile": num_ex_difficile,
        }
        total_ex = sum(difficulty_counts_ex.values())
        if total_ex == 0:
            st.warning("⚠️ Sélectionnez au moins un exercice.")

        exercise_type_label = st.radio(
            "Type d'exercice",
            ["Calcul numérique", "Questions à trou", "Cas pratique"],
            horizontal=True,
            help="Calcul : réponse numérique vérifiable par code Python. À trou : compléter des blancs. Cas pratique : scénario avec sous-questions.",
        )
        exercise_type_map = {
            "Calcul numérique": "calcul",
            "Questions à trou": "trou",
            "Cas pratique": "cas_pratique",
        }
        exercise_type = exercise_type_map[exercise_type_label]

        if exercise_type == "calcul":
            st.info(
                "🔬 Chaque exercice a une **réponse numérique vérifiable**. "
                "Un agent IA exécute du code Python pour confirmer la correction."
            )
        elif exercise_type == "trou":
            st.info("📝 Des phrases à compléter avec les termes manquants. Vérification manuelle recommandée.")
        else:
            st.info("📋 Un scénario avec plusieurs sous-questions. Vérification manuelle recommandée.")

        # 📝 Édition des prompts d'exercice (persona + difficulté + règles fixes)
        with st.expander("📝 Personnaliser les Prompts d'Exercice"):
            # Section 1 : Persona
            st.markdown("**1. Persona de l'expert** (modifiable)")
            st.session_state.exercise_persona = st.text_area(
                "Persona", value=st.session_state.exercise_persona,
                height=80, key="ex_persona_input", label_visibility="collapsed",
            )
            if st.button("🔄 Réinitialiser le persona", key="reset_ex_persona"):
                st.session_state.exercise_persona = EXERCISE_DEFAULT_PERSONA
                st.rerun()

            st.divider()

            # Section 2 : Instructions par difficulté (adaptées au type sélectionné)
            st.markdown(f"**2. Instructions par difficulté** (type : *{exercise_type_label}*)")
            # Sélectionner le bon dict de prompts selon le type
            if exercise_type == "trou":
                _ex_prompts_key = "exercise_prompts_trou"
                _ex_defaults = DEFAULT_EXERCISE_PROMPTS_TROU
            elif exercise_type == "cas_pratique":
                _ex_prompts_key = "exercise_prompts_cas_pratique"
                _ex_defaults = DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE
            else:
                _ex_prompts_key = "exercise_prompts"
                _ex_defaults = DEFAULT_EXERCISE_PROMPTS

            _ex_current = st.session_state[_ex_prompts_key]
            ex_tab_f, ex_tab_m, ex_tab_d = st.tabs(["🟢 Facile", "🟡 Moyen", "🔴 Difficile"])
            with ex_tab_f:
                _ex_current["facile"] = st.text_area(
                    "Facile", value=_ex_current["facile"], height=120, key="ex_prompt_facile",
                )
                if st.button("🔄 Réinitialiser", key="reset_ex_facile"):
                    _ex_current["facile"] = _ex_defaults["facile"]
                    st.rerun()
            with ex_tab_m:
                _ex_current["moyen"] = st.text_area(
                    "Moyen", value=_ex_current["moyen"], height=120, key="ex_prompt_moyen",
                )
                if st.button("🔄 Réinitialiser", key="reset_ex_moyen"):
                    _ex_current["moyen"] = _ex_defaults["moyen"]
                    st.rerun()
            with ex_tab_d:
                _ex_current["difficile"] = st.text_area(
                    "Difficile", value=_ex_current["difficile"], height=120, key="ex_prompt_difficile",
                )
                if st.button("🔄 Réinitialiser", key="reset_ex_difficile"):
                    _ex_current["difficile"] = _ex_defaults["difficile"]
                    st.rerun()

            st.divider()

            # Section 3 : Règles fixes (lecture seule)
            st.markdown("**3. Règles fixes du pipeline** (non modifiables)")
            st.code(EXERCISE_FIXED_RULES_BY_TYPE.get(exercise_type, ""), language=None)

        if st.button("🧮 Générer les Exercices", type="primary", width='stretch', disabled=(total_ex == 0)):
            progress_bar = st.progress(0, text="Démarrage...")
            _ex_start = time.time()

            def exercise_progress(current, total):
                if total > 0:
                    pct = current / total
                    elapsed = time.time() - _ex_start
                    if pct > 0.01:
                        eta = int(elapsed / pct - elapsed)
                        eta_str = f" — ~{eta}s restantes"
                    else:
                        eta_str = ""
                    progress_bar.progress(
                        pct,
                        text=f"Exercice {min(current, total)}/{total}{eta_str}"
                    )

            try:
                active_notions = None
                if st.session_state.notions:
                    active_notions = [n for n in st.session_state.notions if n.enabled]

                # Sélectionner les prompts éditables correspondant au type
                _active_ex_prompts = st.session_state.get(
                    {"calcul": "exercise_prompts", "trou": "exercise_prompts_trou", "cas_pratique": "exercise_prompts_cas_pratique"}.get(exercise_type, "exercise_prompts")
                )
                exercises = generate_exercises(
                    chunks=chunks,
                    difficulty_counts=difficulty_counts_ex,
                    model=selected_model,
                    progress_callback=exercise_progress,
                    notions=active_notions,
                    custom_exercise_prompts=_active_ex_prompts,
                    batch_mode=batch_mode,
                    vision_mode=vision_enabled,
                    exercise_type=exercise_type,
                    persona=st.session_state.exercise_persona,
                )
                st.session_state.exercises = exercises
                _invalidate_download_cache()
                increment_stats(questions=len(exercises))
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
                diff_label = ex.difficulty_level or "moyen"
                diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                verified_label = "✅ Vérifié" if ex.verified else "⚠️ Non vérifié"
                with st.expander(
                    f"{diff_emoji} **Exercice {i+1}** — {verified_label}",
                    expanded=True
                ):
                    # Statut de vérification
                    if ex.verified:
                        st.success("✅ Réponse vérifiée par exécution de code")
                    else:
                        st.warning("⚠️ La vérification automatique n'a pas pu confirmer la réponse")

                    # Badge difficulté
                    render_difficulty_badge(diff_label)

                    # Tags notions
                    if ex.related_notions:
                        tags_html = " ".join(
                            f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                            f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                            f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                            for n in ex.related_notions
                        )
                        st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

                    # Énoncé
                    st.markdown("#### 📝 Énoncé")
                    st.markdown(ex.statement)

                    # Affichage selon le type d'exercice
                    ex_type = getattr(ex, "exercise_type", "calcul")

                    if ex_type == "trou":
                        # Questions à trou : afficher les blancs et réponses
                        blanks = getattr(ex, "blanks", [])
                        if blanks:
                            st.markdown("#### ✏️ Réponses attendues")
                            for b in blanks:
                                st.markdown(f"**Blanc {b.get('position', '?')} :** `{b.get('answer', '')}` — *{b.get('context', '')}*")
                    elif ex_type == "cas_pratique":
                        # Cas pratique : afficher les sous-questions
                        sub_qs = getattr(ex, "sub_questions", [])
                        if sub_qs:
                            st.markdown("#### ❓ Sous-questions & Réponses")
                            for j, sq in enumerate(sub_qs):
                                st.markdown(f"**Q{j+1} :** {sq.get('question', '')}")
                                st.markdown(f"> {sq.get('answer', '')}")
                    else:
                        # Calcul numérique
                        st.markdown(f"#### 🎯 Réponse attendue : `{ex.expected_answer}`")

                        if ex.steps:
                            st.markdown(f"#### 📊 Résolution ({ex.num_steps} étapes)")
                            for j, step in enumerate(ex.steps):
                                st.markdown(f"**{j+1}.** {step}")

                        if ex.verification_output:
                            with st.expander("📋 Détails de la vérification", expanded=not ex.verified):
                                st.text(ex.verification_output)

                        if ex.verification_code:
                            with st.expander("🔍 Code de vérification"):
                                st.code(ex.verification_code, language="python")

                    # Correction IA (tous types)
                    if ex.correction:
                        st.markdown("#### 🤖 Correction IA")
                        st.markdown(ex.correction)

                    # Source enrichie
                    render_source_info(ex.source_document, ex.source_pages)

                    if ex.citation:
                        st.markdown(f"📝 **Citation :** *\"{ex.citation}\"*")
            # Boutons de téléchargement pour les exercices
            st.divider()
            col_ex1, col_ex2 = st.columns(2)
            try:
                with col_ex1:
                    html_exercises = _get_cached("ex_html", export_exercises_html, exercises)
                    st.download_button(
                        label="📥 Télécharger les Exercices (HTML)",
                        data=html_exercises,
                        file_name="exercices.html",
                        mime="text/html",
                        type="primary",
                        width='stretch'
                    )
                with col_ex2:
                    csv_exercises = _get_cached("ex_csv", export_exercises_csv, exercises)
                    st.download_button(
                        label="📊 Télécharger les Exercices (CSV)",
                        data=csv_exercises,
                        file_name="exercices.csv",
                        mime="text/csv",
                        type="secondary",
                        width='stretch'
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

    # ═══ ONGLET GUIDE FORMATEUR ══════════════════════════════════════════════════

    GUIDE_SYSTEM_PROMPT = """Tu es un assistant pédagogique intégré au Générateur de Quizz & Exercices IA.
Tu aides les formateurs à utiliser l'outil efficacement, à interpréter les résultats, et à adopter les meilleures pratiques pédagogiques.

CONTEXTE DE L'OUTIL :
- L'application génère des QCM et exercices à partir de documents (PDF, DOCX, PPTX, ODT, TXT) ou en mode libre par conversation.
- Pipeline : Upload document → Extraction texte → Détection notions fondamentales → Génération QCM / Exercices → Export / Session partagée.
- Le formateur peut intervenir à chaque étape : activer/désactiver des notions, personnaliser les prompts, ajuster la difficulté, vérifier les questions par IA, éditer manuellement.
- Les sessions partagées permettent aux étudiants de passer le quizz en ligne avec un code d'accès. Le formateur voit les résultats en temps réel dans l'onglet Analytics.
- La vérification IA (onglet Quizz > Vérification) détecte les questions ambiguës et peut les reformuler automatiquement.
- Les niveaux de difficulté (Facile / Moyen / Difficile) génèrent des questions distinctes sans doublons entre niveaux.
- Le nombre de bonnes réponses peut être fixe ou variable selon la configuration.
- Les notions fondamentales guident la génération : une notion désactivée n'est pas couverte par les questions.

RÈGLES DE RÉPONSE :
- Tu n'as PAS accès aux documents uploadés ni aux sessions en cours.
- Réponds en français, de façon concise et pratique.
- Si une question dépasse le périmètre de l'outil, dis-le clairement.
- Cite les onglets ou fonctionnalités de l'interface quand c'est utile (ex: "dans l'onglet Notions", "via le bouton Vérification IA")."""

    with tab_guide:
        st.markdown("## ❓ Guide formateur")
        st.caption("Comment fonctionne l'outil, où intervenir, et FAQ.")

        # ── Schéma du pipeline ──────────────────────────────────────────────────
        st.markdown("### 🔄 Pipeline de génération")
        st.markdown("""
```
📄 Document(s)
    │
    ▼
🔍 Extraction texte + découpage en chunks
    │
    ▼
📚 Détection des notions fondamentales  ◄── [Formateur] Activer / Désactiver / Éditer les notions
    │
    ├──► 🎯 Génération QCM              ◄── [Formateur] Configurer difficulté, prompts, nombre de réponses
    │         │
    │         ▼
    │    🤖 Vérification IA (optionnel) ◄── [Formateur] Valider ou reformuler les questions ambiguës
    │         │
    │         ▼
    │    ✏️ Édition manuelle (optionnel)◄── [Formateur] Modifier, supprimer, améliorer par IA
    │         │
    │         ▼
    │    📤 Export (HTML / CSV)
    │         │
    │         ▼
    │    📡 Session partagée            ◄── [Formateur] Partager le code aux étudiants
    │         │
    │         ▼
    │    📊 Analytics                   ◄── [Formateur] Analyser résultats, identifier lacunes
    │
    └──► 🧮 Génération exercices        ◄── [Formateur] Choisir type (calcul / trou / cas pratique)
```
""")

        st.divider()

        # ── Points d'intervention formateur ────────────────────────────────────
        st.markdown("### 🎯 Où intervenir en tant que formateur ?")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
**📚 Onglet Notions**
- Activer / désactiver des notions pour cibler la génération
- Éditer une notion via instruction LLM
- Fusionner les notions similaires
- Voir combien de questions couvrent chaque notion

**🎯 Onglet Quizz**
- Configurer le nombre de questions par niveau
- Choisir difficulté fixe ou variable en bonnes réponses
- Personnaliser le persona de l'expert et les instructions par niveau
- Lancer la vérification IA après génération
- Éditer manuellement une question ou demander une amélioration IA
""")
        with col2:
            st.markdown("""
**🧮 Onglet Exercices**
- Choisir le type : calcul numérique, questions à trou, cas pratique
- Personnaliser les instructions par niveau
- Vérification automatique du code Python (exercices calcul)

**📊 Onglet Analytics**
- Voir les taux de réussite par question et par notion
- Identifier les notions les moins bien maîtrisées
- Consulter le classement des participants

**📡 Sessions partagées (sidebar)**
- Créer une session avec code d'accès
- Suivre en temps réel les réponses des participants
""")

        st.divider()

        # ── FAQ statique ────────────────────────────────────────────────────────
        st.markdown("### 💬 Questions fréquentes")

        faq_items = [
            (
                "Pourquoi certaines questions sont-elles imprécises ou mal formulées ?",
                """Le LLM génère des questions à partir des passages du document mais peut produire des formulations vagues ou des explications incorrectes, surtout sur des documents techniques complexes.

**Recommandations :**
- Activez la **Vérification IA** après génération (onglet Quizz) — elle détecte et reformule automatiquement les questions ambiguës.
- Utilisez l'**édition manuelle** pour corriger les cas restants.
- Améliorez les instructions de difficulté dans l'expander "Personnaliser les prompts" pour orienter le style des questions."""
            ),
            (
                "Comment éviter les doublons entre les niveaux Facile / Moyen / Difficile ?",
                """En v3, l'anti-duplication est actif par défaut : les questions déjà générées (Facile) sont transmises au LLM lors de la génération du niveau suivant (Moyen, puis Difficile), avec l'instruction explicite de ne pas les dupliquer.

Si vous constatez encore des doublons, réduisez le nombre de questions par niveau ou augmentez la diversité des notions activées."""
            ),
            (
                "Combien de questions générer pour une bonne couverture ?",
                """Une règle pratique : **2 à 3 questions par notion active** par niveau de difficulté.

Utilisez le **compteur de questions par notion** dans l'onglet Notions (badge coloré à côté de chaque notion) : les notions avec 0 question affichent une alerte ⚠️.

Pour une formation de 2 heures, 15 à 25 questions QCM constituent un quizz équilibré."""
            ),
            (
                "Les documents uploadés sont-ils envoyés à un serveur distant ?",
                """Cela dépend de la configuration de votre API LLM (fichier `.env`) :
- Si `OPENAI_API_BASE` pointe vers un modèle **local** (ex: LM Studio, Ollama), les données restent sur votre machine.
- Si vous utilisez une API cloud (OpenAI, Anthropic…), les extraits de texte sont envoyés à ce service.

Les documents eux-mêmes ne sont jamais stockés de façon permanente — seul le texte extrait est utilisé le temps de la session."""
            ),
            (
                "Comment fonctionne la vérification IA des QCM ?",
                """La vérification IA (bouton dans l'onglet Quizz) analyse chaque question selon plusieurs critères :
- La bonne réponse est-elle correcte et sourçable dans le texte ?
- L'explication est-elle cohérente avec la réponse ?
- La formulation est-elle claire et non ambiguë ?

Si une question est jugée incorrecte, l'IA tente jusqu'à 3 reformulations. Si elle ne parvient pas à corriger, la question est marquée "à vérifier manuellement"."""
            ),
            (
                "À quoi servent les notions fondamentales ?",
                """Les notions sont les concepts clés identifiés dans le document (définitions, théorèmes, méthodes…). Elles servent à :
- **Guider la génération** : le LLM reçoit la liste des notions actives et doit s'assurer que chaque question en couvre au moins une.
- **Traçer les questions** : chaque question indique les notions qu'elle couvre (badges violets).
- **Mesurer la couverture** : l'Analytics montre quelles notions sont les mieux maîtrisées par les étudiants.

Désactivez les notions hors-scope avant de générer pour éviter les questions hors-sujet."""
            ),
            (
                "Comment fonctionne le mode 'Variable (1 à N bonnes réponses)' ?",
                """En mode Variable, le LLM choisit librement le nombre de bonnes réponses (1 à N-1) selon la nature de la question, ce qui rend le quizz moins prévisible.

L'interface participant s'adapte automatiquement : bouton radio pour 1 seule réponse, cases à cocher pour plusieurs.

Recommandation : utilisez le mode Variable pour les niveaux Moyen et Difficile, et Fixe (1 bonne réponse) pour le niveau Facile."""
            ),
            (
                "Quelle est la différence entre les types d'exercices ?",
                """- **Calcul numérique** : exercice avec étapes de résolution, code Python vérifié automatiquement, valeurs numériques exactes attendues.
- **Questions à trou** : phrase ou définition avec des blancs à compléter — idéal pour mémoriser les termes clés.
- **Cas pratique** : scénario réaliste avec plusieurs sous-questions — adapté à l'évaluation de la compréhension contextuelle.

La vérification Python automatique ne s'applique qu'aux exercices de type Calcul."""
            ),
            (
                "Comment interpréter les analytics après une session ?",
                """L'onglet Analytics affiche :
- **Taux de réussite par question** (barres) : les questions avec < 50% de réussite méritent une révision ou une reformulation.
- **Couverture par notion** (radar) : les notions en creux sont celles sur lesquelles les étudiants ont le plus de lacunes — priorisez-les en révision.
- **Classement participants** : permet d'identifier les étudiants en difficulté pour un accompagnement ciblé."""
            ),
            (
                "Peut-on réutiliser un quizz pour plusieurs sessions ?",
                """Oui. Après génération, utilisez le bouton **"📤 Exporter (HTML / CSV)"** pour sauvegarder le quizz, puis recréez une session partagée à chaque utilisation via le bouton **"📡 Créer une session partagée"**.

Chaque session a son propre code et ses propres résultats, indépendants des sessions précédentes."""
            ),
        ]

        for question, answer in faq_items:
            with st.expander(f"❓ {question}"):
                st.markdown(answer)

        st.divider()

        # ── Chatbot Assistant formateur ─────────────────────────────────────────
        st.markdown("### 🤖 Assistant formateur")
        st.caption("Posez vos questions sur l'utilisation de l'outil, les bonnes pratiques pédagogiques ou l'interprétation des résultats.")

        # Afficher l'historique du chatbot guide
        for msg in st.session_state.guide_chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if guide_input := st.chat_input("Votre question sur l'outil…", key="guide_chat_input"):
            st.session_state.guide_chat_messages.append({"role": "user", "content": guide_input})
            with st.chat_message("user"):
                st.markdown(guide_input)

            with st.chat_message("assistant"):
                with st.spinner("Réflexion…"):
                    api_messages = [{"role": "system", "content": GUIDE_SYSTEM_PROMPT}] + [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.guide_chat_messages
                    ]
                    try:
                        response = call_llm_chat(api_messages, temperature=0.5)
                    except Exception as e:
                        response = f"Erreur lors de la génération de la réponse : {e}"
                    st.markdown(response)

            st.session_state.guide_chat_messages.append({"role": "assistant", "content": response})

        if st.session_state.guide_chat_messages:
            if st.button("🗑️ Effacer la conversation", key="guide_clear_chat"):
                st.session_state.guide_chat_messages = []
                st.rerun()

elif app_mode == "💬 Mode libre (IA)":
    # ═══ MODE LIBRE (CHAT LLM) ════════════════════════════════════════════════
    st.markdown("### 💬 Mode libre — Générez un quizz par conversation")
    st.caption("Décrivez le sujet souhaité et l'IA vous guidera pour créer un quizz ou des exercices.")

    # Initialiser la session de chat si nécessaire
    if st.session_state.chat_session is None:
        welcome_msg, session = init_session()
        st.session_state.chat_session = session

    chat_session = st.session_state.chat_session

    # Afficher l'historique des messages
    for msg in chat_session.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Phase NOTION_VALIDATION : afficher les notions avec contrôles
    if chat_session.state == ChatState.NOTION_VALIDATION and chat_session.notions:
        st.divider()
        st.markdown("#### 📚 Notions détectées — Cochez celles à conserver")

        for idx, notion in enumerate(chat_session.notions):
            col_check, col_text = st.columns([0.5, 9.5])
            with col_check:
                new_enabled = st.checkbox(
                    "act", value=notion.enabled,
                    key=f"chat_notion_{idx}", label_visibility="collapsed"
                )
                if new_enabled != notion.enabled:
                    st.session_state.chat_session.notions[idx].enabled = new_enabled
            with col_text:
                style = "" if notion.enabled else "opacity: 0.5;"
                st.markdown(
                    f"<div style='{style}'><strong>{notion.title}</strong><br/>"
                    f"<span style='color: #a0a0b8; font-size: 0.85em;'>{notion.description}</span></div>",
                    unsafe_allow_html=True
                )

        if st.button("✅ Valider les notions et configurer le quizz", type="primary", width='stretch'):
            st.session_state.chat_session.state = ChatState.GENERATION_CONFIG
            st.session_state.chat_session.notions = [n for n in chat_session.notions if n.enabled]
            # Stocker les notions dans le session state global aussi
            st.session_state.notions = st.session_state.chat_session.notions
            confirm_msg = (
                f"✅ **{len(st.session_state.chat_session.notions)} notion(s) validée(s).** "
                "Configurez maintenant le quizz ou les exercices ci-dessous."
            )
            st.session_state.chat_session.messages.append({"role": "assistant", "content": confirm_msg})
            st.rerun()

    # Phase GENERATION_CONFIG : configuration + génération
    if chat_session.state in (ChatState.GENERATION_CONFIG, ChatState.COMPLETE):
        st.divider()
        st.markdown("#### ⚙️ Configuration de la génération")

        # Pré-remplir depuis les préférences extraites de la conversation
        cfg = chat_session.suggested_config or {}
        default_gen = cfg.get("gen_type", "quiz")
        gen_type_options = ["🎯 Quizz QCM", "🧮 Exercices", "🎯+🧮 Les deux"]
        gen_type_index = 0
        if default_gen == "exercices":
            gen_type_index = 1
        elif default_gen == "les_deux":
            gen_type_index = 2
        gen_type = st.radio("Type de génération", gen_type_options, index=gen_type_index, horizontal=True, key="chat_gen_type")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Questions par niveau**")
            c1, c2, c3 = st.columns(3)
            with c1:
                chat_num_facile = st.number_input("🟢 Facile", min_value=0, max_value=50, value=cfg.get("facile", 0), key="chat_facile")
            with c2:
                chat_num_moyen = st.number_input("🟡 Moyen", min_value=0, max_value=50, value=cfg.get("moyen", 5), key="chat_moyen")
            with c3:
                chat_num_difficile = st.number_input("🔴 Difficile", min_value=0, max_value=50, value=cfg.get("difficile", 0), key="chat_difficile")
        with col_b:
            chat_num_choices = 4
            chat_num_correct = 1
            if "Quizz" in gen_type:
                chat_num_choices = st.slider("Nombre de choix", min_value=4, max_value=7, value=cfg.get("num_choices", 4), key="chat_choices")
                chat_num_correct = st.slider("Bonnes réponses", min_value=1, max_value=chat_num_choices - 1, value=min(cfg.get("num_correct", 1), chat_num_choices - 1), key="chat_correct")

        chat_difficulty_counts = {
            "facile": chat_num_facile,
            "moyen": chat_num_moyen,
            "difficile": chat_num_difficile,
        }
        chat_total = sum(chat_difficulty_counts.values())

        if st.button("🚀 Générer", type="primary", width='stretch', disabled=(chat_total == 0)):
            progress_bar = st.progress(0, text="🧠 Génération directe des questions...")

            try:
                _gen_start = time.time()

                # Générer le quizz directement (sans document synthétique)
                if "Quizz" in gen_type:
                    def chat_quiz_progress(current, total):
                        if total > 0:
                            pct = 0.5 * (current / total)
                            elapsed = time.time() - _gen_start
                            if current / total > 0.01:
                                eta = int(elapsed / (current / total) - elapsed)
                                eta_str = f" — ~{eta}s restantes"
                            else:
                                eta_str = ""
                            progress_bar.progress(max(0.01, pct), text=f"Quiz: niveau {min(current+1,total)}/{total}{eta_str}")

                    quiz = generate_quiz_direct(
                        session=st.session_state.chat_session,
                        difficulty_counts=chat_difficulty_counts,
                        num_choices=chat_num_choices,
                        num_correct=chat_num_correct,
                        model=selected_model,
                        progress_callback=chat_quiz_progress,
                        batch_mode=batch_mode,
                    )
                    st.session_state.quiz = quiz
                    st.session_state.chat_session.quiz = quiz
                    _invalidate_download_cache()
                    increment_stats(questions=len(quiz.questions))

                # Générer les exercices directement
                if "Exercices" in gen_type or "deux" in gen_type:
                    def chat_ex_progress(current, total):
                        if total > 0:
                            base = 0.5 if "Quizz" in gen_type else 0.0
                            pct = base + 0.5 * (current / total)
                            elapsed = time.time() - _gen_start
                            if current / total > 0.01:
                                eta = int(elapsed / (current / total) - elapsed)
                                eta_str = f" — ~{eta}s restantes"
                            else:
                                eta_str = ""
                            progress_bar.progress(max(0.01, pct), text=f"Exercice: niveau {min(current+1,total)}/{total}{eta_str}")

                    exercises = generate_exercises_direct(
                        session=st.session_state.chat_session,
                        difficulty_counts=chat_difficulty_counts,
                        model=selected_model,
                        progress_callback=chat_ex_progress,
                        batch_mode=batch_mode,
                    )
                    st.session_state.exercises = exercises
                    st.session_state.chat_session.exercises = exercises
                    _invalidate_download_cache()
                    increment_stats(questions=len(exercises))

                st.session_state.chat_session.state = ChatState.COMPLETE
                progress_bar.progress(1.0, text="✅ Génération terminée !")
                time.sleep(0.5)
                progress_bar.empty()
                st.rerun()

            except Exception as e:
                progress_bar.empty()
                st.error(f"❌ Erreur lors de la génération : {str(e)}")

        # Afficher les résultats si disponibles
        if st.session_state.quiz is not None and chat_session.state == ChatState.COMPLETE:
            quiz = st.session_state.quiz
            st.markdown(f"### 📋 Résultat : {len(quiz.questions)} questions générées")

            for i, q in enumerate(quiz.questions):
                diff_label = q.difficulty_level or "moyen"
                diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                with st.expander(f"{diff_emoji} **Q{i+1}.** {q.question}", expanded=(i < 3)):
                    render_difficulty_badge(diff_label)
                    if q.related_notions:
                        tags_html = " ".join(
                            f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                            f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                            f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                            for n in q.related_notions
                        )
                        st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)
                    for label, text in q.choices.items():
                        is_correct = label in q.correct_answers
                        icon = "✅" if is_correct else "⬜"
                        st.markdown(f"**{icon} {label}.** {text}")
                    if q.explanation:
                        st.info(f"💡 **Explication :** {q.explanation}")

            # ─── Vérification IA (mode libre) ────────────────────────────
            st.divider()
            st.markdown("### 🔍 Vérification IA des réponses")
            st.caption(
                "Le LLM tente de répondre aux questions comme un étudiant (à partir de ses connaissances). "
                "Si il échoue, la question est reformulée (jusqu'à 3 fois) ou supprimée."
            )

            if st.session_state.verification_results is not None:
                vr_list = st.session_state.verification_results
                n_v = sum(1 for r in vr_list if r.status == "verified")
                n_r = sum(1 for r in vr_list if r.status == "reformulated")
                n_d = sum(1 for r in vr_list if r.status == "deleted")
                cv1, cv2, cv3 = st.columns(3)
                cv1.metric("✅ Vérifiées", n_v)
                cv2.metric("🔄 Reformulées", n_r)
                cv3.metric("🗑️ Supprimées", n_d)
                if n_d > 0:
                    st.warning(f"{n_d} question(s) supprimée(s) après 3 reformulations.")
                if n_r > 0:
                    st.info(f"{n_r} question(s) reformulée(s) pour plus de clarté.")
                with st.expander("📋 Détails des vérifications", expanded=False):
                    for r in vr_list:
                        icon = {"verified": "✅", "reformulated": "🔄", "deleted": "🗑️"}.get(r.status, "❓")
                        status_label = {"verified": "Vérifiée", "reformulated": "Reformulée", "deleted": "Supprimée"}.get(r.status, r.status)
                        st.markdown(f"**{icon} Q{r.question_index + 1}** — {status_label}")
                        for a in r.attempts:
                            a_icon = "✅" if a.is_correct else "❌"
                            ref_tag = " *(après reformulation)*" if a.was_reformulated else ""
                            st.markdown(
                                f"&nbsp;&nbsp;&nbsp;&nbsp;Tentative {a.attempt_num + 1} : "
                                f"LLM → `{a.llm_answers}` vs attendu `{a.expected_answers}` "
                                f"{a_icon}{ref_tag}"
                            )
                            if a.reasoning:
                                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;💬 {a.reasoning[:300]}")
                        st.markdown("---")

            if st.button("🔍 Vérifier les réponses par l'IA", type="secondary", width='stretch', key="verify_quiz_libre"):
                # En mode libre, pas de chunks — on génère un texte source depuis les notions
                notions_text = "\n\n".join(
                    f"## {n.title}\n{n.description}"
                    for n in (chat_session.notions or [])
                )
                fake_chunks = [TextChunk(
                    text=f"Sujet : {chat_session.topic}\n\n{notions_text}",
                    source_pages=[],
                    source_document="Généré par IA",
                    token_count=0,
                )]
                verify_bar = st.progress(0, text="Vérification en cours...")
                _vstart = time.time()

                def libre_verify_progress(current, total):
                    if total > 0:
                        pct = current / total
                        elapsed = time.time() - _vstart
                        eta_str = f" — ~{int(elapsed / pct - elapsed)}s" if pct > 0.01 else ""
                        verify_bar.progress(max(0.01, pct), text=f"Question {min(current+1, total)}/{total}{eta_str}")

                try:
                    verified_quiz, vr_results = verify_quiz(
                        quiz=quiz, chunks=fake_chunks, model=selected_model,
                        max_reformulations=3, progress_callback=libre_verify_progress,
                        batch_mode=batch_mode,
                    )
                    st.session_state.quiz = verified_quiz
                    st.session_state.chat_session.quiz = verified_quiz
                    st.session_state.verification_results = vr_results
                    _invalidate_download_cache()
                    verify_bar.progress(1.0, text="✅ Vérification terminée !")
                    time.sleep(0.5)
                    verify_bar.empty()
                    st.rerun()
                except Exception as e:
                    verify_bar.empty()
                    st.error(f"❌ Erreur lors de la vérification : {str(e)}")

            st.divider()
            col_d1, col_d2 = st.columns(2)
            try:
                with col_d1:
                    html_content = _get_cached("quiz_html", export_quiz_html, quiz)
                    st.download_button("📥 Télécharger HTML", data=html_content, file_name="quizz_libre.html", mime="text/html", type="primary", width='stretch')
                with col_d2:
                    csv_content = _get_cached("quiz_csv", export_quiz_csv, quiz)
                    st.download_button("📊 Télécharger CSV", data=csv_content, file_name="quizz_libre.csv", mime="text/csv", width='stretch')
            except Exception as e:
                st.error(f"Erreur export : {e}")

            # Section partage (mode libre)
            st.divider()
            st.markdown("### 🔗 Partager ce quizz")
            share_title_libre = st.text_input(
                "Titre de la session partagée",
                value=quiz.title,
                key="share_quiz_title_libre",
            )
            if st.button("📤 Créer une session partagée", type="secondary", width='stretch', key="share_libre"):
                try:
                    quiz_data = {
                        "title": quiz.title,
                        "difficulty": quiz.difficulty,
                        "questions": [
                            {
                                "question": q.question, "choices": q.choices,
                                "correct_answers": q.correct_answers, "explanation": q.explanation,
                                "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                                "source_document": q.source_document, "citation": q.citation,
                                "related_notions": q.related_notions,
                            } for q in quiz.questions
                        ],
                    }
                    notions_data = []
                    if st.session_state.notions:
                        notions_data = [
                            {"title": n.title, "description": n.description, "enabled": n.enabled}
                            for n in st.session_state.notions
                        ]
                    session_obj = create_quiz_session(quiz_data, notions_data, share_title_libre)
                    st.success(f"Session créée ! Code : **{session_obj.session_code}**")
                    st.code(f"Code de session : {session_obj.session_code}", language=None)
                    st.caption("Les participants peuvent rejoindre via la page 'Quiz Session' avec ce code.")
                    increment_stats(sessions=1)
                except Exception as e:
                    st.error(f"Erreur : {e}")

        if st.session_state.exercises is not None and chat_session.state == ChatState.COMPLETE:
            exercises = st.session_state.exercises
            st.markdown(f"### 📋 {len(exercises)} exercice(s) généré(s)")

            for i, ex in enumerate(exercises):
                diff_label = ex.difficulty_level or "moyen"
                diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                verified_label = "✅ Vérifié" if ex.verified else "⚠️ Non vérifié"
                with st.expander(f"{diff_emoji} **Exercice {i+1}** — {verified_label}", expanded=True):
                    if ex.verified:
                        st.success("✅ Réponse vérifiée par exécution de code")
                    else:
                        st.warning("⚠️ La vérification automatique n'a pas pu confirmer la réponse")
                    render_difficulty_badge(diff_label)
                    if ex.related_notions:
                        tags_html = " ".join(
                            f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                            f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                            f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                            for n in ex.related_notions
                        )
                        st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)
                    st.markdown("#### 📝 Énoncé")
                    st.markdown(ex.statement)
                    st.markdown(f"#### 🎯 Réponse attendue : `{ex.expected_answer}`")
                    if ex.steps:
                        st.markdown(f"#### 📊 Résolution ({ex.num_steps} étapes)")
                        for j, step in enumerate(ex.steps):
                            st.markdown(f"**{j+1}.** {step}")

            st.divider()
            col_e1, col_e2 = st.columns(2)
            try:
                with col_e1:
                    html_ex = _get_cached("ex_html", export_exercises_html, exercises)
                    st.download_button("📥 Exercices HTML", data=html_ex, file_name="exercices_libre.html", mime="text/html", type="primary", width='stretch')
                with col_e2:
                    csv_ex = _get_cached("ex_csv", export_exercises_csv, exercises)
                    st.download_button("📊 Exercices CSV", data=csv_ex, file_name="exercices_libre.csv", mime="text/csv", width='stretch')
            except Exception as e:
                st.error(f"Erreur export : {e}")

    # Input de chat (toujours visible sauf pendant la génération et après complétion config)
    if chat_session.state in (ChatState.TOPIC_DISCOVERY, ChatState.NOTION_VALIDATION):
        if user_input := st.chat_input("Votre message..."):
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.spinner("🧠 Réflexion..."):
                response, updated_session = process_user_message(
                    st.session_state.chat_session, user_input, model=selected_model
                )
                st.session_state.chat_session = updated_session
            st.rerun()

    # Bouton pour réinitialiser le chat
    if chat_session.state != ChatState.TOPIC_DISCOVERY or len(chat_session.messages) > 1:
        st.divider()
        if st.button("🔄 Nouvelle conversation", width='stretch'):
            st.session_state.chat_session = None
            st.session_state.quiz = None
            st.session_state.exercises = None
            st.session_state.notions = None
            _invalidate_download_cache()
            st.rerun()

elif app_mode == "📡 Sessions Partagées":
    # ═══ MODE SESSIONS PARTAGÉES ══════════════════════════════════════════════
    st.markdown("### 📡 Sessions Partagées")
    st.caption("Consultez les sessions de quizz partagées, les questions et les analytics.")

    all_sessions = list_sessions()
    if not all_sessions:
        st.info("Aucune session partagée n'a été créée. Générez un quizz puis partagez-le.")
    else:
        # Sélecteur de session
        session_labels = {
            f"{'🟢' if s.is_active else '🔴'} {s.title} ({s.session_code}) — {s.created_at[:10]}": s.session_code
            for s in all_sessions
        }
        selected_label = st.selectbox("Sélectionnez une session", list(session_labels.keys()))
        selected_code = session_labels.get(selected_label, "")

        if selected_code:
            sess = get_quiz_session(selected_code)
            if sess:
                # Infos session
                col_info1, col_info2, col_info3 = st.columns(3)
                with col_info1:
                    st.metric("Code", sess.session_code)
                with col_info2:
                    st.metric("Statut", "Active" if sess.is_active else "Fermée")
                with col_info3:
                    st.metric("Créée le", sess.created_at[:10])

                # Actions
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if sess.is_active:
                        if st.button("🔒 Fermer cette session", width='stretch'):
                            deactivate_session(selected_code)
                            st.success("Session fermée.")
                            st.rerun()
                with col_act2:
                    if st.button("🔃 Rafraîchir", width='stretch', key="refresh_sessions"):
                        st.rerun()

                st.divider()

                # Onglets Questions / Analytics
                tab_questions, tab_analytics_shared = st.tabs(["📋 Questions", "📊 Quizz Session Analytics"])

                with tab_questions:
                    quiz_data = json.loads(sess.quiz_json)
                    questions = quiz_data.get("questions", [])
                    st.markdown(f"**{len(questions)} question(s)** dans cette session")

                    for i, q in enumerate(questions):
                        diff_label = q.get("difficulty_level", "moyen")
                        diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                        related_notions = q.get("related_notions", [])

                        with st.expander(f"{diff_emoji} **Q{i+1}.** {q.get('question', '')}", expanded=(i < 3)):
                            render_difficulty_badge(diff_label)

                            if related_notions:
                                tags_html = " ".join(
                                    f'<span style="background:rgba(108,99,255,0.15);color:#6c63ff;'
                                    f'padding:0.2rem 0.6rem;border-radius:12px;font-size:0.8rem;'
                                    f'margin-right:0.3rem;display:inline-block;margin-bottom:0.3rem;">{n}</span>'
                                    for n in related_notions
                                )
                                st.markdown(f"📚 {tags_html}", unsafe_allow_html=True)

                            st.markdown(q.get("question", ""))

                            choices = q.get("choices", {})
                            correct_answers = q.get("correct_answers", [])
                            for label, text in choices.items():
                                is_correct = label in correct_answers
                                icon = "✅" if is_correct else "⬜"
                                st.markdown(f"**{icon} {label}.** {text}")

                            explanation = q.get("explanation", "")
                            if explanation:
                                st.info(f"💡 {explanation}")

                with tab_analytics_shared:
                    render_analytics_dashboard(selected_code)

else:
    # Message quand aucun document n'est uploadé (mode document)
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
