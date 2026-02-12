"""
pdf_processor.py — Extraction de texte depuis un PDF et chunking intelligent.
"""

import re
from dataclasses import dataclass, field
from typing import List, Literal

import pdfplumber
import tiktoken


@dataclass
class TextChunk:
    """Un morceau de texte extrait du PDF avec ses métadonnées."""
    text: str
    source_pages: List[int] = field(default_factory=list)
    token_count: int = 0


# Encodeur tiktoken — cl100k_base est compatible avec la plupart des modèles OpenAI
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Compte le nombre de tokens dans un texte."""
    return len(_encoder.encode(text))


def extract_text_from_pdf(pdf_file) -> List[dict]:
    """
    Extrait le texte page par page depuis un fichier PDF.
    
    Args:
        pdf_file: Chemin du fichier ou objet file-like (UploadedFile de Streamlit).
    
    Returns:
        Liste de dicts {"page": int, "text": str}
    """
    pages = []
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Nettoyage basique
            text = re.sub(r'\s+', ' ', text).strip()  # espaces multiples
            text = re.sub(r'(\n\s*){3,}', '\n\n', text)  # sauts de ligne excessifs
            if text:
                pages.append({"page": i + 1, "text": text})
    return pages


def split_into_paragraphs(pages: List[dict]) -> List[TextChunk]:
    """
    Sépare le texte en paragraphes (basé sur les doubles sauts de ligne
    ou les limites de page).
    """
    paragraphs = []
    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"]
        # Split sur double saut de ligne ou points de rupture naturels
        parts = re.split(r'\n\n+', text)
        for part in parts:
            part = part.strip()
            if part and len(part) > 20:  # Ignorer les fragments trop courts
                paragraphs.append(TextChunk(
                    text=part,
                    source_pages=[page_num],
                    token_count=count_tokens(part)
                ))
    return paragraphs


def chunk_text(
    pages: List[dict],
    max_tokens: int = 2000,
    overlap_tokens: int = 200
) -> List[TextChunk]:
    """
    Découpe le texte complet en chunks de taille max_tokens avec overlap.
    
    Args:
        pages: Liste de dicts {"page": int, "text": str}
        max_tokens: Taille maximale d'un chunk en tokens.
        overlap_tokens: Nombre de tokens de chevauchement entre chunks.
    
    Returns:
        Liste de TextChunk.
    """
    # Concaténer tout le texte avec des marqueurs de page
    full_text = ""
    page_boundaries = []  # (char_start, page_num)
    for page_data in pages:
        start = len(full_text)
        full_text += page_data["text"] + "\n\n"
        page_boundaries.append((start, page_data["page"]))

    tokens = _encoder.encode(full_text)
    total_tokens = len(tokens)
    
    if total_tokens == 0:
        return []

    chunks = []
    start = 0
    
    while start < total_tokens:
        end = min(start + max_tokens, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text_str = _encoder.decode(chunk_tokens)
        
        # Déterminer les pages sources
        chunk_char_start = len(_encoder.decode(tokens[:start]))
        chunk_char_end = chunk_char_start + len(chunk_text_str)
        source_pages = []
        for boundary_start, page_num in page_boundaries:
            # La page contribue au chunk si elle chevauche la plage de caractères
            if boundary_start < chunk_char_end:
                if page_num not in source_pages:
                    source_pages.append(page_num)
        
        chunks.append(TextChunk(
            text=chunk_text_str.strip(),
            source_pages=source_pages,
            token_count=len(chunk_tokens)
        ))
        
        # Avancer avec overlap
        if end >= total_tokens:
            break
        start = end - overlap_tokens

    return chunks


def split_into_pages(pages: List[dict]) -> List[TextChunk]:
    """
    Sépare le texte par page (1 chunk = 1 page).
    """
    chunks = []
    for page_data in pages:
        text = page_data["text"].strip()
        if text:
            chunks.append(TextChunk(
                text=text,
                source_pages=[page_data["page"]],
                token_count=count_tokens(text)
            ))
    return chunks


def extract_and_chunk(
    pdf_file,
    mode: Literal["page", "token"] = "page",
    max_tokens: int = 10000,
    overlap_tokens: int = 200
) -> List[TextChunk]:
    """
    Pipeline complet : extraction + chunking selon le mode choisi.
    
    Args:
        pdf_file: Fichier PDF (path ou file-like).
        mode: "page" (1 chunk = 1 page), 
              "token" (découpage par taille fixe de tokens).
        max_tokens: Taille max d'un chunk en tokens (pour le mode "token").
        overlap_tokens: Overlap entre chunks (pour le mode "token").
    
    Returns:
        Liste de TextChunk.
    """
    pages = extract_text_from_pdf(pdf_file)
    
    if not pages:
        return []

    if mode == "page":
        return split_into_pages(pages)
    
    elif mode == "token":
        return chunk_text(pages, max_tokens, overlap_tokens)
    
    else:
        raise ValueError(f"Mode inconnu : {mode}")


def _normalize_chunks(chunks: List[TextChunk], max_tokens: int) -> List[TextChunk]:
    """
    Fusionne les chunks trop petits (<100 tokens) avec le suivant,
    et découpe les chunks trop grands.
    """
    normalized = []
    buffer_text = ""
    buffer_pages = []
    
    for chunk in chunks:
        if chunk.token_count > max_tokens:
            # D'abord flush le buffer
            if buffer_text:
                normalized.append(TextChunk(
                    text=buffer_text.strip(),
                    source_pages=list(set(buffer_pages)),
                    token_count=count_tokens(buffer_text)
                ))
                buffer_text = ""
                buffer_pages = []
            
            # Découper le chunk trop grand
            words = chunk.text.split()
            current = ""
            for word in words:
                test = current + " " + word if current else word
                if count_tokens(test) > max_tokens:
                    if current:
                        normalized.append(TextChunk(
                            text=current.strip(),
                            source_pages=chunk.source_pages.copy(),
                            token_count=count_tokens(current)
                        ))
                    current = word
                else:
                    current = test
            if current:
                normalized.append(TextChunk(
                    text=current.strip(),
                    source_pages=chunk.source_pages.copy(),
                    token_count=count_tokens(current)
                ))
        
        elif chunk.token_count < 100:
            # Trop petit — accumuler dans le buffer
            buffer_text += " " + chunk.text
            buffer_pages.extend(chunk.source_pages)
            
            if count_tokens(buffer_text) >= 100:
                normalized.append(TextChunk(
                    text=buffer_text.strip(),
                    source_pages=list(set(buffer_pages)),
                    token_count=count_tokens(buffer_text)
                ))
                buffer_text = ""
                buffer_pages = []
        else:
            # Flush buffer d'abord
            if buffer_text:
                buffer_text += " " + chunk.text
                buffer_pages.extend(chunk.source_pages)
                normalized.append(TextChunk(
                    text=buffer_text.strip(),
                    source_pages=list(set(buffer_pages)),
                    token_count=count_tokens(buffer_text)
                ))
                buffer_text = ""
                buffer_pages = []
            else:
                normalized.append(chunk)
    
    # Flush le buffer final
    if buffer_text:
        normalized.append(TextChunk(
            text=buffer_text.strip(),
            source_pages=list(set(buffer_pages)),
            token_count=count_tokens(buffer_text)
        ))
    
    return normalized


def get_full_text(pages: List[dict]) -> str:
    """Retourne le texte complet concaténé."""
    return "\n\n".join(p["text"] for p in pages)


def get_text_stats(pdf_file) -> dict:
    """Retourne des statistiques sur le PDF."""
    pages = extract_text_from_pdf(pdf_file)
    full_text = get_full_text(pages)
    total_tokens = count_tokens(full_text)
    return {
        "num_pages": len(pages),
        "total_chars": len(full_text),
        "total_tokens": total_tokens,
        "avg_tokens_per_page": total_tokens // max(len(pages), 1)
    }
