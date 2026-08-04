/**
 * Persistance locale de l'état de travail (sans dépendance externe).
 *
 * La génération d'un quiz s'étale sur plusieurs minutes et plusieurs étapes : un
 * rechargement de page (F5, restauration d'onglet, coupure réseau) ne doit pas faire
 * perdre les documents analysés, les notions ni les questions déjà produites.
 *
 * Le stockage est `localStorage` : volontairement par navigateur et par poste, jamais
 * envoyé au serveur. Toutes les écritures sont tolérantes aux pannes (mode privé,
 * quota dépassé) — une persistance impossible ne doit jamais casser l'application.
 */

/** Version du format : incrémenter invalide les états sauvegardés incompatibles. */
const VERSION = 1;

interface Envelope<T> {
    v: number;
    savedAt: number;
    data: T;
}

function storage(): Storage | null {
    try {
        return window.localStorage;
    } catch {
        return null; // cookies/stockage bloqués
    }
}

/** Relit un état sauvegardé. Renvoie `null` si absent, illisible ou périmé. */
export function loadState<T>(key: string, maxAgeMs = 7 * 24 * 3600 * 1000): T | null {
    const store = storage();
    if (!store) return null;
    try {
        const raw = store.getItem(key);
        if (!raw) return null;
        const envelope = JSON.parse(raw) as Envelope<T>;
        if (envelope.v !== VERSION) return null;
        if (maxAgeMs > 0 && Date.now() - envelope.savedAt > maxAgeMs) {
            store.removeItem(key);
            return null;
        }
        return envelope.data;
    } catch {
        return null;
    }
}

/** Écrit un état. Le dépassement de quota purge la clé plutôt que de lever. */
export function saveState<T>(key: string, data: T): void {
    const store = storage();
    if (!store) return;
    try {
        store.setItem(key, JSON.stringify({ v: VERSION, savedAt: Date.now(), data }));
    } catch {
        // Quota dépassé (quiz volumineux) : on abandonne la sauvegarde de cette clé
        // pour ne pas laisser une version tronquée qui serait relue plus tard.
        try {
            store.removeItem(key);
        } catch {
            /* rien de plus à faire */
        }
    }
}

export function clearState(key: string): void {
    const store = storage();
    try {
        store?.removeItem(key);
    } catch {
        /* ignoré */
    }
}
