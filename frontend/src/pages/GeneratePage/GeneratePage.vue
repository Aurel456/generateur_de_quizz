<template>
    <h1>Générer un quiz</h1>

    <div v-if="store.error" class="fr-alert fr-alert--error fr-mb-3w" role="alert">
        <p>{{ store.error }}</p>
    </div>
    <div v-if="store.notice" class="fr-alert fr-alert--warning fr-alert--sm fr-mb-3w" role="status">
        <p>{{ store.notice }}</p>
    </div>

    <!-- Récapitulatif : ce que les onglets ne montrent plus d'un seul coup d'œil. -->
    <ul v-if="store.upload" class="fr-tags-group fr-mb-2w">
        <li>
            <span class="fr-badge fr-badge--sm fr-badge--blue-cumulus">
                {{ store.upload.documents.length }} document(s) · {{ store.upload.num_chunks }} bloc(s)
            </span>
        </li>
        <li>
            <span class="fr-badge fr-badge--sm">{{ store.notions.length }} notion(s)</span>
        </li>
        <li>
            <span class="fr-badge fr-badge--sm">{{ store.acronyms.length }} acronyme(s)</span>
        </li>
        <li>
            <span class="fr-badge fr-badge--sm">{{ store.questions.length }} question(s)</span>
        </li>
        <li>
            <span class="fr-badge fr-badge--sm">{{ store.exercises.length }} exercice(s)</span>
        </li>
    </ul>

    <DsfrTabs v-model="tab" :tabs="tabs" tabs-label="Étapes de génération du quiz">
        <!-- ─── Documents ──────────────────────────────────────────────────── -->
        <template #documents>
            <h2 class="fr-h4">Document(s) source</h2>
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

            <div class="fr-alert fr-alert--info fr-alert--sm fr-mt-2w">
                <p class="fr-mb-0">
                    Les documents sont analysés en <strong>mode Vision one-shot</strong> : les pages
                    sont envoyées telles quelles au modèle à grand contexte, ce qui préserve schémas,
                    tableaux et mise en page. Les documents trop volumineux pour le contexte sont
                    découpés automatiquement en blocs.
                </p>
            </div>

            <div v-if="selectedFiles.length" class="fr-mt-2w">
                <p class="fr-text--sm fr-mb-1v">
                    <strong>{{ selectedFiles.length }}</strong> fichier(s) sélectionné(s) :
                </p>
                <ul class="fr-tags-group">
                    <li v-for="f in selectedFiles" :key="f.name">
                        <span class="fr-tag fr-tag--sm">📄 {{ f.name }} · {{ formatSize(f.size) }}</span>
                    </li>
                </ul>
            </div>

            <button
                class="fr-btn fr-mt-2w"
                :disabled="!selectedFiles.length || store.busy === 'upload'"
                @click="upload"
            >
                {{ store.busy === 'upload' ? 'Analyse…' : 'Analyser les documents' }}
            </button>

            <div v-if="store.upload" class="fr-mt-2w">
                <div class="fr-alert fr-alert--success fr-alert--sm fr-mb-2w">
                    <p class="fr-mb-0">
                        ✅ Analyse terminée : <strong>{{ store.upload.documents.length }}</strong>
                        document(s), <strong>{{ store.upload.num_chunks }}</strong> blocs,
                        <strong>{{ store.upload.total_tokens.toLocaleString('fr-FR') }}</strong> tokens.
                        <template v-if="store.acronyms.length">
                            {{ store.acronyms.length }} acronyme(s) reconnu(s) au passage.
                        </template>
                    </p>
                </div>
                <div class="fr-table fr-table--sm fr-table--bordered">
                    <table>
                        <thead>
                            <tr>
                                <th scope="col">Document</th>
                                <th scope="col">Pages</th>
                                <th scope="col">Tokens</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="doc in store.upload.documents" :key="doc.name">
                                <td>{{ doc.name }}</td>
                                <td>{{ doc.num_pages || '—' }}</td>
                                <td>{{ doc.total_tokens.toLocaleString('fr-FR') }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <button class="fr-btn fr-btn--secondary fr-mt-2w" @click="tab = 'notions'">
                    Continuer vers les notions →
                </button>
            </div>
        </template>

        <!-- ─── Notions & acronymes ────────────────────────────────────────── -->
        <template #notions>
            <DsfrTabs
                v-model="notionsTab"
                :tabs="notionsTabs"
                tabs-label="Notions et acronymes"
                class="sub-tabs"
            >
                <template #liste>
                    <h2 class="fr-h4">Notions fondamentales</h2>
                    <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
                        <button
                            class="fr-btn"
                            :disabled="store.busy === 'notions'"
                            @click="store.detectNotions()"
                        >
                            {{ store.busy === 'notions' ? 'Détection…' : '🔍 Détecter les notions' }}
                        </button>
                        <button class="fr-btn fr-btn--secondary" @click="addNotionAndEdit">
                            ➕ Ajouter une notion
                        </button>
                    </div>
                    <p class="fr-text--sm fr-mt-1v fr-mb-0">
                        La détection repère aussi les sigles inconnus, dans la même passe (onglet
                        « Acronymes »).
                    </p>
                    <GenerationProgress kind="notions" />

                    <template v-if="store.notions.length">
                        <div class="fr-grid-row fr-grid-row--middle fr-mt-2w fr-mb-1v">
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
                                    :aria-pressed="notionsGrouped"
                                    @click="notionsGrouped = !notionsGrouped"
                                >
                                    🗂️ Par thématique
                                </button>
                            </div>
                        </div>

                        <section
                            v-for="[category, group] in displayGroups"
                            :key="category || '_flat'"
                            class="notion-group"
                        >
                            <h3 v-if="notionsGrouped" class="fr-h6 fr-mt-2w fr-mb-1v notion-group__title">
                                {{ category }}
                                <span class="fr-badge fr-badge--sm fr-ml-1v">{{ group.length }}</span>
                            </h3>

                            <div v-for="{ notion, index } in group" :key="index" class="notion-row fr-mb-1v">
                                <!-- Édition manuelle : brouillon local, validé au clic sur
                                     « Enregistrer ». Sans cela, changer la catégorie ferait
                                     sauter la notion d'un groupe à l'autre à chaque frappe. -->
                                <div v-if="editingIndex === index" class="notion-edit fr-p-2w">
                                    <div class="fr-input-group fr-mb-1v">
                                        <label class="fr-label fr-text--sm" :for="`notion-title-${index}`">
                                            Titre
                                        </label>
                                        <input
                                            :id="`notion-title-${index}`"
                                            class="fr-input"
                                            v-model="draft.title"
                                        />
                                    </div>
                                    <div class="fr-input-group fr-mb-1v">
                                        <label class="fr-label fr-text--sm" :for="`notion-cat-${index}`">
                                            Partie / thématique
                                            <span class="fr-hint-text">
                                                Regroupe les notions dans l'affichage « Par thématique ».
                                            </span>
                                        </label>
                                        <input
                                            :id="`notion-cat-${index}`"
                                            class="fr-input"
                                            list="notion-categories"
                                            v-model="draft.category"
                                        />
                                    </div>
                                    <div class="fr-input-group fr-mb-1v">
                                        <label class="fr-label fr-text--sm" :for="`notion-desc-${index}`">
                                            Description
                                        </label>
                                        <textarea
                                            :id="`notion-desc-${index}`"
                                            class="fr-input"
                                            rows="3"
                                            v-model="draft.description"
                                        />
                                    </div>
                                    <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
                                        <button class="fr-btn fr-btn--sm" @click="commitNotion">
                                            ✓ Enregistrer
                                        </button>
                                        <button
                                            class="fr-btn fr-btn--sm fr-btn--tertiary"
                                            @click="editingIndex = -1"
                                        >
                                            Annuler
                                        </button>
                                    </div>
                                </div>

                                <!-- Lecture -->
                                <div v-else class="fr-grid-row fr-grid-row--middle notion-card">
                                    <div class="fr-col">
                                        <div class="fr-checkbox-group fr-checkbox-group--sm">
                                            <input
                                                :id="`notion-${index}`"
                                                type="checkbox"
                                                v-model="notion.enabled"
                                            />
                                            <label class="fr-label" :for="`notion-${index}`">
                                                <span class="notion-title">
                                                    {{ notion.title || '(sans titre)' }}
                                                </span>
                                                <span class="fr-hint-text notion-meta">
                                                    <span
                                                        v-if="notion.category && !notionsGrouped"
                                                        class="fr-badge fr-badge--sm fr-badge--purple-glycine"
                                                    >
                                                        {{ notion.category }}
                                                    </span>
                                                    <span
                                                        v-if="store.notionQuestionCounts[notion.title]"
                                                        class="fr-badge fr-badge--sm fr-badge--green-emeraude"
                                                        title="Questions rattachées à cette notion"
                                                    >
                                                        {{ store.notionQuestionCounts[notion.title] }} Q
                                                    </span>
                                                    <span v-if="notion.source_pages?.length" class="notion-source">
                                                        p. {{ notion.source_pages.join(', ') }}
                                                    </span>
                                                </span>
                                                <span class="fr-hint-text notion-desc">
                                                    {{ notion.description }}
                                                </span>
                                            </label>
                                        </div>
                                    </div>
                                    <div class="fr-col-auto">
                                        <button
                                            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                                            :title="`Modifier « ${notion.title} »`"
                                            @click="startEdit(index)"
                                        >
                                            ✏️
                                        </button>
                                        <button
                                            class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                                            :title="`Supprimer « ${notion.title} »`"
                                            @click="store.deleteNotion(index)"
                                        >
                                            🗑️
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </section>

                        <datalist id="notion-categories">
                            <option v-for="c in store.notionCategories" :key="c" :value="c" />
                        </datalist>

                        <div class="fr-input-group fr-mt-2w">
                            <label class="fr-label fr-text--sm" for="notion-edit">
                                💬 Modifier les notions avec l'IA
                                <span class="fr-hint-text">
                                    Les parties/thématiques existantes sont conservées.
                                </span>
                            </label>
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
                    </template>
                    <p v-else-if="store.busy !== 'notions'" class="fr-text--sm fr-mt-2w">
                        Aucune notion pour l'instant — lancez la détection ci-dessus.
                    </p>
                </template>

                <template #acronymes>
                    <h2 class="fr-h4">Acronymes</h2>
                    <p class="fr-text--sm">
                        Les sigles du référentiel sont reconnus dès l'analyse des documents ; la
                        détection des notions y ajoute ceux qu'elle rencontre. Les sigles cochés sont
                        transmis au modèle pendant la génération et repris dans le glossaire des exports.
                    </p>
                    <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="store.busy === 'acronyms'"
                            @click="store.detectAcronyms()"
                        >
                            {{ store.busy === 'acronyms' ? 'Détection…' : '🔍 Relancer la détection' }}
                        </button>
                        <button class="fr-btn fr-btn--secondary" @click="store.addAcronym()">
                            ➕ Ajouter un acronyme
                        </button>
                    </div>

                    <template v-if="store.acronyms.length">
                        <p class="fr-text--sm fr-mt-2w fr-mb-1v">
                            {{ store.enabledAcronyms.length }} / {{ store.acronyms.length }} acronymes actifs
                        </p>
                        <div class="fr-table fr-table--sm fr-table--bordered acronym-table">
                            <table>
                                <thead>
                                    <tr>
                                        <th scope="col" class="acronym-col-check">Actif</th>
                                        <th scope="col" class="acronym-col-sigle">Sigle</th>
                                        <th scope="col">Définition</th>
                                        <th scope="col" class="acronym-col-actions">
                                            <span class="fr-sr-only">Actions</span>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr
                                        v-for="(a, i) in store.acronyms"
                                        :key="`${a.acronym}-${i}`"
                                        :class="{ 'acronym-row--off': !a.enabled }"
                                    >
                                        <td>
                                            <div class="fr-checkbox-group fr-checkbox-group--sm">
                                                <input :id="`acro-${i}`" type="checkbox" v-model="a.enabled" />
                                                <label class="fr-label" :for="`acro-${i}`">
                                                    <span class="fr-sr-only">
                                                        Utiliser {{ a.acronym }}
                                                    </span>
                                                </label>
                                            </div>
                                        </td>
                                        <td>
                                            <input
                                                class="fr-input fr-input--sm"
                                                v-model="a.acronym"
                                                :aria-label="`Sigle ${i + 1}`"
                                            />
                                            <span
                                                class="fr-badge fr-badge--sm fr-mt-1v"
                                                :class="a.from_reference ? 'fr-badge--blue-cumulus' : 'fr-badge--yellow-tournesol'"
                                            >
                                                {{ a.from_reference ? 'référentiel' : 'détecté' }}
                                            </span>
                                        </td>
                                        <td>
                                            <input
                                                class="fr-input fr-input--sm"
                                                v-model="a.definition"
                                                :aria-label="`Définition de ${a.acronym}`"
                                            />
                                            <p
                                                v-if="otherDefinitions(a).length"
                                                class="fr-text--xs fr-mb-0 fr-mt-1v acronym-suggestions"
                                            >
                                                Autres définitions connues :
                                                <button
                                                    v-for="(def, di) in otherDefinitions(a)"
                                                    :key="di"
                                                    type="button"
                                                    class="acronym-suggestion"
                                                    @click="a.definition = def"
                                                >
                                                    {{ def }}
                                                </button>
                                            </p>
                                        </td>
                                        <td>
                                            <button
                                                class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
                                                :title="`Supprimer ${a.acronym}`"
                                                @click="store.deleteAcronym(i)"
                                            >
                                                🗑️
                                            </button>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>

                        <div class="fr-input-group fr-mt-2w">
                            <label class="fr-label fr-text--sm" for="acro-edit">
                                💬 Modifier les acronymes avec l'IA
                            </label>
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
                    </template>
                    <p v-else class="fr-text--sm fr-mt-2w">
                        Aucun acronyme repéré dans ces documents.
                    </p>
                </template>
            </DsfrTabs>
        </template>

        <!-- ─── Quiz QCM ───────────────────────────────────────────────────── -->
        <template #quiz>
            <DsfrTabs v-model="quizTab" :tabs="quizTabs" tabs-label="Quiz QCM" class="sub-tabs">
                <template #config>
                    <h2 class="fr-h4">Configuration du quiz</h2>
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

                    <div class="fr-mt-2w">
                        <div class="fr-checkbox-group">
                            <input id="vraifaux" type="checkbox" v-model="config.vrai_faux" />
                            <label class="fr-label" for="vraifaux">
                                Mode Vrai / Faux
                                <span class="fr-hint-text">
                                    Affirmations à juger : force 2 choix et 1 bonne réponse.
                                </span>
                            </label>
                        </div>
                    </div>

                    <!-- Format des réponses. En Vrai/Faux le format est imposé, on masque
                         les réglages plutôt que de les afficher grisés. -->
                    <template v-if="!config.vrai_faux">
                        <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
                            <div class="fr-col-12 fr-col-md-4">
                                <label class="fr-label" for="num-choices">
                                    Nombre de choix (A, B, C…)
                                </label>
                                <input
                                    id="num-choices"
                                    class="fr-input"
                                    type="number"
                                    min="2"
                                    max="6"
                                    v-model.number="config.num_choices"
                                />
                            </div>
                            <div class="fr-col-12 fr-col-md-8">
                                <fieldset class="fr-fieldset fr-fieldset--inline fr-mb-0">
                                    <legend class="fr-fieldset__legend fr-text--regular">
                                        Nombre de bonnes réponses
                                    </legend>
                                    <div class="fr-fieldset__content">
                                        <div class="fr-radio-group">
                                            <input
                                                id="correct-fixed"
                                                type="radio"
                                                value="fixe"
                                                v-model="correctMode"
                                            />
                                            <label class="fr-label" for="correct-fixed">
                                                Fixe
                                                <span class="fr-hint-text">
                                                    Le même nombre pour toutes les questions.
                                                </span>
                                            </label>
                                        </div>
                                        <div class="fr-radio-group">
                                            <input
                                                id="correct-variable"
                                                type="radio"
                                                value="variable"
                                                v-model="correctMode"
                                            />
                                            <label class="fr-label" for="correct-variable">
                                                Variable (1 à N)
                                                <span class="fr-hint-text">
                                                    Le modèle choisit entre 1 et N par question.
                                                </span>
                                            </label>
                                        </div>
                                    </div>
                                </fieldset>
                            </div>
                        </div>

                        <div class="fr-grid-row fr-grid-row--gutters fr-mt-1w">
                            <div class="fr-col-12 fr-col-md-4">
                                <label class="fr-label" for="num-correct">
                                    {{
                                        correctMode === 'fixe'
                                            ? 'Nombre exact de bonnes réponses'
                                            : 'Maximum de bonnes réponses (N)'
                                    }}
                                    <span class="fr-hint-text">
                                        Au plus {{ config.num_choices - 1 }} (il faut au moins un
                                        mauvais choix).
                                    </span>
                                </label>
                                <input
                                    id="num-correct"
                                    class="fr-input"
                                    type="number"
                                    min="1"
                                    :max="maxCorrectAllowed"
                                    v-model.number="correctCount"
                                />
                            </div>
                        </div>
                    </template>
                    <p v-else class="fr-text--sm fr-mt-1w">
                        📝 Mode Vrai/Faux : 2 choix, 1 bonne réponse par question.
                    </p>

                    <div class="fr-mt-2w">
                        <div class="fr-checkbox-group">
                            <input id="humor" type="checkbox" v-model="config.humor" />
                            <label class="fr-label" for="humor">Touche d'humour</label>
                        </div>
                        <div class="fr-checkbox-group">
                            <input id="mixing" type="checkbox" v-model="config.notion_mixing" />
                            <label class="fr-label" for="mixing">
                                Mélange des notions
                                <span class="fr-hint-text">
                                    Activé : une question peut croiser plusieurs notions. Désactivé :
                                    une question porte sur une seule notion.
                                </span>
                            </label>
                        </div>
                        <div class="fr-checkbox-group">
                            <input id="batch" type="checkbox" v-model="config.batch_mode" />
                            <label class="fr-label" for="batch">
                                Traitement par lots (Batch API)
                                <span class="fr-hint-text">
                                    Plus rapide si le serveur supporte /v1/batches — pas d'affichage
                                    au fil de l'eau.
                                </span>
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

                    <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
                        <button
                            class="fr-btn"
                            :disabled="store.busy === 'quiz' || totalQuestions === 0"
                            @click="generate"
                        >
                            {{ store.busy === 'quiz' ? 'Génération en cours…' : `Générer ${totalQuestions} question(s)` }}
                        </button>
                        <button class="fr-btn fr-btn--secondary" @click="addQuestionAndShow">
                            ➕ Ajouter une question manuelle
                        </button>
                    </div>
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
                </template>

                <template #questions>
                    <h2 class="fr-h4">Quiz généré ({{ store.questions.length }} questions)</h2>

                    <div class="fr-btns-group fr-btns-group--inline fr-btns-group--sm fr-mb-2w">
                        <button
                            class="fr-btn fr-btn--secondary"
                            :disabled="store.busy === 'verify'"
                            @click="store.verifyQuiz()"
                        >
                            {{ store.busy === 'verify' ? 'Vérification…' : '🔍 Vérifier les réponses (IA)' }}
                        </button>
                        <button class="fr-btn fr-btn--tertiary" :disabled="!store.canUndo" @click="store.undo()">
                            ↩ Annuler la dernière modification
                        </button>
                        <button class="fr-btn fr-btn--tertiary" @click="store.addQuestion()">
                            ➕ Ajouter une question
                        </button>
                        <button class="fr-btn fr-btn--tertiary" @click="tab = 'exports'">
                            📦 Exporter / partager
                        </button>
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
                    <p v-if="!store.questions.length" class="fr-text--sm">
                        Aucune question pour l'instant — lancez une génération depuis l'onglet
                        « Configuration ».
                    </p>
                </template>
            </DsfrTabs>
        </template>

        <!-- ─── Exercices ──────────────────────────────────────────────────── -->
        <template #exercices>
            <DsfrTabs
                v-model="exerciseTab"
                :tabs="exerciseTabs"
                tabs-label="Exercices"
                class="sub-tabs"
            >
                <template #config>
                    <h2 class="fr-h4">Génération d'exercices</h2>
                    <div class="fr-grid-row fr-grid-row--gutters">
                        <div class="fr-col-12 fr-col-md-4">
                            <label class="fr-label" for="ex-type">Type</label>
                            <select id="ex-type" class="fr-select" v-model="exConfig.exercise_type">
                                <option v-for="t in exerciseTypes" :key="t.key" :value="t.key">
                                    {{ t.label }}
                                </option>
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
                        <input id="classify-ex" type="checkbox" v-model="classifyEx" />
                        <label class="fr-label" for="classify-ex">
                            Analyser la consigne (style vs périmètre)
                        </label>
                    </div>
                    <div class="fr-checkbox-group">
                        <input id="ex-mixing" type="checkbox" v-model="exConfig.notion_mixing" />
                        <label class="fr-label" for="ex-mixing">Mélange des notions</label>
                    </div>
                    <div class="fr-checkbox-group">
                        <input id="ex-batch" type="checkbox" v-model="exConfig.batch_mode" />
                        <label class="fr-label" for="ex-batch">Traitement par lots (Batch API)</label>
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

                    <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
                        <button
                            class="fr-btn"
                            :disabled="store.busy === 'exercises' || totalExercises === 0"
                            @click="generateExercises"
                        >
                            {{ store.busy === 'exercises' ? 'Génération…' : `Générer ${totalExercises} exercice(s)` }}
                        </button>
                        <button
                            class="fr-btn fr-btn--secondary"
                            @click="addExerciseAndShow"
                        >
                            ➕ Ajouter un exercice manuel
                        </button>
                    </div>
                    <GenerationProgress kind="exercises" />
                    <p v-if="exConfig.exercise_type === 'calcul'" class="fr-text--sm fr-mt-1v">
                        ⚠️ Les exercices de calcul sont auto-vérifiés par exécution Python côté serveur
                        (sandbox).
                    </p>
                    <p class="fr-text--sm fr-mt-1v">
                        Les exercices générés s'ajoutent aux précédents et se retrouvent dans l'onglet
                        de leur type.
                    </p>
                </template>

                <!-- Un onglet de résultats par type d'exercice (comme l'app Streamlit). -->
                <template #calcul>
                    <h2 class="fr-h4">🧮 Calcul numérique ({{ exercisesByType.calcul.length }})</h2>
                    <ExerciseCard
                        v-for="{ exercise, index } in exercisesByType.calcul"
                        :key="index"
                        :exercise="exercise"
                        :index="index"
                    />
                </template>
                <template #trou>
                    <h2 class="fr-h4">✏️ Texte à trou ({{ exercisesByType.trou.length }})</h2>
                    <ExerciseCard
                        v-for="{ exercise, index } in exercisesByType.trou"
                        :key="index"
                        :exercise="exercise"
                        :index="index"
                    />
                </template>
                <template #cas_pratique>
                    <h2 class="fr-h4">📋 Cas pratique ({{ exercisesByType.cas_pratique.length }})</h2>
                    <ExerciseCard
                        v-for="{ exercise, index } in exercisesByType.cas_pratique"
                        :key="index"
                        :exercise="exercise"
                        :index="index"
                    />
                </template>
            </DsfrTabs>
        </template>

        <!-- ─── Aperçu texte ───────────────────────────────────────────────── -->
        <template #apercu>
            <h2 class="fr-h4">Aperçu du texte extrait</h2>
            <p class="fr-text--sm">
                Ce que le modèle voit réellement de vos documents, bloc par bloc. Utile pour
                vérifier une extraction douteuse (PDF scanné, tableau, colonnes) avant de
                lancer une génération.
            </p>

            <template v-if="store.upload">
                <div
                    v-for="(chunk, ci) in store.upload.chunks_preview"
                    :key="ci"
                    class="fr-mb-2w chunk-preview"
                >
                    <p class="fr-text--sm fr-mb-1v">
                        <span class="fr-badge fr-badge--sm">Bloc {{ ci + 1 }}</span>
                        <span class="fr-ml-1v">{{ chunk.source_document }}</span>
                        <span v-if="chunk.source_pages.length" class="fr-hint-text fr-ml-1v">
                            page(s) {{ chunk.source_pages.join(', ') }}
                        </span>
                    </p>
                    <pre class="chunk-preview--text">{{ chunk.text_preview }}</pre>
                </div>
                <p v-if="!store.upload.chunks_preview.length" class="fr-text--sm">
                    Aucun aperçu renvoyé par le serveur pour ces documents (mode Vision : les pages
                    sont transmises en images).
                </p>
            </template>
        </template>

        <!-- ─── Exports & partage ──────────────────────────────────────────── -->
        <template #exports>
            <h2 class="fr-h4">Exporter</h2>
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
                    class="fr-btn fr-btn--tertiary"
                    @click="store.exportFile('scenari', store.exercises.length ? 'combined' : 'quiz')"
                    title="Archive ZIP d'items .quiz importables dans SCENARI"
                >
                    SCENARI .quiz (ZIP)
                </button>
                <button
                    v-if="store.exercises.length"
                    class="fr-btn fr-btn--tertiary"
                    @click="store.exportFile('html', 'combined')"
                >
                    Quiz + Exercices HTML
                </button>
            </div>

            <h2 class="fr-h4 fr-mt-4w">Partager en session</h2>
            <div class="fr-p-3w session-box">
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

            <h2 class="fr-h4 fr-mt-4w">Repartir de zéro</h2>
            <p class="fr-text--sm">
                Le travail en cours (documents, notions, questions, exercices) est conservé dans ce
                navigateur et restauré au rechargement de la page.
            </p>
            <button class="fr-btn fr-btn--secondary" @click="resetAll">
                🗑️ Effacer le travail en cours
            </button>
        </template>
    </DsfrTabs>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { Acronym, Exercise, ExerciseType, Notion } from '@/services/api';
