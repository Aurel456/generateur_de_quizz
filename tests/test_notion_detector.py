"""Tests des notions : conservation des catégories lors des retouches LLM.

Le LLM omet régulièrement la catégorie thématique dans ses réponses. Sans report
depuis la notion d'origine, une simple édition faisait basculer toutes les notions
dans « Sans catégorie » et cassait le regroupement par partie/sous-partie.
"""
from unittest.mock import patch

from generation.notion_detector import (
    Notion,
    edit_notions_with_llm,
    merge_similar_notions,
)


def _notions():
    return [
        Notion(
            title="Laïcité",
            description="Principe de neutralité de l'État.",
            source_document="cours.pdf",
            source_pages=[3],
            category="Fondements",
            question_count=4,
        ),
        Notion(
            title="Devoir de réserve",
            description="Obligation de retenue de l'agent public.",
            source_document="cours.pdf",
            source_pages=[7],
            category="Obligations",
        ),
    ]


def test_edit_notions_returns_notions_and_explanation():
    """Le contrat est un tuple : l'appelant qui l'ignorait produisait une erreur 500."""
    response = {
        "notions": [{"title": "Laïcité", "description": "Neutralité de l'État."}],
        "explanation": "Description raccourcie.",
    }
    with patch("generation.notion_detector.call_llm_json", return_value=response):
        notions, explanation = edit_notions_with_llm(_notions(), "raccourcis la description")

    assert explanation == "Description raccourcie."
    assert [n.title for n in notions] == ["Laïcité"]


def test_edit_notions_keeps_category_when_llm_omits_it():
    response = {
        "notions": [
            {"title": "Laïcité", "description": "Neutralité de l'État."},
            {"title": "Devoir de réserve", "description": "Retenue.", "category": "Obligations"},
        ],
        "explanation": "",
    }
    with patch("generation.notion_detector.call_llm_json", return_value=response):
        notions, _ = edit_notions_with_llm(_notions(), "reformule")

    assert notions[0].category == "Fondements"  # reprise de la notion d'origine
    assert notions[1].category == "Obligations"  # renvoyée par le LLM
    # Les métadonnées de l'origine survivent aussi (comptage, source).
    assert notions[0].question_count == 4
    assert notions[0].source_pages == [3]


def test_edit_notions_keeps_category_despite_title_variation():
    """Le report se fait par rapprochement de titres (accents, casse, ponctuation)."""
    response = {"notions": [{"title": "La laïcité", "description": "Neutralité."}]}
    with patch("generation.notion_detector.call_llm_json", return_value=response):
        notions, _ = edit_notions_with_llm(_notions(), "renomme")

    assert notions[0].category == "Fondements"


def test_new_notion_has_no_inherited_category():
    response = {
        "notions": [
            {"title": "Laïcité", "description": "Neutralité."},
            {"title": "Secret professionnel", "description": "Nouveau.", "category": "Obligations"},
        ]
    }
    with patch("generation.notion_detector.call_llm_json", return_value=response):
        notions, _ = edit_notions_with_llm(_notions(), "ajoute le secret professionnel")

    added = next(n for n in notions if n.title == "Secret professionnel")
    assert added.category == "Obligations"


def test_merge_similar_notions_keeps_category():
    response = {
        "merged_notions": [
            {"title": "Laïcité", "description": "Fusion des deux descriptions."},
        ],
        "merge_summary": "2 → 1",
    }
    with patch("generation.notion_detector.call_llm_json", return_value=response):
        merged, summary = merge_similar_notions(_notions())

    assert summary == "2 → 1"
    assert merged[0].category == "Fondements"


def test_merge_returns_input_when_nothing_to_merge():
    notions = _notions()[:1]
    merged, summary = merge_similar_notions(notions)
    assert merged == notions
    assert "Aucune fusion" in summary
