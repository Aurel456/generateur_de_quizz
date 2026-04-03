"""
app.py — Interface Streamlit principale pour le générateur de quizz et exercices.
"""

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
from core.llm_service import VISION_MODEL_NAME, VISION_MODEL_NAMES, VISION_CONTEXT_WINDOW, call_llm_chat
from generation.quiz_generator import generate_quiz, Quiz, QuizQuestion, DIFFICULTY_PROMPTS, QUIZ_DEFAULT_PERSONA, QUIZ_FIXED_RULES_DISPLAY
from generation.exercise_generator import (
    generate_exercises, Exercise, DEFAULT_EXERCISE_PROMPTS,
    DEFAULT_EXERCISE_PROMPTS_TROU, DEFAULT_EXERCISE_PROMPTS_CAS_PRATIQUE,
    EXERCISE_DEFAULT_PERSONA, EXERCISE_FIXED_RULES_BY_TYPE,
    generate_blank_suggestions,
)
from export.quiz_exporter import (
    export_quiz_html, export_quiz_csv, export_exercises_csv, export_exercises_html,
    export_combined_html, export_combined_csv,
)
from generation.notion_detector import detect_notions, edit_notions_with_llm, merge_similar_notions, Notion
from ui.ui_components import render_stat_card, render_source_info, render_difficulty_badge
from core.stats_manager import load_stats, increment_stats
from core.personas import PERSONA_DOMAINS, get_persona_for_domain
from generation.chat_mode import (
    ChatSession, ChatState, init_session, process_user_message,
    extract_generation_config, generate_quiz_direct, generate_exercises_direct,
)
from sessions.session_store import (
    create_session as create_quiz_session, create_pool_session,
    create_work_session, get_work_session, update_work_session_draft,
)
from generation.quiz_verifier import verify_quiz, QuestionVerificationResult
from generation.question_editor import improve_question_with_llm

# ─── Configuration de la page ───────────────────────────────────────────────────

