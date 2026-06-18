<template>
    <h1>Générer un quiz</h1>

    <div v-if="store.error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ store.error }}</p>
    </div>

    <!-- Étape 1 : Document -->
    <section class="fr-mb-4w">
        <h2 class="fr-h4">1. Document(s) source</h2>
        <div class="fr-upload-group">
            <label class="fr-label" for="files">
                Fichiers
                <span class="fr-hint-text">PDF, DOCX, PPTX, ODT, TXT — plusieurs possibles.</span>
            </label>
            <input
                id="files"
                class="fr-upload"
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.odt,.odp,.ods,.txt"
                :disabled="store.busy === 'upload'"
                @change="onFilesChange"
            />
        </div>
        <div class="fr-checkbox-group fr-mt-1w">
            <input id="vision" type="checkbox" v-model="visionMode" :disabled="store.busy === 'upload' || oneShot" />
            <label class="fr-label" for="vision">
                Mode Vision (PDF → images)
                <span class="fr-hint-text">Analyse les pages PDF en images (schémas, formules). Nécessite un modèle vision configuré.</span>
            </label>
        </div>
        <div class="fr-checkbox-group">
            <input id="oneshot" type="checkbox" v-model="oneShot" :disabled="store.busy === 'upload'" />
            <label class="fr-label" for="oneshot">
                Mode One-shot
                <span class="fr-hint-text">
                    Envoie tout le(s) document(s) en un minimum de blocs au modèle à grand contexte
                    (vision, DPI fixe). Idéal pour une vue d'ensemble.
                </span>
            </label>
        </div>

        <details class="fr-mt-2w prompt-editor">
            <summary class="fr-text--sm">⚙️ Réglages avancés du découpage</summary>
            <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
                <div class="fr-col-12 fr-col-md-6">
                    <label class="fr-label fr-text--sm" for="adv-maxtok">
                        Taille de bloc (tokens, mode texte)
                        <span class="fr-hint-text">0 = valeur par défaut</span>
                    </label>
                    <input id="adv-maxtok" class="fr-input" type="number" min="0" step="1000" v-model.number="advUpload.max_tokens" />
                </div>
                <div class="fr-col-12 fr-col-md-6">
                    <label class="fr-label fr-text--sm" for="adv-imgpc">
                        Pages par bloc (mode vision)
                    </label>
                    <input id="adv-imgpc" class="fr-input" type="number" min="1" max="50" v-model.number="advUpload.max_images_per_chunk" />
                </div>
                <div class="fr-col-6 fr-col-md-6">
                    <label class="fr-label fr-text--sm" for="adv-mindpi">DPI min (vision)</label>
                    <input id="adv-mindpi" class="fr-input" type="number" min="40" max="300" v-model.number="advUpload.min_dpi" />
                </div>
                <div class="fr-col-6 fr-col-md-6">
                    <label class="fr-label fr-text--sm" for="adv-maxdpi">DPI max (vision)</label>
                    <input id="adv-maxdpi" class="fr-input" type="number" min="40" max="300" v-model.number="advUpload.max_dpi" />
                </div>
            </div>
        </details>

        <button
            class="fr-btn fr-mt-2w"
            :disabled="!selectedFiles.length || store.busy === 'upload'"
            @click="upload"
        >
            {{ store.busy === 'upload' ? 'Analyse…' : 'Analyser les documents' }}
        </button>

        <div v-if="store.upload" class="fr-mt-2w fr-text--sm">
            <p class="fr-mb-1v">
                <strong>{{ store.upload.num_chunks }}</strong> blocs •
                <strong>{{ store.upload.total_tokens }}</strong> tokens •
                {{ store.upload.documents.length }} document(s)
            </p>
            <ul class="fr-mb-0">
                <li v-for="doc in store.upload.documents" :key="doc.name">
                    {{ doc.name }} — {{ doc.total_tokens }} tokens
                </li>
            </ul>
        </div>
    </section>

    <!-- Étape 2 : Notions -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">2. Notions fondamentales</h2>
        <button
            class="fr-btn fr-btn--secondary"
            :disabled="store.busy === 'notions'"
            @click="store.detectNotions()"
        >
            {{ store.busy === 'notions' ? 'Détection…' : 'Détecter les notions' }}
        </button>
        <button class="fr-btn fr-btn--secondary fr-ml-1w" @click="addNotionAndEdit">
            ➕ Ajouter une notion
        </button>
        <GenerationProgress kind="notions" />

        <div v-if="store.notions.length" class="fr-mt-2w">
            <div class="fr-grid-row fr-grid-row--middle fr-mb-1v">
                <p class="fr-col fr-text--sm fr-mb-0">
                    {{ store.enabledNotions.length }} / {{ store.notions.length }} notions activées
                </p>
                <div class="fr-col-auto">
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.toggleAllNotions(true)"
                    >
                        ✓ Tout cocher
                    </button>
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.toggleAllNotions(false)"
                    >
                        ✗ Tout décocher
                    </button>
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :disabled="store.busy === 'notions'"
                        @click="store.mergeNotions()"
                    >
                        🔗 Fusionner (IA)
                    </button>
                    <button
                        class="fr-btn fr-btn--tertiary fr-btn--sm"
                        :class="{ 'fr-btn--secondary': notionsGrouped }"
                        @click="notionsGrouped = !notionsGrouped"
                    >
                        🗂️ Par thématique
                    </button>
                </div>
            </div>

            <template v-for="[category, group] in displayGroups" :key="category || '_flat'">
                <h3 v-if="notionsGrouped" class="fr-h6 fr-mt-2w fr-mb-1v">{{ category }}</h3>
                <div
                    v-for="notion in group"
                    :key="notionIndex(notion)"
                    class="notion-row fr-mb-1v"
                >
                    <!-- Édition manuelle d'une notion -->
                    <div v-if="editingNotionIndex === notionIndex(notion)" class="notion-edit fr-p-2w">
                        <input class="fr-input fr-mb-1v" v-model="notion.title" placeholder="Titre" />
                        <input class="fr-input fr-mb-1v" v-model="notion.category" placeholder="Catégorie / thématique" />
                        <textarea class="fr-input fr-mb-1v" rows="2" v-model="notion.description" placeholder="Description" />
                        <button class="fr-btn fr-btn--sm" @click="editingNotionIndex = -1">✓ Terminer</button>
                    </div>
                    <!-- Lecture -->
                    <div v-else class="fr-grid-row fr-grid-row--middle">
                        <div class="fr-col">
                            <div class="fr-checkbox-group fr-checkbox-group--sm">
                                <input :id="`notion-${notionIndex(notion)}`" type="checkbox" v-model="notion.enabled" />
                                <label class="fr-label" :for="`notion-${notionIndex(notion)}`">
                                    <strong>{{ notion.title || '(sans titre)' }}</strong>
                                    <span v-if="notion.category && !notionsGrouped" class="fr-badge fr-badge--sm fr-ml-1v">
                                        {{ notion.category }}
                                    </span>
                                    <span
                                        v-if="store.notionQuestionCounts[notion.title]"
                                        class="fr-badge fr-badge--sm fr-badge--green-emeraude fr-ml-1v"
                                        title="Questions rattachées à cette notion"
                                    >
                                        {{ store.notionQuestionCounts[notion.title] }} Q
                                    </span>
                                    <span class="fr-hint-text">{{ notion.description }}</span>
                                </label>
                            </div>
                        </div>
                        <div class="fr-col-auto">
                            <button
                                class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                                @click="editingNotionIndex = notionIndex(notion)"
                            >
                                ✏️
                            </button>
                            <button
                                class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                                @click="store.deleteNotion(notion)"
                            >
                                🗑️
                            </button>
                        </div>
                    </div>
                </div>
            </template>

            <div class="fr-input-group fr-mt-2w">
                <label class="fr-label fr-text--sm" for="notion-edit">💬 Modifier les notions avec l'IA</label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input
                            id="notion-edit"
                            class="fr-input"
                            v-model="notionInstruction"
                            placeholder="Ex : ajoute une notion sur les dérivées partielles"
                            :disabled="store.busy === 'notions'"
                            @keyup.enter="editNotions"
                        />
                    </div>
                    <div class="fr-col-auto">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="store.busy === 'notions' || !notionInstruction.trim()"
                            @click="editNotions"
                        >
                            Appliquer
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Étape 2 bis : Acronymes -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">2 bis. Acronymes</h2>
        <button
            class="fr-btn fr-btn--secondary"
            :disabled="store.busy === 'acronyms'"
            @click="store.detectAcronyms()"
        >
            {{ store.busy === 'acronyms' ? 'Détection…' : 'Détecter les acronymes' }}
        </button>
        <button class="fr-btn fr-btn--secondary fr-ml-1w" @click="store.addAcronym()">
            ➕ Ajouter un acronyme
        </button>

        <div v-if="store.acronyms.length" class="fr-mt-2w">
            <div
                v-for="(a, i) in store.acronyms"
                :key="i"
                class="fr-grid-row fr-grid-row--gutters fr-grid-row--middle fr-mb-1v"
            >
                <div class="fr-col-auto">
                    <div class="fr-checkbox-group fr-checkbox-group--sm">
                        <input :id="`acro-${i}`" type="checkbox" v-model="a.enabled" />
                        <label class="fr-label" :for="`acro-${i}`">
                            <span class="fr-sr-only">Acronyme actif</span>
                        </label>
                    </div>
                </div>
                <div class="fr-col-3">
                    <input class="fr-input" v-model="a.acronym" placeholder="Sigle" />
                </div>
                <div class="fr-col">
                    <input class="fr-input" v-model="a.definition" placeholder="Définition" />
                </div>
                <div class="fr-col-auto">
                    <button
                        class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                        @click="store.deleteAcronym(i)"
                    >
                        🗑️
                    </button>
                </div>
            </div>

            <div class="fr-input-group fr-mt-2w">
                <label class="fr-label fr-text--sm" for="acro-edit">💬 Modifier les acronymes avec l'IA</label>
                <div class="fr-grid-row fr-grid-row--gutters fr-grid-row--bottom">
                    <div class="fr-col">
                        <input
                            id="acro-edit"
                            class="fr-input"
                            v-model="acronymInstruction"
                            placeholder="Ex : ajoute la définition de DGFIP, supprime les sigles non pertinents"
                            :disabled="store.busy === 'acronyms'"
                            @keyup.enter="editAcronyms"
                        />
                    </div>
                    <div class="fr-col-auto">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="store.busy === 'acronyms' || !acronymInstruction.trim()"
                            @click="editAcronyms"
                        >
                            Appliquer
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Étape 3 : Configuration -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">3. Configuration</h2>
        <div class="fr-grid-row fr-grid-row--gutters">
            <div class="fr-col-6 fr-col-md-3" v-for="level in levels" :key="level.key">
                <label class="fr-label" :for="`count-${level.key}`">{{ level.label }}</label>
                <input
                    :id="`count-${level.key}`"
                    class="fr-input"
                    type="number"
                    min="0"
                    max="50"
                    v-model.number="counts[level.key]"
                />
            </div>
        </div>

        <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
            <div class="fr-col-6 fr-col-md-3">
                <label class="fr-label" for="num-choices">Choix par question</label>
                <input
                    id="num-choices"
                    class="fr-input"
                    type="number"
                    min="2"
                    max="6"
                    v-model.number="config.num_choices"
                />
            </div>
            <div class="fr-col-6 fr-col-md-3">
                <label class="fr-label" for="num-correct">Bonnes réponses</label>
                <input
                    id="num-correct"
                    class="fr-input"
                    type="number"
                    min="1"
                    :max="config.num_choices - 1"
                    :disabled="config.variable_correct || config.vrai_faux"
                    v-model.number="config.num_correct"
                />
            </div>
        </div>

        <div class="fr-mt-2w">
            <div class="fr-checkbox-group">
                <input id="variable" type="checkbox" v-model="config.variable_correct" />
                <label class="fr-label" for="variable">Nombre de bonnes réponses variable</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="vraifaux" type="checkbox" v-model="config.vrai_faux" />
                <label class="fr-label" for="vraifaux">Mode Vrai / Faux</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="humor" type="checkbox" v-model="config.humor" />
                <label class="fr-label" for="humor">Touche d'humour</label>
            </div>
            <div class="fr-checkbox-group">
                <input id="batch" type="checkbox" v-model="config.batch_mode" />
                <label class="fr-label" for="batch">
                    Traitement par lots (Batch API)
                    <span class="fr-hint-text">Plus rapide si le serveur supporte /v1/batches.</span>
                </label>
            </div>
            <div class="fr-checkbox-group">
                <input id="thinking" type="checkbox" v-model="config.enable_thinking" />
                <label class="fr-label" for="thinking">
                    Mode raisonnement (thinking)
                    <span class="fr-hint-text">Améliore la qualité des questions ; un peu plus lent.</span>
                </label>
            </div>
            <div class="fr-checkbox-group">
                <input id="mixing" type="checkbox" v-model="config.notion_mixing" />
                <label class="fr-label" for="mixing">
                    Mélange des notions
                    <span class="fr-hint-text">Répartit les questions sur l'ensemble des notions sélectionnées.</span>
                </label>
            </div>
        </div>

        <div class="fr-input-group fr-mt-2w">
            <label class="fr-label" for="persona">
                Persona expert <span class="fr-hint-text">(optionnel)</span>
            </label>
            <input
                id="persona"
                class="fr-input"
                v-model="config.persona"
                placeholder="Ex : Tu es un expert en droit fiscal."
            />
        </div>
        <div class="fr-input-group">
            <label class="fr-label" for="instructions">
                Consignes libres <span class="fr-hint-text">(optionnel)</span>
            </label>
            <textarea id="instructions" class="fr-input" rows="3" v-model="config.user_instructions" />
        </div>
        <div class="fr-checkbox-group">
            <input id="classify-quiz" type="checkbox" v-model="classifyQuiz" />
            <label class="fr-label" for="classify-quiz">
                Analyser la consigne (style vs périmètre)
                <span class="fr-hint-text">
                    Sépare automatiquement la consigne : le « périmètre » filtre les passages du
                    document, le « style » guide la formulation.
                </span>
            </label>
        </div>

        <details class="fr-mt-2w prompt-editor">
            <summary class="fr-text--sm">⚙️ Personnaliser les consignes par niveau (quiz)</summary>
            <p v-if="store.promptDefaults?.fixed_rules.quiz" class="fr-text--sm fr-mt-1w fixed-rules">
                🔒 {{ store.promptDefaults.fixed_rules.quiz }}
            </p>
            <div v-for="level in levels" :key="`qp-${level.key}`" class="fr-input-group fr-mt-1w">
                <label class="fr-label fr-text--sm" :for="`qp-${level.key}`">{{ level.label }}</label>
                <textarea
                    :id="`qp-${level.key}`"
                    class="fr-input"
                    rows="3"
                    v-model="quizPrompts[level.key]"
                />
            </div>
            <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="applyQuizDefaults">
                ↺ Réinitialiser
            </button>
        </details>

        <button
            class="fr-btn fr-mt-2w"
            :disabled="store.busy === 'quiz' || totalQuestions === 0"
            @click="generate"
        >
            {{ store.busy === 'quiz' ? 'Génération en cours…' : `Générer ${totalQuestions} question(s)` }}
        </button>
        <button class="fr-btn fr-btn--secondary fr-mt-2w fr-ml-1w" @click="store.addQuestion()">
            ➕ Ajouter une question manuelle
        </button>
        <GenerationProgress kind="quiz" />
        <p v-if="store.busy === 'quiz' && !store.progress.total" class="fr-text--sm fr-mt-1v">
            La génération peut prendre plusieurs minutes selon le volume.
        </p>

        <details class="fr-mt-3w prompt-editor">
            <summary class="fr-text--sm">🧠 Générer des questions sans document (base du modèle)</summary>
            <p class="fr-text--sm fr-mt-1w">
                Utile pour compléter un document : pose des questions générales sur un sujet ou
                une notion au-delà de ce que le document contient. Les questions sont ajoutées au
                quiz courant et signalées comme issues de la base du modèle.
            </p>
            <div class="fr-input-group">
                <label class="fr-label fr-text--sm" for="kb-topic">Sujet</label>
                <input
                    id="kb-topic"
                    class="fr-input"
                    v-model="kb.topic"
                    placeholder="Ex : la laïcité dans le service public"
                />
            </div>
            <div class="fr-input-group">
                <label class="fr-label fr-text--sm" for="kb-context">
                    Périmètre / contexte <span class="fr-hint-text">(optionnel)</span>
                </label>
                <textarea
                    id="kb-context"
                    class="fr-input"
                    rows="2"
                    v-model="kb.additional_context"
                />
            </div>
            <div class="fr-grid-row fr-grid-row--gutters">
                <div class="fr-col-4" v-for="level in levels" :key="`kb-${level.key}`">
                    <label class="fr-label fr-text--sm" :for="`kb-count-${level.key}`">
                        {{ level.label }}
                    </label>
                    <input
                        :id="`kb-count-${level.key}`"
                        class="fr-input"
                        type="number"
                        min="0"
                        max="50"
                        v-model.number="kbCounts[level.key]"
                    />
                </div>
            </div>
            <button
                class="fr-btn fr-btn--secondary fr-mt-2w"
                :disabled="store.busy === 'quiz' || !kb.topic.trim() || kbTotal === 0"
                @click="generateFromKnowledge"
            >
                {{ store.busy === 'quiz' ? 'Génération…' : `Générer ${kbTotal} question(s) sans document` }}
            </button>
        </details>
    </section>

    <!-- Étape 4 : Résultats -->
    <section v-if="store.questions.length" class="fr-mb-4w">
        <h2 class="fr-h4">4. Quiz généré ({{ store.questions.length }} questions)</h2>

        <div class="fr-grid-row fr-grid-row--middle fr-mb-2w fr-grid-row--gutters">
            <div class="fr-col-auto">
                <button
                    class="fr-btn fr-btn--secondary"
                    :disabled="store.busy === 'verify'"
                    @click="store.verifyQuiz()"
                >
                    {{ store.busy === 'verify' ? 'Vérification…' : '🔍 Vérifier les réponses (IA)' }}
                </button>
            </div>
            <div class="fr-col-auto">
                <button
                    class="fr-btn fr-btn--tertiary"
                    :disabled="!store.canUndo"
                    @click="store.undo()"
                >
                    ↩ Annuler la dernière modification
                </button>
            </div>
        </div>
        <GenerationProgress kind="verify" />
        <div v-if="store.verifyResults.length" class="fr-alert fr-alert--info fr-mb-2w">
            <p class="fr-mb-0">
                Vérification : {{ verifySummary.verified }} validée(s),
                {{ verifySummary.reformulated }} reformulée(s),
                {{ verifySummary.deleted }} supprimée(s).
            </p>
        </div>

        <QuestionCard
            v-for="(q, qi) in store.questions"
            :key="qi"
            :question="q"
            :index="qi"
        />

        <!-- Exports -->
        <div class="fr-p-3w session-box fr-mb-3w">
            <h3 class="fr-h6">Exporter</h3>
            <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('html', 'quiz')">
                    Quiz HTML
                </button>
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('csv', 'quiz')">
                    Quiz CSV
                </button>
                <button class="fr-btn fr-btn--tertiary" @click="store.exportFile('moodle', 'quiz')">
                    Quiz Moodle XML
                </button>
                <button
                    v-if="store.exercises.length"
                    class="fr-btn fr-btn--tertiary"
                    @click="store.exportFile('html', 'combined')"
                >
                    Quiz + Exercices HTML
                </button>
            </div>
        </div>

        <!-- Création de session partagée -->
        <div class="fr-p-3w session-box">
            <h3 class="fr-h6">Partager en session</h3>
            <div class="fr-input-group">
                <label class="fr-label" for="session-title">Titre de la session</label>
                <input id="session-title" class="fr-input" v-model="sessionTitle" />
            </div>
            <div class="fr-checkbox-group">
                <input id="pool-mode" type="checkbox" v-model="poolMode" />
                <label class="fr-label" for="pool-mode">
                    Mode Pool
                    <span class="fr-hint-text">
                        Chaque participant tire un sous-ensemble aléatoire de questions ; il peut
                        réessayer avec de nouvelles questions.
                    </span>
                </label>
            </div>
            <div v-if="poolMode" class="fr-grid-row fr-grid-row--gutters">
                <div class="fr-col-6">
                    <label class="fr-label fr-text--sm" for="subset-size">Questions par participant</label>
                    <input id="subset-size" class="fr-input" type="number" min="1" :max="store.questions.length" v-model.number="subsetSize" />
                </div>
                <div class="fr-col-6">
                    <label class="fr-label fr-text--sm" for="pass-threshold">Seuil de réussite (%)</label>
                    <input id="pass-threshold" class="fr-input" type="number" min="0" max="100" v-model.number="passThreshold" />
                </div>
            </div>
            <button
                class="fr-btn fr-mt-1w"
                :disabled="store.busy === 'session' || !sessionTitle.trim()"
                @click="createSession"
            >
                {{ store.busy === 'session' ? 'Création…' : poolMode ? 'Créer la session pool' : 'Créer la session' }}
            </button>

            <div v-if="sessionCode" class="fr-alert fr-alert--success fr-mt-2w">
                <p>
                    Session créée — code <strong>{{ sessionCode }}</strong>.
                    <RouterLink :to="{ name: 'ParticipantPage', query: { code: sessionCode } }">
                        Page participant
                    </RouterLink>
                    ·
                    <RouterLink :to="{ name: 'AnalyticsPage', query: { code: sessionCode } }">
                        Analytics
                    </RouterLink>
                </p>
            </div>

            <hr class="fr-mt-2w fr-mb-2w" />
            <h3 class="fr-h6">Ou exporter vers un atelier formateur</h3>
            <button
                class="fr-btn fr-btn--secondary"
                :disabled="store.busy === 'workshop' || !sessionTitle.trim()"
                @click="createWorkshop"
            >
                {{ store.busy === 'workshop' ? 'Création…' : 'Créer un atelier' }}
            </button>
            <div v-if="workshopCode" class="fr-alert fr-alert--success fr-mt-2w">
                <p>
                    Atelier créé — code <strong>{{ workshopCode }}</strong>.
                    <RouterLink :to="{ name: 'WorkshopPage', query: { code: workshopCode } }">
                        Ouvrir l'atelier
                    </RouterLink>
                </p>
            </div>
        </div>
    </section>

    <!-- Étape 5 : Exercices -->
    <section v-if="store.upload" class="fr-mb-4w">
        <h2 class="fr-h4">5. Exercices</h2>
        <div class="fr-grid-row fr-grid-row--gutters">
            <div class="fr-col-12 fr-col-md-4">
                <label class="fr-label" for="ex-type">Type</label>
                <select id="ex-type" class="fr-select" v-model="exConfig.exercise_type">
                    <option value="calcul">Calcul numérique</option>
                    <option value="trou">Texte à trou</option>
                    <option value="cas_pratique">Cas pratique</option>
                </select>
            </div>
            <div class="fr-col-4 fr-col-md-2" v-for="level in levels" :key="`ex-${level.key}`">
                <label class="fr-label" :for="`ex-count-${level.key}`">{{ level.label }}</label>
                <input
                    :id="`ex-count-${level.key}`"
                    class="fr-input"
                    type="number"
                    min="0"
                    max="20"
                    v-model.number="exCounts[level.key]"
                />
            </div>
        </div>

        <div class="fr-input-group fr-mt-2w">
            <label class="fr-label" for="ex-persona">
                Persona expert <span class="fr-hint-text">(optionnel)</span>
            </label>
            <input id="ex-persona" class="fr-input" v-model="exConfig.persona" />
        </div>
        <div class="fr-input-group">
            <label class="fr-label" for="ex-instructions">
                Consignes libres <span class="fr-hint-text">(optionnel)</span>
            </label>
            <textarea
                id="ex-instructions"
                class="fr-input"
                rows="2"
                v-model="exConfig.user_instructions"
            />
        </div>
        <div class="fr-checkbox-group">
            <input id="ex-batch" type="checkbox" v-model="exConfig.batch_mode" />
            <label class="fr-label" for="ex-batch">Traitement par lots (Batch API)</label>
        </div>
        <div class="fr-checkbox-group">
            <input id="classify-ex" type="checkbox" v-model="classifyEx" />
            <label class="fr-label" for="classify-ex">
                Analyser la consigne (style vs périmètre)
            </label>
        </div>
        <div class="fr-checkbox-group">
            <input id="ex-thinking" type="checkbox" v-model="exConfig.enable_thinking" />
            <label class="fr-label" for="ex-thinking">Mode raisonnement (thinking)</label>
        </div>
        <div class="fr-checkbox-group">
            <input id="ex-mixing" type="checkbox" v-model="exConfig.notion_mixing" />
            <label class="fr-label" for="ex-mixing">Mélange des notions</label>
        </div>

        <details v-if="exPrompts[exConfig.exercise_type]" class="fr-mt-2w prompt-editor">
            <summary class="fr-text--sm">⚙️ Personnaliser les consignes par niveau (exercices)</summary>
            <p v-if="store.promptDefaults?.fixed_rules.exercises" class="fr-text--sm fr-mt-1w fixed-rules">
                🔒 {{ store.promptDefaults.fixed_rules.exercises }}
            </p>
            <div v-for="level in levels" :key="`ep-${level.key}`" class="fr-input-group fr-mt-1w">
                <label class="fr-label fr-text--sm" :for="`ep-${level.key}`">{{ level.label }}</label>
                <textarea
                    :id="`ep-${level.key}`"
                    class="fr-input"
                    rows="3"
                    v-model="exPrompts[exConfig.exercise_type][level.key]"
                />
            </div>
            <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="applyExerciseDefaults">
                ↺ Réinitialiser
            </button>
        </details>

        <button
            class="fr-btn fr-mt-1w"
            :disabled="store.busy === 'exercises' || totalExercises === 0"
            @click="generateExercises"
        >
            {{ store.busy === 'exercises' ? 'Génération…' : `Générer ${totalExercises} exercice(s)` }}
        </button>
        <button
            class="fr-btn fr-btn--secondary fr-mt-1w fr-ml-1w"
            @click="store.addExercise(exConfig.exercise_type)"
        >
            ➕ Ajouter un exercice manuel
        </button>
        <GenerationProgress kind="exercises" />
        <p v-if="exConfig.exercise_type === 'calcul'" class="fr-text--sm fr-mt-1v">
            ⚠️ Les exercices de calcul sont auto-vérifiés par exécution Python côté serveur
            (sandbox).
        </p>

        <div v-if="store.exercises.length" class="fr-mt-3w">
            <h3 class="fr-h6">{{ store.exercises.length }} exercice(s)</h3>
            <ExerciseCard
                v-for="(ex, ei) in store.exercises"
                :key="ei"
                :exercise="ex"
                :index="ei"
            />
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { ExerciseType, Notion } from '@/services/api';
import { useGenerationStore } from '@/stores/generationStore';
import QuestionCard from '@/components/QuestionCard.vue';
import ExerciseCard from '@/components/ExerciseCard.vue';
import GenerationProgress from '@/components/GenerationProgress.vue';