import { useGenerationStore } from '@/stores/generationStore';
import QuestionCard from '@/components/QuestionCard.vue';
import ExerciseCard from '@/components/ExerciseCard.vue';
import GenerationProgress from '@/components/GenerationProgress.vue';
import DsfrTabs from '@/components/DsfrTabs.vue';
import type { TabDefinition } from '@/components/dsfrTabs';
import { loadState, saveState } from '@/services/persist';

defineOptions({ name: 'GeneratePage' });

const store = useGenerationStore();

const levels = [
    { key: 'facile', label: '🟢 Facile' },
    { key: 'moyen', label: '🟡 Moyen' },
    { key: 'difficile', label: '🔴 Difficile' },
] as const;

const exerciseTypes = [
    { key: 'calcul', label: '🧮 Calcul numérique' },
    { key: 'trou', label: '✏️ Texte à trou' },
    { key: 'cas_pratique', label: '📋 Cas pratique' },
] as const satisfies readonly { key: ExerciseType; label: string }[];

// ── Onglets ──────────────────────────────────────────────────────────────────
// Reprend le découpage de l'interface Streamlit historique. Les onglets qui
// supposent un document analysé restent désactivés tant que l'upload n'a pas eu
// lieu ; celui des exports attend qu'il y ait quelque chose à exporter.
const tab = ref('documents');
const notionsTab = ref('liste');
const quizTab = ref('config');
const exerciseTab = ref('config');