st.set_page_config(
    page_title="📝 Générateur de Quizz & Exercices",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Authentification (désactivé temporairement) ──────────────────────────────
# from core.auth import authenticate
#
# if "user" not in st.session_state:
#     st.session_state.user = None
#
# if st.session_state.user is None:
#     st.markdown("### 🔐 Connexion")
#     with st.form("login_form"):
#         login_username = st.text_input("Nom d'utilisateur")
#         login_password = st.text_input("Mot de passe", type="password")
#         login_submitted = st.form_submit_button("Se connecter", type="primary")
#     if login_submitted:
#         user = authenticate(login_username, login_password)
#         if user:
#             st.session_state.user = user
#             st.rerun()
#         else:
#             st.error("Identifiants incorrects.")
#     st.caption("Contactez un administrateur pour obtenir un compte.")
#     st.stop()

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

with st.popover("🏷️ v3.0"):
    st.markdown("""
**Nouveautés v3.0 :**
- Génération cumulative des quiz (les questions s'ajoutent)
- Personas par domaine DGFiP (contrôle fiscal, contentieux, etc.)
- Bouton Humour pour les quiz
- Ajout/suppression manuelle de questions
- Onglet Exports unifié (téléchargements + sessions + ateliers)
- Sessions Partagées : page dédiée `/shared_session`
- Analytics : fond blanc, sélection par nom ou code
- Système de login (Admin / Formateur / Utilisateur)
- Notions non couvertes mises en avant
- Documentation du pipeline de génération

**Rappel v2 :**
- Mode Vision (Qwen3-VL), 3 types d'exercices, sessions pool, ateliers formateurs, vérification IA, cache LLM, token tracking
""")

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
    # Navigation
    st.page_link("pages/work_session.py", label="🛠️ Ateliers Formateurs", icon=None)
    st.page_link("pages/shared_session.py", label="📡 Sessions Partagées", icon=None)
    # Auth désactivé temporairement
    # _current_user = st.session_state.user
    # st.markdown(f"👤 **{_current_user.display_name}** ({_current_user.role})")
    # if st.button("🚪 Déconnexion", key="logout_btn"):
    #     st.session_state.user = None
    #     st.rerun()
    # if _current_user.role == "admin":
    #     st.page_link("pages/admin.py", label="🔧 Administration", icon=None)

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
    app_mode = _radio_mode

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

        # Persistance des fichiers entre pages (cache bytes dans session_state)
        if uploaded_files:
            import io as _io_cache
            _cached = []
            for f in uploaded_files:
                f.seek(0)
                _cached.append({"name": f.name, "bytes": f.read()})
                f.seek(0)
            st.session_state["_uploaded_files_cache"] = _cached
        elif st.session_state.get("_uploaded_files_cache") and not uploaded_files:
            import io as _io_cache
            uploaded_files = []
            for fc in st.session_state["_uploaded_files_cache"]:
                buf = _io_cache.BytesIO(fc["bytes"])
                buf.name = fc["name"]
                uploaded_files.append(buf)
            if uploaded_files:
                st.caption(f"📎 {len(uploaded_files)} document(s) en cache : {', '.join(f.name for f in uploaded_files)}")

        st.divider()

    read_mode = "token"
    max_chunk_tokens = 10000

    # ─── Options avancées (Batch + Vision) — avant le sélecteur de modèle ───
    batch_mode = False
    vision_enabled = False
    vision_text_mode = False
    if app_mode == "📄 Depuis un document":
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

        enable_thinking = st.toggle(
            "Raisonnement IA (thinking)",
            value=not vision_enabled,
            help="Active le mode raisonnement du LLM. Desactive par defaut en mode vision pour de meilleures performances.",
        )
        st.session_state["enable_thinking"] = enable_thinking

        st.divider()

    # ─── Modèle LLM (auto-switché si vision activé) ──────────────────────────
    selected_model = VISION_MODEL_NAME if vision_enabled else "Gpt-oss-120b"

    st.divider()
    st.markdown("## 🌍 Statistiques Globales")
    global_stats = load_stats()
    st.metric("Questions & Ex. générés", global_stats["total_questions"])
    st.metric("Documents traités", global_stats["total_documents"])
    st.metric("Sessions créées", global_stats.get("total_sessions", 0))
    st.metric("Tokens générés (IA)", f"{global_stats['total_tokens']:,}")


# ─── Traitement du PDF ──────────────────────────────────────────────────────────

_has_existing_data = (st.session_state.quiz is not None or st.session_state.exercises is not None or st.session_state.notions is not None)

if app_mode == "📄 Depuis un document":
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
                                col_p1, col_p2 = st.columns(2)
                                with col_p1:
                                    if st.button("Standard (65 DPI)", width='stretch', key="dpi_preset_65"):
                                        st.session_state["vision_dpi_slider"] = 65
                                with col_p2:
                                    if st.button("Haute res (80 DPI)", width='stretch', key="dpi_preset_80"):
                                        st.session_state["vision_dpi_slider"] = 80

                                user_dpi = st.slider(
                                    "Ajuster le DPI",
                                    min_value=50,
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

                        # Slider pages par chunk
                        pages_per_chunk = st.slider(
                            "Pages par chunk (vision)",
                            min_value=1,
                            max_value=20,
                            value=st.session_state.get("vision_pages_per_chunk", 10),
                            key="vision_pages_per_chunk",
                            help="Nombre de pages groupées par chunk pour le traitement vision. "
                                 "Moins de pages = plus de chunks mais plus précis.",
                        )
                        # Estimation tokens par chunk
                        if dpi_info and dpi_info.get("page_sizes_pt"):
                            from processing.vision_processor import calculate_page_tokens
                            current_dpi = vision_dpi_override or dpi_info["auto_dpi"]
                            avg_tokens_per_page = sum(
                                calculate_page_tokens(w, h, current_dpi)
                                for w, h in dpi_info["page_sizes_pt"]
                            ) / max(len(dpi_info["page_sizes_pt"]), 1)
                            tokens_per_chunk = int(avg_tokens_per_page * pages_per_chunk)
                            st.caption(f"~{tokens_per_chunk:,} tokens/chunk ({avg_tokens_per_page:.0f} tokens/page × {pages_per_chunk} pages)")

        # ─── Extraire les stats et chunks ────────────────────────────────────────
        files_key = "_".join(sorted(f.name for f in uploaded_files))
        vision_dpi_param = vision_dpi_override or "auto"
        vision_pages_chunk = st.session_state.get("vision_pages_per_chunk", 10)
        current_params = f"{files_key}_{read_mode}_{max_chunk_tokens}_{vision_enabled}_{vision_text_mode}_{vision_dpi_param}_{vision_pages_chunk}"

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
                        vision_kwargs["max_pages_per_chunk"] = vision_pages_chunk
                        st.session_state.chunks = extract_and_chunk_multiple_vision_text(
                            uploaded_files, **vision_kwargs
                        )
                    else:
                        vision_kwargs["max_images_per_chunk"] = vision_pages_chunk
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


    # Fallback si pas de fichiers uploadés
    chunks = st.session_state.chunks or []
    stats = st.session_state.pdf_stats

    if stats and chunks:
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

    tab_exports, tab_notions, tab_quiz, tab_exercises, tab_preview, tab_guide = st.tabs(["📦 Exports", "📚 Notions Fondamentales", "🎯 Quizz QCM", "🧮 Exercices", "👁️ Aperçu texte", "❓ Guide"])

    # ═══ ONGLET EXPORTS ═══════════════════════════════════════════════════════════

    with tab_exports:
        st.markdown("### 📦 Exports")

        _exp_quiz = st.session_state.quiz
        _exp_exercises = st.session_state.exercises

        if _exp_quiz is None and _exp_exercises is None:
            st.info("Générez d'abord un quiz ou des exercices pour accéder aux exports.")
        else:
            # ─── Section Téléchargements ──────────────────────────────────────
            st.markdown("#### 📥 Téléchargements")
            try:
                if _exp_quiz is not None and _exp_quiz.questions:
                    st.markdown("**Quiz**")
                    col_q1, col_q2 = st.columns(2)
                    with col_q1:
                        html_content = _get_cached("quiz_html", export_quiz_html, _exp_quiz)
                        st.download_button(
                            label=f"📥 HTML Quiz ({len(_exp_quiz.questions)}Q)",
                            data=html_content,
                            file_name="quizz_interactif.html",
                            mime="text/html",
                            # type="primary",
                            width='stretch',
                            key="exp_tab_quiz_html",
                        )
                    with col_q2:
                        csv_content = _get_cached("quiz_csv", export_quiz_csv, _exp_quiz)
                        st.download_button(
                            label=f"📊 CSV Quiz ({len(_exp_quiz.questions)}Q)",
                            data=csv_content,
                            file_name="quizz.csv",
                            mime="text/csv",
                            width='stretch',
                            key="exp_tab_quiz_csv",
                        )

                if _exp_exercises:
                    st.markdown("**Exercices**")
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        html_ex = _get_cached("ex_html", export_exercises_html, _exp_exercises)
                        st.download_button(
                            label=f"📥 HTML Exercices ({len(_exp_exercises)}Ex)",
                            data=html_ex,
                            file_name="exercices.html",
                            mime="text/html",
                            # type="primary",
                            width='stretch',
                            key="exp_tab_ex_html",
                        )
                    with col_e2:
                        csv_ex = _get_cached("ex_csv", export_exercises_csv, _exp_exercises)
                        st.download_button(
                            label=f"📊 CSV Exercices ({len(_exp_exercises)}Ex)",
                            data=csv_ex,
                            file_name="exercices.csv",
                            mime="text/csv",
                            width='stretch',
                            key="exp_tab_ex_csv",
                        )

                if _exp_quiz and _exp_quiz.questions and _exp_exercises:
                    st.markdown("**Export combiné (Quiz + Exercices)**")
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        combined_html = export_combined_html(_exp_quiz, _exp_exercises)
                        st.download_button(
                            label=f"📥 HTML Combiné ({len(_exp_quiz.questions)}Q + {len(_exp_exercises)}Ex)",
                            data=combined_html,
                            file_name="quiz_exercices.html",
                            mime="text/html",
                            type="primary",
                            width='stretch',
                            key="exp_tab_combined_html",
                        )
                    with col_c2:
                        combined_csv = export_combined_csv(_exp_quiz, _exp_exercises)
                        st.download_button(
                            label=f"📊 CSV Combiné ({len(_exp_quiz.questions)}Q + {len(_exp_exercises)}Ex)",
                            data=combined_csv,
                            file_name="quiz_exercices.csv",
                            mime="text/csv",
                            width='stretch',
                            key="exp_tab_combined_csv",
                        )

                st.caption("Les fichiers HTML sont standalone — ouvrez-les dans n'importe quel navigateur.")
            except Exception as e:
                st.error(f"Erreur lors de l'export : {e}")

            # ─── Section Session Partagée ─────────────────────────────────────
            st.divider()
            st.markdown("#### 📡 Session Partagée")

            if _exp_quiz is not None and _exp_quiz.questions:
                share_title = st.text_input(
                    "Titre de la session partagée",
                    value=_exp_quiz.title,
                    key="share_quiz_title",
                )

                total_q = len(_exp_quiz.questions)
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
                        )
                    with pool_col2:
                        pass_threshold_pct = st.slider(
                            "Seuil de réussite (%)",
                            min_value=0, max_value=100, value=70, step=5,
                            key="share_pass_threshold",
                        )
                    st.caption(f"Pool : {total_q} questions — Passage : {subset_size} questions — Seuil : {pass_threshold_pct}%")

                if st.button("📤 Créer une session partagée", type="secondary", width='stretch', key="export_quiz_share_btn"):
                    try:
                        quiz_data = {
                            "title": _exp_quiz.title,
                            "difficulty": _exp_quiz.difficulty,
                            "questions": [
                                {
                                    "question": q.question, "choices": q.choices,
                                    "correct_answers": q.correct_answers, "explanation": q.explanation,
                                    "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                                    "source_document": q.source_document, "citation": q.citation,
                                    "related_notions": q.related_notions,
                                } for q in _exp_quiz.questions
                            ],
                        }
                        notions_data = []
                        if st.session_state.notions:
                            notions_data = [
                                {"title": n.title, "description": n.description, "enabled": n.enabled}
                                for n in st.session_state.notions
                            ]
                        exercises_data = None
                        if _exp_exercises:
                            exercises_data = [
                                {
                                    "statement": ex.statement, "expected_answer": ex.expected_answer,
                                    "steps": ex.steps, "correction": ex.correction,
                                    "verification_code": ex.verification_code, "verified": ex.verified,
                                    "source_pages": ex.source_pages, "source_document": ex.source_document,
                                    "citation": ex.citation, "difficulty_level": ex.difficulty_level,
                                    "related_notions": ex.related_notions, "exercise_type": ex.exercise_type,
                                    "blanks": ex.blanks, "sub_questions": ex.sub_questions,
                                } for ex in _exp_exercises
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
                            session_obj = create_quiz_session(quiz_data, notions_data, share_title, exercises_data=exercises_data)
                            st.success(f"Session créée ! Code : **{session_obj.session_code}**")
                        st.code(f"Code de session : {session_obj.session_code}", language=None)
                        st.caption("Les participants accèdent au quizz via la page quiz_session avec `?code=" + session_obj.session_code + "`.")
                        increment_stats(sessions=1)
                    except Exception as e:
                        st.error(f"Erreur : {e}")
            else:
                st.caption("Générez un quiz pour créer une session partagée.")

            # ─── Section Atelier Formateur ─────────────────────────────────────
            st.divider()
            st.markdown("#### 🛠️ Atelier Formateur")

            ws_target = st.text_input(
                "Code de l'atelier (vide = créer un nouvel atelier)",
                key="export_ws_code", placeholder="Ex: K8S42X",
            )
            ws_owner = st.text_input("Votre nom", key="export_ws_owner", placeholder="Formateur")

            if _exp_quiz is not None and _exp_quiz.questions:
                if st.button("🛠️ Exporter le quiz vers l'atelier", key="export_to_ws"):
                    quiz_data_export = {
                        "title": _exp_quiz.title,
                        "difficulty": _exp_quiz.difficulty,
                        "questions": [
                            {
                                "question": q.question, "choices": q.choices,
                                "correct_answers": q.correct_answers, "explanation": q.explanation,
                                "source_pages": q.source_pages, "difficulty_level": q.difficulty_level,
                                "source_document": q.source_document, "citation": q.citation,
                                "related_notions": q.related_notions,
                            } for q in _exp_quiz.questions
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
                                st.success(f"✅ {len(_exp_quiz.questions)} question(s) ajoutées à l'atelier **{ws_target.strip().upper()}** ({len(existing_qs)} total)")
                        else:
                            ws_obj = create_work_session(quiz_data_export, notions_export, _exp_quiz.title, owner_name=ws_owner or "?")
                            st.session_state["export_ws_code"] = ws_obj.work_code
                            st.success(f"Atelier créé ! Code : **{ws_obj.work_code}**")
                            st.code(f"Code atelier : {ws_obj.work_code}", language=None)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

            if _exp_exercises:
                if st.button("🛠️ Exporter les exercices vers l'atelier", key="ex_export_to_ws"):
                    exercises_data_ws = [
                        {
                            "statement": ex.statement, "expected_answer": ex.expected_answer,
                            "steps": ex.steps, "correction": ex.correction,
                            "verification_code": ex.verification_code, "verified": ex.verified,
                            "source_pages": ex.source_pages, "source_document": ex.source_document,
                            "citation": ex.citation, "difficulty_level": ex.difficulty_level,
                            "related_notions": ex.related_notions, "exercise_type": ex.exercise_type,
                            "blanks": ex.blanks, "sub_questions": ex.sub_questions,
                        } for ex in _exp_exercises
                    ]
                    notions_export = []
                    if st.session_state.notions:
                        notions_export = [
                            {"title": n.title, "description": n.description, "enabled": n.enabled}
                            for n in st.session_state.notions
                        ]
                    try:
                        if ws_target.strip():
                            existing_ws = get_work_session(ws_target.strip().upper())
                            if existing_ws is None:
                                st.error(f"Atelier introuvable : {ws_target}")
                            else:
                                import json as _json
                                existing_ex = _json.loads(existing_ws.draft_exercises_json or "[]")
                                existing_ex.extend(exercises_data_ws)
                                update_work_session_draft(
                                    ws_target.strip().upper(),
                                    _json.loads(existing_ws.draft_quiz_json),
                                    ws_owner or "?",
                                    notions_export,
                                    exercises_data=existing_ex,
                                )
                                st.success(f"✅ {len(_exp_exercises)} exercice(s) ajoutés à l'atelier **{ws_target.strip().upper()}**")
                        else:
                            ws_obj = create_work_session(
                                {"title": "Exercices", "questions": []},
                                notions_export,
                                "Exercices générés",
                                owner_name=ws_owner or "?",
                                exercises_data=exercises_data_ws,
                            )
                            st.session_state["export_ws_code"] = ws_obj.work_code
                            st.success(f"Atelier créé ! Code : **{ws_obj.work_code}**")
                            st.code(f"Code atelier : {ws_obj.work_code}", language=None)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

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

                notions = detect_notions(chunks, model=selected_model, progress_callback=notion_progress, vision_mode=vision_enabled, enable_thinking=st.session_state.get("enable_thinking", True))
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
                max_correct = num_correct
            else:
                max_correct = st.slider(
                    "Maximum de bonnes réponses (N)",
                    min_value=2,
                    max_value=num_choices - 1,
                    value=num_choices - 1,
                    help="Le LLM choisira entre 1 et N bonnes réponses par question."
                )
                num_correct = 1  # valeur par défaut ignorée en mode variable

            notion_mixing = st.toggle(
                "Mélanger plusieurs notions par question",
                value=True,
                help="Activé : le LLM peut combiner plusieurs notions dans une même question. Désactivé : chaque question porte sur une seule notion.",
            )

            humor = st.toggle(
                "😄 Humour",
                value=False,
                help="Activé : le LLM ajoute un choix de réponse légèrement humoristique ou décalé parmi les mauvaises réponses.",
            )

        # 📝 Édition des prompts
        with st.expander("📝 Personnaliser les Prompts"):
            st.markdown("**1️⃣ Domaine d'expertise** *(persona)*")
            st.caption("Sélectionnez un domaine pour adapter le style et l'expertise de l'IA.")
            _quiz_domain = st.selectbox(
                "Domaine d'expertise",
                options=PERSONA_DOMAINS,
                index=0,
                key="quiz_persona_domain",
                help="Choisissez un domaine DGFiP ou 'Personnalisé' pour un texte libre.",
            )
            if _quiz_domain != "Personnalisé" and st.session_state.get("_last_quiz_domain") != _quiz_domain:
                # Domaine vient de changer — mettre à jour le persona ET la clé du widget
                _domain_persona = get_persona_for_domain(_quiz_domain)
                st.session_state.quiz_persona = _domain_persona
                st.session_state["quiz_persona_text"] = _domain_persona
            st.session_state["_last_quiz_domain"] = _quiz_domain
            st.session_state.quiz_persona = st.text_area(
                "Persona (éditable)",
                value=st.session_state.quiz_persona,
                height=100,
                key="quiz_persona_text",
                help="Modifiez librement le persona, quel que soit le domaine sélectionné.",
            )

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

        # Boutons de génération et réinitialisation
        # Détecter les notions manquantes pour le bouton dédié
        _uncovered_notions_for_btn = []
        if st.session_state.quiz is not None and st.session_state.notions:
            _covered_set = set()
            for _qq in st.session_state.quiz.questions:
                _covered_set.update(_qq.related_notions)
            _uncovered_notions_for_btn = [n for n in st.session_state.notions if n.enabled and n.title not in _covered_set]

        col_gen, col_uncov, col_reset = st.columns([4, 3, 1])
        with col_reset:
            if st.session_state.quiz is not None:
                if st.button("🗑️ Réinit.", key="reset_quiz_btn", help="Supprimer toutes les questions et recommencer"):
                    st.session_state.quiz = None
                    st.session_state.verification_results = None
                    st.session_state._quiz_changelog = []
                    st.session_state._quiz_original_snapshot = None
                    _invalidate_download_cache()
                    st.rerun()
        with col_gen:
            _gen_quiz_clicked = st.button("🚀 Générer le Quizz", type="primary", use_container_width=True)
        with col_uncov:
            _gen_uncovered_clicked = st.button(
                f"🎯 Notions manquantes ({len(_uncovered_notions_for_btn)})",
                disabled=len(_uncovered_notions_for_btn) == 0,
                help="Générer des questions uniquement pour les notions non encore couvertes",
                use_container_width=True,
            )
        _gen_any_clicked = _gen_quiz_clicked or _gen_uncovered_clicked
        if _gen_any_clicked:
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
                # Récupérer les notions activées (filtrées si bouton "notions manquantes")
                active_notions = None
                if st.session_state.notions:
                    if _gen_uncovered_clicked and _uncovered_notions_for_btn:
                        active_notions = _uncovered_notions_for_btn
                    else:
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
                    enable_thinking=st.session_state.get("enable_thinking", True),
                    max_correct=max_correct if variable_correct else None,
                    humor=humor,
                )
                if st.session_state.quiz is None:
                    st.session_state.quiz = quiz
                else:
                    st.session_state.quiz.questions.extend(quiz.questions)
                st.session_state.verification_results = None
                if st.session_state._quiz_original_snapshot is None:
                    st.session_state._quiz_original_snapshot = len(st.session_state.quiz.questions)
                else:
                    st.session_state._quiz_original_snapshot = len(st.session_state.quiz.questions)
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

                        col_edit, col_del = st.columns([8, 1])
                        with col_edit:
                            if st.button("✏️ Éditer", key=f"edit_btn_{i}"):
                                st.session_state._editing_question_idx = i
                                st.rerun()
                        with col_del:
                            if st.button("🗑️", key=f"del_read_{i}", help="Supprimer cette question"):
                                deleted_q = quiz.questions.pop(i)
                                st.session_state._quiz_changelog.append({
                                    "action": "🗑️ Supprimée",
                                    "index": i + 1,
                                    "before": {"question": deleted_q.question, "correct_answers": list(deleted_q.correct_answers)},
                                    "after": None,
                                })
                                st.session_state._editing_question_idx = None
                                _invalidate_download_cache()
                                st.rerun()

            # ─── Notions non couvertes ──────────────────────────────────────
            if st.session_state.notions:
                _covered_notions = set()
                for _q in quiz.questions:
                    _covered_notions.update(_q.related_notions)
                _uncovered = [n for n in st.session_state.notions if n.enabled and n.title not in _covered_notions]
                if _uncovered:
                    st.warning(
                        f"⚠️ **{len(_uncovered)} notion(s) non couvertes** par le quiz : "
                        + ", ".join(f"*{n.title}*" for n in _uncovered)
                        + "\n\nRelancez la génération pour ajouter des questions sur ces notions."
                    )

            # ─── Ajout manuel de question ──────────────────────────────────
            with st.expander("➕ Ajouter une question manuellement", expanded=False):
                _add_q_text = st.text_area("Énoncé de la question", key="add_q_text", height=80)
                _add_q_cols = st.columns(2)
                _add_choices = {}
                for _ci, _cl in enumerate(["A", "B", "C", "D"]):
                    with _add_q_cols[_ci % 2]:
                        _add_choices[_cl] = st.text_input(f"Choix {_cl}", key=f"add_q_choice_{_cl}")
                _add_correct = st.multiselect(
                    "Bonne(s) réponse(s)", options=["A", "B", "C", "D"], key="add_q_correct",
                )
                _add_diff = st.selectbox(
                    "Difficulté", options=["facile", "moyen", "difficile"], index=1, key="add_q_diff",
                )
                _add_expl = st.text_area("Explication", key="add_q_expl", height=60)
                _add_citation = st.text_input("Citation source (optionnel)", key="add_q_cit")
                _add_notions = []
                if st.session_state.notions:
                    _notion_titles = [n.title for n in st.session_state.notions if n.enabled]
                    _add_notions = st.multiselect("Notions associées", options=_notion_titles, key="add_q_notions")

                if st.button("✅ Ajouter la question", key="add_q_btn", disabled=not (_add_q_text and _add_correct and all(_add_choices.values()))):
                    new_q = QuizQuestion(
                        question=_add_q_text,
                        choices=_add_choices,
                        correct_answers=_add_correct,
                        explanation=_add_expl,
                        citation=_add_citation,
                        difficulty_level=_add_diff,
                        related_notions=_add_notions,
                    )
                    quiz.questions.append(new_q)
                    st.session_state._quiz_changelog.append({
                        "action": "➕ Ajout manuel",
                        "index": len(quiz.questions),
                        "before": None,
                        "after": {"question": _add_q_text, "correct_answers": _add_correct},
                    })
                    _invalidate_download_cache()
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
                        enable_thinking=st.session_state.get("enable_thinking", True),
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

                            # Montrer les changements de réponses correctes
                            before_ans = before.get("correct_answers", [])
                            after_ans = after.get("correct_answers", [])
                            if before_ans != after_ans:
                                st.markdown(f"Réponses correctes : `{before_ans}` → `{after_ans}`")

                            # Montrer les choix de réponse modifiés
                            before_choices = before.get("choices", {})
                            after_choices = after.get("choices", {})
                            if before_choices and after_choices and before_choices != after_choices:
                                changed_choices = [(k, before_choices.get(k, ""), after_choices.get(k, "")) for k in after_choices if after_choices.get(k) != before_choices.get(k)]
                                if changed_choices:
                                    with st.expander(f"🔀 {len(changed_choices)} choix modifié(s)", expanded=False):
                                        for key, b_val, a_val in changed_choices:
                                            st.markdown(f"**{key} :** ~~{b_val}~~ → {a_val}")

                            # Montrer les changements d'explication
                            before_exp = before.get("explanation", "")
                            after_exp = after.get("explanation", "")
                            if before_exp != after_exp and after_exp:
                                st.caption(f"💡 Explication mise à jour")

                        if idx < len(changelog) - 1:
                            st.markdown("---")

            st.info("📦 Retrouvez les exports (téléchargements, sessions partagées, ateliers) dans l'onglet **Exports**.")

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
            # Section 1 : Persona par domaine
            st.markdown("**1. Domaine d'expertise** *(persona)*")
            _ex_domain = st.selectbox(
                "Domaine d'expertise (exercices)",
                options=PERSONA_DOMAINS,
                index=0,
                key="ex_persona_domain",
                help="Choisissez un domaine DGFiP ou 'Personnalisé' pour un texte libre.",
            )
            if _ex_domain != "Personnalisé" and st.session_state.get("_last_ex_domain") != _ex_domain:
                _ex_domain_persona = get_persona_for_domain(_ex_domain)
                st.session_state.exercise_persona = _ex_domain_persona
                st.session_state["ex_persona_text"] = _ex_domain_persona
            st.session_state["_last_ex_domain"] = _ex_domain
            st.session_state.exercise_persona = st.text_area(
                "Persona (éditable)",
                value=st.session_state.exercise_persona,
                height=100,
                key="ex_persona_text",
                help="Modifiez librement le persona, quel que soit le domaine sélectionné.",
            )

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
                    enable_thinking=st.session_state.get("enable_thinking", True),
                )
                # Accumulation : ajouter sans écraser les exercices existants
                if st.session_state.exercises is None:
                    st.session_state.exercises = exercises
                else:
                    st.session_state.exercises = st.session_state.exercises + exercises
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

            # Compteur par type
            type_counts = {}
            for ex in exercises:
                t = getattr(ex, 'exercise_type', 'calcul')
                type_counts[t] = type_counts.get(t, 0) + 1
            type_summary = " + ".join(f"{v} {k}" for k, v in type_counts.items())

            col_ex_title, col_ex_clear = st.columns([4, 1])
            with col_ex_title:
                st.markdown(f"### {len(exercises)} exercice(s) ({type_summary})")
            with col_ex_clear:
                if st.button("Effacer tout", key="clear_exercises_btn"):
                    st.session_state.exercises = None
                    _invalidate_download_cache()
                    st.rerun()

            def _render_exercise_card(ex, idx, key_prefix=""):
                """Affiche une carte d'exercice dans un st.expander."""
                diff_label = ex.difficulty_level or "moyen"
                diff_emoji = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}.get(diff_label, "⬜")
                ex_type = getattr(ex, "exercise_type", "calcul")
                if ex.verified:
                    verified_label = "✅ Vérifié (code)" if ex_type == "calcul" else "✅ Vérifié (LLM)"
                else:
                    verified_label = "⚠️ Non vérifié"
                with st.expander(
                    f"{diff_emoji} **Exercice {idx+1}** — {verified_label}",
                    expanded=True
                ):
                    if ex.verified:
                        if ex_type == "calcul":
                            st.success("✅ Réponse vérifiée par exécution de code Python")
                        else:
                            st.success("✅ Réponse vérifiée par auto-correction LLM")
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

                    if ex_type == "trou":
                        blanks = getattr(ex, "blanks", [])
                        if blanks:
                            st.markdown("#### ✏️ Réponses attendues")
                            for b in blanks:
                                b_pos = b.get('position', '?')
                                st.markdown(f"**Blanc {b_pos} :** `{b.get('answer', '')}` — *{b.get('context', '')}*")
                            # Bouton suggestions par blanc
                            st.divider()
                            _sugg_col1, _sugg_col2 = st.columns([3, 1])
                            with _sugg_col1:
                                _sugg_blank_idx = st.selectbox(
                                    "Blanc à aider",
                                    options=list(range(len(blanks))),
                                    format_func=lambda idx: f"Blanc {blanks[idx].get('position', idx+1)} : {blanks[idx].get('context', '')[:40]}…",
                                    key=f"sugg_blank_sel_{idx}",
                                )
                            with _sugg_col2:
                                _sugg_n = st.number_input("Nb suggestions", min_value=1, max_value=5, value=3, key=f"sugg_n_{idx}")
                            if st.button("💡 Générer des indices", key=f"sugg_btn_{idx}"):
                                with st.spinner("Génération des indices…"):
                                    try:
                                        _suggestions = generate_blank_suggestions(
                                            blank=blanks[_sugg_blank_idx],
                                            statement=ex.statement,
                                            n=_sugg_n,
                                            model=selected_model,
                                            enable_thinking=st.session_state.get("enable_thinking", True),
                                        )
                                        st.session_state[f"_sugg_cache_{idx}_{_sugg_blank_idx}"] = _suggestions
                                    except Exception as e:
                                        st.error(f"Erreur : {e}")
                            _cached_sugg = st.session_state.get(f"_sugg_cache_{idx}_{_sugg_blank_idx}")
                            if _cached_sugg:
                                for _si, _s in enumerate(_cached_sugg, 1):
                                    st.info(f"💡 **Indice {_si} :** {_s}")
                    elif ex_type == "cas_pratique":
                        sub_qs = getattr(ex, "sub_questions", [])
                        if sub_qs:
                            st.markdown("#### ❓ Sous-questions & Réponses")
                            for j, sq in enumerate(sub_qs):
                                st.markdown(f"**Q{j+1} :** {sq.get('question', '')}")
                                st.markdown(f"> {sq.get('answer', '')}")
                    else:
                        sub_parts = getattr(ex, "sub_parts", [])
                        if sub_parts:
                            st.markdown("#### 🔢 Questions")
                            for sp_idx, sp in enumerate(sub_parts):
                                sp_verified = sp.get("verified", False)
                                sp_icon = "✅" if sp_verified else "⚠️"
                                st.markdown(f"**{sp_icon} Q{sp_idx+1}.** {sp.get('question', '')}")
                                st.markdown(f"🎯 Réponse attendue : `{sp.get('expected_answer', '')}`")
                                sp_steps = sp.get("steps", [])
                                if sp_steps:
                                    for sj, sstep in enumerate(sp_steps):
                                        st.markdown(f"   {sj+1}. {sstep}")
                                if sp.get("verification_output"):
                                    st.caption(sp["verification_output"])
                                st.markdown("---")
                        else:
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

                    if ex.correction:
                        st.markdown("#### 🤖 Correction IA")
                        st.markdown(ex.correction)

                    render_source_info(ex.source_document, ex.source_pages)

                    if ex.citation:
                        st.markdown(f"📝 **Citation :** *\"{ex.citation}\"*")

            # Affichage groupé par type si plusieurs types
            type_labels = {"calcul": "🔢 Calcul", "trou": "✏️ Questions à trou", "cas_pratique": "📋 Cas pratique"}
            type_groups = {}
            for i, ex in enumerate(exercises):
                t = getattr(ex, 'exercise_type', 'calcul')
                type_groups.setdefault(t, []).append((i, ex))

            if len(type_groups) > 1:
                tab_names = [f"{type_labels.get(t, t)} ({len(exs)})" for t, exs in type_groups.items()]
                ex_type_tabs = st.tabs(tab_names)
                for tab, (t, exs) in zip(ex_type_tabs, type_groups.items()):
                    with tab:
                        for orig_idx, ex in exs:
                            _render_exercise_card(ex, orig_idx, key_prefix=f"{t}_")
            else:
                for i, ex in enumerate(exercises):
                    _render_exercise_card(ex, i)
            st.info("📦 Retrouvez les exports (téléchargements, sessions partagées, ateliers) dans l'onglet **Exports**.")

    # ═══ ONGLET APERÇU TEXTE ════════════════════════════════════════════════════

    with tab_preview:
        st.markdown("### 👁️ Aperçu du texte extrait")
        st.caption(f"Mode de lecture : **{read_mode}** — {len(chunks)} chunks créés")

        # Filtre par document
        doc_names = sorted(set(c.source_document for c in chunks if c.source_document))
        if len(doc_names) > 1:
            selected_doc = st.selectbox(
                "Filtrer par document",
                ["Tous les documents"] + doc_names,
                key="preview_doc_filter",
            )
            if selected_doc != "Tous les documents":
                filtered_chunks = [(idx, c) for idx, c in enumerate(chunks) if c.source_document == selected_doc]
            else:
                filtered_chunks = list(enumerate(chunks))
        else:
            filtered_chunks = list(enumerate(chunks))

        # Pagination de l'aperçu
        CHUNKS_PER_PAGE = 20
        total_pages_preview = max(1, (len(filtered_chunks) + CHUNKS_PER_PAGE - 1) // CHUNKS_PER_PAGE)

        if total_pages_preview > 1:
            preview_page = st.number_input(
                "Page", min_value=1, max_value=total_pages_preview, value=1,
                key="preview_page",
                help=f"{total_pages_preview} page(s) de {CHUNKS_PER_PAGE} chunks"
            )
        else:
            preview_page = 1

        start_idx = (preview_page - 1) * CHUNKS_PER_PAGE
        end_idx = min(start_idx + CHUNKS_PER_PAGE, len(filtered_chunks))
        
        for pos, (orig_idx, chunk) in enumerate(filtered_chunks[start_idx:end_idx]):
            doc_label = f"📄 {chunk.source_document} — " if chunk.source_document else ""
            with st.expander(
                f"{doc_label}Chunk {orig_idx+1} — {chunk.token_count} tokens — "
                f"Pages {', '.join(map(str, chunk.source_pages))}",
                expanded=(pos == 0)
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

        st.markdown("### 📖 Comment fonctionne le pipeline en détail")
        st.markdown("""
**1. Upload et extraction texte**
Les documents (PDF, DOCX, ODT, PPTX, TXT) sont convertis en texte brut avec métadonnées de page. Chaque page est annotée avec des marqueurs `[Début Page X]...[Fin Page X]` pour la traçabilité.

**2. Chunking par blocs de tokens**
Le texte est découpé en **chunks de 10 000 tokens** (par défaut) avec un chevauchement de 200 tokens entre chunks consécutifs. Ce chevauchement garantit qu'aucune information n'est perdue aux frontières. Chaque chunk conserve les numéros de pages source.

**3. Détection des notions fondamentales**
Le LLM analyse chaque chunk pour identifier les concepts clés (notions). Les notions similaires entre chunks sont fusionnées. Le formateur peut ensuite activer, désactiver, éditer ou fusionner les notions.

**4. Génération de questions/exercices par chunk**
Pour chaque niveau de difficulté, les questions sont **réparties proportionnellement** entre les chunks selon leur taille en tokens. Un chunk de 8 000 tokens recevra plus de questions qu'un chunk de 3 000 tokens. L'**anti-duplication** transmet les questions déjà générées au LLM pour éviter les doublons entre niveaux.

**5. Vérification IA (optionnel)**
Le LLM tente de répondre à chaque question comme un étudiant. S'il échoue, la question est reformulée (max 3 tentatives) puis supprimée si non corrigeable. Les exercices de calcul sont vérifiés par exécution Python sandboxée.

**6. Export et sessions**
Les résultats sont exportables en HTML interactif ou CSV. Les sessions partagées permettent aux participants de répondre via un code d'accès, avec scoring côté serveur et analytics en temps réel.
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
                        response = call_llm_chat(api_messages, temperature=0.5, enable_thinking=st.session_state.get("enable_thinking", True))
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
                        enable_thinking=st.session_state.get("enable_thinking", True),
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
                        enable_thinking=st.session_state.get("enable_thinking", True),
                    )
                    # Accumulation
                    if st.session_state.exercises is None:
                        st.session_state.exercises = exercises
                    else:
                        st.session_state.exercises = st.session_state.exercises + exercises
                    st.session_state.chat_session.exercises = st.session_state.exercises
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
                        enable_thinking=st.session_state.get("enable_thinking", True),
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