defineOptions({ name: 'GeneratePage' });

const store = useGenerationStore();

const levels = [
    { key: 'facile', label: '🟢 Facile' },
    { key: 'moyen', label: '🟡 Moyen' },
    { key: 'difficile', label: '🔴 Difficile' },
] as const;

// ── Prompts éditables par niveau ─────────────────────────────────────────────
const quizPrompts = reactive<Record<string, string>>({ facile: '', moyen: '', difficile: '' });
const exPrompts = reactive<Record<string, Record<string, string>>>({});
const classifyQuiz = ref(false);
const classifyEx = ref(false);

function applyQuizDefaults() {
    const d = store.promptDefaults?.quiz;
    if (d) Object.assign(quizPrompts, d);
}
function applyExerciseDefaults() {
    const d = store.promptDefaults?.exercises;
    if (d) for (const [type, prompts] of Object.entries(d)) exPrompts[type] = { ...prompts };
}

onMounted(async () => {
    await store.loadPromptDefaults();
    applyQuizDefaults();
    applyExerciseDefaults();
});
// Si les défauts arrivent après le montage (chargement asynchrone).
watch(
    () => store.promptDefaults,
    () => {
        applyQuizDefaults();
        applyExerciseDefaults();
    },
);

// ── Quiz sans document (base de connaissance du LLM) ─────────────────────────
const kb = reactive({ topic: '', additional_context: '' });
const kbCounts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });
const kbTotal = computed(() =>
    Object.values(kbCounts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

function generateFromKnowledge() {
    sessionCode.value = '';
    store.generateQuizFromKnowledge({
        topic: kb.topic,
        additional_context: kb.additional_context,
        difficulty_counts: { ...kbCounts },
        num_choices: config.num_choices,
        num_correct: config.num_correct,
        variable_correct: config.variable_correct,
        vrai_faux: config.vrai_faux,
        batch_mode: config.batch_mode,
    });
}

const selectedFiles = ref<File[]>([]);
const visionMode = ref(false);
const oneShot = ref(false);
const advUpload = reactive({ max_tokens: 0, max_images_per_chunk: 10, min_dpi: 65, max_dpi: 80 });
const notionInstruction = ref('');
const acronymInstruction = ref('');
const editingNotionIndex = ref(-1);
const notionsGrouped = ref(false);
const counts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });
const config = reactive({
    num_choices: 4,
    num_correct: 1,
    variable_correct: false,
    vrai_faux: false,
    humor: false,
    batch_mode: false,
    persona: '',
    user_instructions: '',
    enable_thinking: true,
    notion_mixing: true,
});
const sessionTitle = ref('');
const sessionCode = ref('');
const workshopCode = ref('');
const poolMode = ref(false);
const subsetSize = ref(5);
const passThreshold = ref(70); // en %