const tabs = computed<TabDefinition[]>(() => {
    const needsDocument = "Analysez d'abord un document dans l'onglet « Documents ».";
    const uploaded = Boolean(store.upload);
    return [
        {
            key: 'documents',
            label: '📄 Documents',
            badge: store.upload?.documents.length,
        },
        {
            key: 'notions',
            label: '📚 Notions',
            disabled: !uploaded,
            disabledHint: needsDocument,
            badge: store.notions.length || undefined,
        },
        {
            key: 'quiz',
            label: '🎯 Quiz QCM',
            disabled: !uploaded,
            disabledHint: needsDocument,
            badge: store.questions.length || undefined,
        },
        {
            key: 'exercices',
            label: '🧮 Exercices',
            disabled: !uploaded,
            disabledHint: needsDocument,
            badge: store.exercises.length || undefined,
        },
        {
            key: 'apercu',
            label: '👁️ Aperçu texte',
            disabled: !uploaded,
            disabledHint: needsDocument,
        },
        {
            key: 'exports',
            label: '📦 Exports & partage',
            disabled: !store.questions.length && !store.exercises.length,
            disabledHint: 'Générez au moins une question ou un exercice.',
        },
    ];
});

const notionsTabs = computed<TabDefinition[]>(() => [
    { key: 'liste', label: '📚 Notions', badge: store.notions.length || undefined },
    { key: 'acronymes', label: '🔤 Acronymes', badge: store.acronyms.length || undefined },
]);

