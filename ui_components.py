"""
ui_components.py — Composants UI réutilisables pour l'application Streamlit.

Regroupe les fonctions d'affichage partagées entre les différents onglets
(stat cards, source attribution, etc.) pour éviter la duplication de code.
"""

import streamlit as st
from typing import List, Optional


def render_stat_card(value, label: str):
    """
    Affiche une carte statistique stylisée avec une valeur et un label.
    
    Args:
        value: Valeur à afficher (nombre, chaîne formatée, etc.)
        label: Label descriptif sous la valeur
    """
    st.markdown(f"""
    <div class="stat-card">
        <div class="stat-value">{value}</div>
        <div class="stat-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def render_source_info(source_document: Optional[str], source_pages: Optional[List[int]]) -> str:
    """
    Construit et affiche les informations de source (document + pages).
    
    Args:
        source_document: Nom du document source.
        source_pages: Liste des numéros de pages.
    
    Returns:
        Texte formaté de la source, ou chaîne vide si aucune info.
    """
    source_parts = []
    if source_document:
        source_parts.append(f"📄 {source_document}")
    if source_pages:
        source_parts.append(f"p. {', '.join(map(str, source_pages))}")
    if source_parts:
        st.caption(f"Source : {', '.join(source_parts)}")
    return ", ".join(source_parts)


def render_difficulty_badge(diff_label: str):
    """
    Affiche un badge coloré pour le niveau de difficulté.
    
    Args:
        diff_label: Niveau de difficulté ('facile', 'moyen', 'difficile')
    """
    diff_colors = {"facile": "#00c853", "moyen": "#ffab00", "difficile": "#ff1744"}
    diff_emojis = {"facile": "🟢", "moyen": "🟡", "difficile": "🔴"}
    diff_color = diff_colors.get(diff_label, "#a0a0b8")
    diff_emoji = diff_emojis.get(diff_label, "⬜")
    
    st.markdown(
        f'<span style="background: {diff_color}20; color: {diff_color}; '
        f'padding: 0.2rem 0.7rem; border-radius: 12px; font-size: 0.8rem; '
        f'font-weight: 600; border: 1px solid {diff_color}40;">'
        f'{diff_emoji} {diff_label.capitalize()}</span>',
        unsafe_allow_html=True
    )