const exCounts = reactive<Record<string, number>>({ facile: 0, moyen: 2, difficile: 0 });
const exConfig = reactive({
    exercise_type: 'calcul' as ExerciseType,
    persona: '',
    user_instructions: '',
    batch_mode: false,
    enable_thinking: true,
    notion_mixing: true,
});

const totalQuestions = computed(() =>
    Object.values(counts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

const totalExercises = computed(() =>
    Object.values(exCounts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

// Notions affichées : groupées par thématique, ou liste plate sous une clé vide.
const displayGroups = computed<[string, Notion[]][]>(() =>
    notionsGrouped.value ? Object.entries(store.notionsByCategory) : [['', store.notions]],
);

const verifySummary = computed(() => ({
    verified: store.verifyResults.filter((r) => r.status === 'verified').length,
    reformulated: store.verifyResults.filter((r) => r.status === 'reformulated').length,
    deleted: store.verifyResults.filter((r) => r.status === 'deleted').length,
}));

function onFilesChange(event: Event) {
    const input = event.target as HTMLInputElement;
    selectedFiles.value = input.files ? Array.from(input.files) : [];
}

function upload() {
    store.uploadDocuments(selectedFiles.value, {
        vision_mode: visionMode.value,
        one_shot: oneShot.value,
        max_tokens: advUpload.max_tokens || undefined,
        max_images_per_chunk: advUpload.max_images_per_chunk,
        min_dpi: advUpload.min_dpi,
        max_dpi: advUpload.max_dpi,
    });
}

function notionIndex(notion: { title: string }) {
    return store.notions.findIndex((n) => n === notion);
}

function addNotionAndEdit() {
    store.addNotion();
    editingNotionIndex.value = store.notions.length - 1;
}

function editAcronyms() {
    store.editAcronyms(acronymInstruction.value);
    acronymInstruction.value = '';
}

function generate() {
    sessionCode.value = '';
    store.generateQuiz({
        difficulty_counts: { ...counts },
        ...config,
        classify_instructions: classifyQuiz.value,
        difficulty_prompts: { ...quizPrompts },
    });
}

function generateExercises() {
    store.generateExercises({
        difficulty_counts: { ...exCounts },
        ...exConfig,
        classify_instructions: classifyEx.value,
        custom_exercise_prompts: { ...(exPrompts[exConfig.exercise_type] ?? {}) },
    });
}

function editNotions() {
    store.editNotions(notionInstruction.value);
    notionInstruction.value = '';
}

async function createSession() {
    sessionCode.value = poolMode.value
        ? await store.createPoolSession(sessionTitle.value, subsetSize.value, passThreshold.value / 100)
        : await store.createSession(sessionTitle.value);
}

async function createWorkshop() {
    workshopCode.value = await store.createWorkshop(sessionTitle.value, '');
}
</script>

<style scoped>
.session-box {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    background: var(--background-alt-grey);
}
.prompt-editor {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    padding: 1rem;
}
.prompt-editor > summary {
    cursor: pointer;
    font-weight: 700;
}
.fixed-rules {
    color: var(--text-mention-grey);
    background: var(--background-alt-grey);
    padding: 0.5rem;
    border-radius: 0.25rem;
}
.notion-edit {
    border: 1px dashed var(--border-default-grey);
    border-radius: 0.25rem;
    background: var(--background-alt-grey);
}
</style>