const quizTabs = computed<TabDefinition[]>(() => [
    { key: 'config', label: '⚙️ Configuration' },
    {
        key: 'questions',
        label: '🎯 Questions générées',
        badge: store.questions.length || undefined,
        disabled: !store.questions.length,
        disabledHint: 'Générez au moins une question.',
    },
]);

const exerciseTabs = computed<TabDefinition[]>(() => [
    { key: 'config', label: '⚙️ Configuration' },
    ...exerciseTypes.map((t) => ({
        key: t.key,
        label: t.label,
        badge: exercisesByType.value[t.key].length || undefined,
        disabled: !exercisesByType.value[t.key].length,
        disabledHint: `Aucun exercice de type « ${t.label} » pour l'instant.`,
    })),
]);

/** Exercices regroupés par type, avec leur index d'origine (édition/suppression). */
const exercisesByType = computed(() => {
    const groups = {
        calcul: [] as { exercise: Exercise; index: number }[],
        trou: [] as { exercise: Exercise; index: number }[],
        cas_pratique: [] as { exercise: Exercise; index: number }[],
    };
    store.exercises.forEach((exercise, index) => {
        (groups[exercise.exercise_type] ?? groups.calcul).push({ exercise, index });
    });
    return groups;
});

// Un onglet peut devenir inaccessible (remise à zéro, suppression du dernier
// contenu exportable) : on revient alors sur le premier onglet du groupe.
function normalizeTabs() {
    if (tabs.value.find((t) => t.key === tab.value)?.disabled) tab.value = 'documents';
    if (quizTabs.value.find((t) => t.key === quizTab.value)?.disabled) quizTab.value = 'config';
    if (exerciseTabs.value.find((t) => t.key === exerciseTab.value)?.disabled)
        exerciseTab.value = 'config';
}

