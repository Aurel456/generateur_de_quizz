"""Utilitaires de formatage des numéros de pages."""
from typing import Iterable, List


def format_page_ranges(
    pages: Iterable[int],
    separator: str = ", ",
    range_dash: str = "-",
) -> str:
    """Compresse une liste de pages en plages contiguës.

    Exemples :
        [5, 6, 7, 9, 10] -> "5-7, 9-10"
        [5, 6, 7, 8, 9, 10] -> "5-10"
        [5] -> "5"
        [] -> ""

    Le tri et la déduplication sont appliqués automatiquement.
    """
    cleaned: List[int] = sorted({int(p) for p in pages if p is not None})
    if not cleaned:
        return ""
    ranges: List[str] = []
    start = prev = cleaned[0]
    for p in cleaned[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(str(start) if start == prev else f"{start}{range_dash}{prev}")
        start = prev = p
    ranges.append(str(start) if start == prev else f"{start}{range_dash}{prev}")
    return separator.join(ranges)
