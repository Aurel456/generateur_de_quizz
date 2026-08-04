export interface ChangelogSection {
    title: string;
    items: string[];
}

/**
 * Découpe le CHANGELOG.md en sections affichables sur la page d'accueil.
 *
 * Format attendu : un titre de niveau 1 par mise à jour, puis une puce par changement.
 * Les commentaires HTML sont ignorés, ainsi que tout contenu placé avant le premier titre.
 */
export function parseChangelogMarkdown(markdown = ''): { sections: ChangelogSection[] } {
    const sections: ChangelogSection[] = [];
    const withoutComments = markdown.replace(/<!--[\s\S]*?-->/g, '');

    let currentSection: ChangelogSection | null = null;

    for (const rawLine of withoutComments.split('\n')) {
        const line = rawLine.trim();

        if (!line) {
            continue;
        }

        if (line.startsWith('# ')) {
            currentSection = { title: line.slice(2).trim(), items: [] };
            sections.push(currentSection);
            continue;
        }

        // Contenu hors section (préambule) : ignoré.
        if (!currentSection) {
            continue;
        }

        if (line.startsWith('- ') || line.startsWith('* ')) {
            currentSection.items.push(line.slice(2).trim());
            continue;
        }

        currentSection.items.push(line);
    }

    return { sections };
}