watch([tabs, quizTabs, exerciseTabs], normalizeTabs);

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
        ...answerFormat(),
        batch_mode: config.batch_mode,
    });
}

const selectedFiles = ref<File[]>([]);
const notionInstruction = ref('');
const acronymInstruction = ref('');
const notionsGrouped = ref(false);
const counts = reactive<Record<string, number>>({ facile: 0, moyen: 5, difficile: 0 });

/** Format des bonnes réponses : « fixe » (nombre exact) ou « variable » (1 à N). */
const correctMode = ref<'fixe' | 'variable'>('fixe');
/**
 * Valeur unique pilotée par le mode : nombre exact en Fixe, plafond N en Variable.
 * Deux champs distincts embrouillaient la lecture (l'ancienne case à cocher grisait
 * un champ qui restait affiché) — un seul champ, dont le libellé change, suffit.
 */
const correctCount = ref(1);

const config = reactive({
    num_choices: 4,
    vrai_faux: false,
    humor: false,
    batch_mode: false,
    persona: '',
    user_instructions: '',
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
    notion_mixing: true,
});

/** Un choix au moins doit être faux, sinon la question n'a plus de distracteur. */
const maxCorrectAllowed = computed(() => Math.max(1, config.num_choices - 1));

// Réduire le nombre de choix ne doit pas laisser une valeur devenue impossible.
watch(maxCorrectAllowed, (max) => {
    if (correctCount.value > max) correctCount.value = max;
});

