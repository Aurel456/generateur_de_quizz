/** Description d'un onglet pour `DsfrTabs.vue`. */
export interface TabDefinition {
    key: string;
    label: string;
    /** Onglet non atteignable (étape précédente non faite). */
    disabled?: boolean;
    /** Infobulle expliquant pourquoi l'onglet est désactivé. */
    disabledHint?: string;
    /** Compteur affiché en pastille (nombre de notions, de questions…). */
    badge?: string | number;
}