/**
 * Traduit le mode choisi en paramètres attendus par le backend :
 * - Vrai/Faux → 2 choix, 1 bonne réponse, format fixe ;
 * - Fixe → `num_correct` exact (`max_correct` inutile) ;
 * - Variable → le modèle choisit entre 1 et `max_correct`.
 */
function answerFormat() {
    if (config.vrai_faux) {
        return {
            num_choices: 2,
            num_correct: 1,
            variable_correct: false,
            max_correct: null,
            vrai_faux: true,
        };
    }
    const variable = correctMode.value === 'variable';
    return {
        num_choices: config.num_choices,
        num_correct: variable ? 1 : Math.min(correctCount.value, maxCorrectAllowed.value),
        variable_correct: variable,
        max_correct: variable ? Math.min(correctCount.value, maxCorrectAllowed.value) : null,
        vrai_faux: false,
    };
}

const totalQuestions = computed(() =>
    Object.values(counts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

const totalExercises = computed(() =>
    Object.values(exCounts).reduce((sum, n) => sum + (Number(n) || 0), 0),
);

// Notions affichées : groupées par thématique, ou liste plate sous une clé vide.
const displayGroups = computed<[string, { notion: Notion; index: number }[]][]>(() =>
    notionsGrouped.value
        ? store.notionsByCategory
        : [['', store.notions.map((notion, index) => ({ notion, index }))]],
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

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function upload() {
    store.uploadDocuments(selectedFiles.value);
}

// ── Notions : édition sur brouillon ──────────────────────────────────────────
const editingIndex = ref(-1);
const draft = reactive<Pick<Notion, 'title' | 'category' | 'description'>>({
    title: '',
    category: '',
    description: '',
});

function startEdit(index: number) {
    const notion = store.notions[index];
    if (!notion) return;
    draft.title = notion.title;
    draft.category = notion.category;
    draft.description = notion.description;
    editingIndex.value = index;
}

function commitNotion() {
    const notion = store.notions[editingIndex.value];
    if (notion) {
        store.updateNotion(editingIndex.value, {
            ...notion,
            title: draft.title.trim(),
            category: draft.category.trim(),
            description: draft.description.trim(),
        });
    }
    editingIndex.value = -1;
}

function addNotionAndEdit() {
    store.addNotion();
    startEdit(store.notions.length - 1);
}

/** Définitions du référentiel autres que celle retenue (proposées en un clic). */
function otherDefinitions(acronym: Acronym): string[] {
    return (acronym.all_definitions ?? []).filter((d) => d && d !== acronym.definition);
}

function editAcronyms() {
    store.editAcronyms(acronymInstruction.value);
    acronymInstruction.value = '';
}

function generate() {
    sessionCode.value = '';
    quizTab.value = 'questions'; // suivre la génération au fil de l'eau
    store.generateQuiz({
        difficulty_counts: { ...counts },
        ...answerFormat(),
        humor: config.humor,
        batch_mode: config.batch_mode,
        persona: config.persona,
        user_instructions: config.user_instructions,
        notion_mixing: config.notion_mixing,
        classify_instructions: classifyQuiz.value,
        difficulty_prompts: { ...quizPrompts },
    });
}

function addQuestionAndShow() {
    store.addQuestion();
    quizTab.value = 'questions';
}

function generateExercises() {
    exerciseTab.value = exConfig.exercise_type; // suivre la génération au fil de l'eau
    store.generateExercises({
        difficulty_counts: { ...exCounts },
        ...exConfig,
        classify_instructions: classifyEx.value,
        custom_exercise_prompts: { ...(exPrompts[exConfig.exercise_type] ?? {}) },
    });
}

function addExerciseAndShow() {
    store.addExercise(exConfig.exercise_type);
    exerciseTab.value = exConfig.exercise_type;
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

function resetAll() {
    store.reset();
    selectedFiles.value = [];
    tab.value = 'documents';
    sessionCode.value = '';
    workshopCode.value = '';
}

// ── Persistance du formulaire (les données vivent dans le store) ─────────────
const FORM_KEY = 'quizz.generate.form.v1';

interface PersistedForm {
    tab: string;
    notionsTab: string;
    quizTab: string;
    exerciseTab: string;
    notionsGrouped: boolean;
    counts: Record<string, number>;
    config: typeof config;
    correctMode: 'fixe' | 'variable';
    correctCount: number;
    exCounts: Record<string, number>;
    exConfig: typeof exConfig;
    classifyQuiz: boolean;
    classifyEx: boolean;
    sessionTitle: string;
    poolMode: boolean;
    subsetSize: number;
    passThreshold: number;
}

function snapshotForm(): PersistedForm {
    return {
        tab: tab.value,
        notionsTab: notionsTab.value,
        quizTab: quizTab.value,
        exerciseTab: exerciseTab.value,
        notionsGrouped: notionsGrouped.value,
        counts: { ...counts },
        config: { ...config },
        correctMode: correctMode.value,
        correctCount: correctCount.value,
        exCounts: { ...exCounts },
        exConfig: { ...exConfig },
        classifyQuiz: classifyQuiz.value,
        classifyEx: classifyEx.value,
        sessionTitle: sessionTitle.value,
        poolMode: poolMode.value,
        subsetSize: subsetSize.value,
        passThreshold: passThreshold.value,
    };
}

function restoreForm() {
    const saved = loadState<PersistedForm>(FORM_KEY);
    if (!saved) return;
    tab.value = saved.tab ?? 'documents';
    notionsTab.value = saved.notionsTab ?? 'liste';
    quizTab.value = saved.quizTab ?? 'config';
    exerciseTab.value = saved.exerciseTab ?? 'config';
    notionsGrouped.value = saved.notionsGrouped ?? false;
    Object.assign(counts, saved.counts ?? {});
    Object.assign(config, saved.config ?? {});
    correctMode.value = saved.correctMode ?? 'fixe';
    correctCount.value = saved.correctCount ?? 1;
    Object.assign(exCounts, saved.exCounts ?? {});
    Object.assign(exConfig, saved.exConfig ?? {});
    classifyQuiz.value = saved.classifyQuiz ?? false;
    classifyEx.value = saved.classifyEx ?? false;
    sessionTitle.value = saved.sessionTitle ?? '';
    poolMode.value = saved.poolMode ?? false;
    subsetSize.value = saved.subsetSize ?? 5;
    passThreshold.value = saved.passThreshold ?? 70;
}

onMounted(async () => {
    restoreForm();
    // L'état de travail (documents, notions, quiz) est restauré par le store, qui
    // se rebranche au passage sur une génération encore en cours côté serveur.
    store.restore();
    // Un onglet restauré peut ne plus être atteignable (contenu effacé entre-temps).
    normalizeTabs();
    await store.loadPromptDefaults();
    applyQuizDefaults();
    applyExerciseDefaults();
    // Sauvegarde du formulaire une fois la restauration terminée (sinon on
    // écraserait l'état sauvegardé avec les valeurs par défaut).
    watch(snapshotForm, (form) => saveState(FORM_KEY, form));
});
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

/* Onglets imbriqués : ils ne doivent pas se confondre avec les onglets d'étape. */
.sub-tabs {
    box-shadow: none;
}

/* ── Notions ───────────────────────────────────────────────────────────── */
.notion-group__title {
    border-left: 4px solid var(--border-action-high-blue-france);
    padding-left: 0.5rem;
}
.notion-card {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.25rem;
    padding: 0.5rem 0.75rem;
}
.notion-title {
    font-weight: 700;
}
.notion-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    align-items: center;
    margin-top: 0.25rem;
}
.notion-desc {
    margin-top: 0.25rem;
}
.notion-source {
    font-style: italic;
}
.notion-edit {
    border: 1px dashed var(--border-action-high-blue-france);
    border-radius: 0.25rem;
    background: var(--background-alt-grey);
}

/* ── Acronymes ─────────────────────────────────────────────────────────── */
.acronym-table {
    overflow-x: auto;
}
.acronym-col-check {
    width: 4rem;
}
.acronym-col-sigle {
    width: 12rem;
}
.acronym-col-actions {
    width: 3.5rem;
}
.acronym-row--off {
    opacity: 0.55;
}
.acronym-suggestions {
    color: var(--text-mention-grey);
}
.acronym-suggestion {
    background: none;
    border: none;
    padding: 0 0.25rem;
    color: var(--text-action-high-blue-france);
    text-decoration: underline;
    cursor: pointer;
    font-size: inherit;
}

/* ── Aperçu texte ──────────────────────────────────────────────────────── */
.chunk-preview {
    border: 1px solid var(--border-default-grey);
    border-radius: 0.5rem;
    padding: 1rem;
}
.chunk-preview--text {
    margin: 0;
    max-height: 18rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 0.875rem;
    background: var(--background-alt-grey);
    padding: 0.75rem;
    border-radius: 0.25rem;
}
</style>
