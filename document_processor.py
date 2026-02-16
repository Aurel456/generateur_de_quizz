"""
document_processor.py — Extraction de texte depuis divers formats (PDF, DOCX, ODT, PPTX) et chunking intelligent.
"""

import re
import io
from dataclasses import dataclass, field
from typing import List, Literal, BinaryIO, Any

import pdfplumber
import tiktoken
from docx import Document as DocxDocument
from pptx import Presentation
from odf.opendocument import load as load_odf
from odf import text, teletype, draw


@dataclass
class TextChunk:
    """Un morceau de texte extrait du document avec ses métadonnées."""
    text: str
    source_pages: List[int] = field(default_factory=list)
    token_count: int = 0


# Encodeur tiktoken — cl100k_base est compatible avec la plupart des modèles OpenAI
_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Compte le nombre de tokens dans un texte."""
    return len(_encoder.encode(text))


def _extract_from_pdf(file: BinaryIO) -> List[dict]:
    """Extrait le texte d'un PDF page par page."""
    pages = []
    try:
        with pdfplumber.open(file) as pdf:
            for i, page in enumerate(pdf.pages):
                text_content = page.extract_text() or ""
                # Nettoyage basique
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                text_content = re.sub(r'(\n\s*){3,}', '\n\n', text_content)
                if text_content:
                    pages.append({"page": i + 1, "text": text_content})
    except Exception as e:
        print(f"Erreur lors de l'extraction PDF : {e}")
    return pages


def _extract_from_docx(file: BinaryIO) -> List[dict]:
    """Extrait le texte d'un fichier DOCX en gérant les sauts de page."""
    pages = []
    try:
        doc = DocxDocument(file)
        
        current_page_text = []
        page_num = 1
        
        # namespaces pour XPath
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

        def flush_page():
            nonlocal current_page_text, page_num
            text_content = "\n\n".join(current_page_text).strip()
            if text_content:
                pages.append({"page": page_num, "text": text_content})
                page_num += 1
            current_page_text = []

        for para in doc.paragraphs:
            # Vérifier si le paragraphe a un saut de page avant (propriété de style)
            if para._element.xpath('.//w:pPr/w:pageBreakBefore', namespaces=ns):
                flush_page()

            para_parts = []
            
            for run in para.runs:
                # Vérifier les sauts de page à l'intérieur des runs
                # w:br type="page" (saut manuel) ou w:lastRenderedPageBreak (saut automatique Word)
                breaks = run._element.xpath('.//w:br[@w:type="page"] | .//w:lastRenderedPageBreak', namespaces=ns)
                
                if breaks:
                    # S'il y a un break, on finit ce qui précédait dans le run
                    # Note: on ne peut pas facilement splitter le texte au milieu d'un run 
                    # mais en général les breaks sont entre les textes ou dans des runs dédiés
                    
                    # On flush le texte accumulé jusque là dans le paragraphe
                    if run.text:
                        para_parts.append(run.text)
                    
                    if para_parts:
                        current_page_text.append(" ".join(para_parts))
                        para_parts = []
                    
                    flush_page()
                else:
                    if run.text:
                        para_parts.append(run.text)
            
            if para_parts:
                current_page_text.append(" ".join(para_parts))

        # Ne pas oublier la dernière page
        flush_page()

        # Fallback si rien n'a été extrait (ex: document vide ou formatage étrange)
        if not pages and doc.paragraphs:
            full_text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            if full_text:
                pages.append({"page": 1, "text": "\n\n".join(full_text)})

    except Exception as e:
        print(f"Erreur lors de l'extraction DOCX : {e}")
    return pages


def _extract_from_pptx(file: BinaryIO) -> List[dict]:
    """Extrait le texte d'un fichier PPTX (slide par slide)."""
    pages = []
    try:
        prs = Presentation(file)
        for i, slide in enumerate(prs.slides):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())
            text_content = "\n".join(slide_text)
            if text_content:
                pages.append({"page": i + 1, "text": text_content})
    except Exception as e:
        print(f"Erreur lors de l'extraction PPTX : {e}")
    return pages


def _extract_from_odf(file: BinaryIO) -> List[dict]:
    """Extrait le texte d'un fichier ODT ou ODP en gérant les sauts de page."""
    pages = []
    try:
        doc = load_odf(file)
        
        # 1. Essayer de détecter des slides (ODP)
        slides = doc.getElementsByType(draw.Page)
        
        if slides:
            # Cas ODP : on traite chaque slide comme une page
            for i, slide in enumerate(slides):
                slide_content = teletype.extractText(slide).strip()
                slide_content = re.sub(r'\s+', ' ', slide_content).strip()
                if slide_content:
                    pages.append({"page": i + 1, "text": slide_content})
        else:
            # Cas ODT : on traverse pour trouver les sauts de page
            pages_content = []      # Liste de listes de lignes
            current_page_lines = []
            
            # Obtenir les qnames pour la comparaison
            QNAME_P = text.P().qname
            QNAME_H = text.H().qname
            QNAME_BREAK = text.SoftPageBreak().qname
            
            def finish_page():
                if current_page_lines:
                    pages_content.append(current_page_lines[:])
                    current_page_lines.clear()
            
            def traverse(node):
                # Récupérer le qname et type du noeud
                qname = getattr(node, 'qname', None)
                
                # S'il y a un saut de page explicite (hors paragraphe ou détecté ainsi)
                if qname == QNAME_BREAK:
                    finish_page()
                    return

                # Si c'est un paragraphe (P) ou un titre (H)
                if qname in (QNAME_P, QNAME_H):
                    child_text_buffer = []
                    
                    # On parcourt les enfants pour voir s'il y a un saut de page à l'intérieur
                    for child in node.childNodes:
                        if getattr(child, 'qname', None) == QNAME_BREAK:
                            # Saut détecté au milieu du paragraphe
                            # On flush ce qui précède
                            text_before = "".join(child_text_buffer).strip()
                            if text_before:
                                current_page_lines.append(text_before)
                            child_text_buffer = []
                            
                            finish_page()
                        else:
                            # Texte normal (span, link, text node...)
                            # teletype.extractText gère la récursion pour le texte
                            child_txt = teletype.extractText(child)
                            if child_txt:
                                child_text_buffer.append(child_txt)
                    
                    # Fin du paragraphe : on ajoute le reste
                    full_text = "".join(child_text_buffer).strip()
                    if full_text:
                        current_page_lines.append(full_text)
                    return

                # Pour les autres containers (body, section, table...), on récurse
                for child in node.childNodes:
                    traverse(child)

            # Traversée depuis la racine du doc
            traverse(doc)
            finish_page()
            
            # Construction du résultat final
            for i, p_lines in enumerate(pages_content):
                page_text = "\n\n".join(p_lines)
                if page_text.strip():
                    pages.append({"page": i + 1, "text": page_text})
            
            # Fallback : si aucun contenu structuré trouvé, essayer globalement
            if not pages:
                all_text = []
                for element in doc.getElementsByType(text.P) + doc.getElementsByType(text.H):
                    content = teletype.extractText(element).strip()
                    if content:
                        all_text.append(content)
                if all_text:
                    pages.append({"page": 1, "text": "\n\n".join(all_text)})

    except Exception as e:
        print(f"Erreur lors de l'extraction ODF : {e}")
    return pages


def _extract_from_txt(file: BinaryIO) -> List[dict]:
    """Extrait le texte d'un fichier texte simple."""
    try:
        content = file.read().decode("utf-8", errors="replace").strip()
        return [{"page": 1, "text": content}] if content else []
    except Exception as e:
        print(f"Erreur lors de l'extraction TXT : {e}")
        return []


def extract_text_from_file(file: BinaryIO) -> List[dict]:
    """
    Extrait le texte depuis un fichier selon son extension.
    Détecte automatiquement le type via file.name.
    """
    if not hasattr(file, "name"):
        # Fallback si pas de nom, essayons PDF par défaut ou erreur
        return _extract_from_pdf(file)

    filename = file.name.lower()
    
    # Reset le pointeur du fichier au début au cas où
    file.seek(0)
    
    if filename.endswith(".pdf"):
        return _extract_from_pdf(file)
    elif filename.endswith(".docx"):
        return _extract_from_docx(file)
    elif filename.endswith(".pptx"):
        return _extract_from_pptx(file)
    elif filename.endswith((".odt", ".odp", ".ods")):
        return _extract_from_odf(file)
    elif filename.endswith(".txt"):
        return _extract_from_txt(file)
    else:
        # Tenter PDF par défaut si extension inconnue mais accepté
        return _extract_from_pdf(file)


def split_into_paragraphs(pages: List[dict]) -> List[TextChunk]:
    """
    Sépare le texte en paragraphes.
    """
    paragraphs = []
    for page_data in pages:
        page_num = page_data["page"]
        text_content = page_data["text"]
        parts = re.split(r'\n\n+', text_content)
        for part in parts:
            part = part.strip()
            if part and len(part) > 20:
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
    """
    full_text = ""
    page_spans = []
    
    for page_data in pages:
        header = f"\n\n[Début Page {page_data['page']}]\n"
        footer = f"\n[Fin Page {page_data['page']}]"
        
        page_content = header + page_data["text"] + footer
        
        start_idx = len(full_text)
        full_text += page_content
        end_idx = len(full_text)
        
        page_spans.append((start_idx, end_idx, page_data["page"]))

    tokens = _encoder.encode(full_text)
    total_tokens = len(tokens)
    
    if total_tokens == 0:
        return []

    chunks = []
    start_token = 0
    
    while start_token < total_tokens:
        end_token = min(start_token + max_tokens, total_tokens)
        chunk_tokens_list = tokens[start_token:end_token]
        chunk_text_str = _encoder.decode(chunk_tokens_list)
        
        prefix_text = _encoder.decode(tokens[:start_token])
        chunk_char_start = len(prefix_text)
        chunk_char_end = chunk_char_start + len(chunk_text_str)
        
        source_pages = []
        for p_start, p_end, p_num in page_spans:
            if max(chunk_char_start, p_start) < min(chunk_char_end, p_end):
                if p_num not in source_pages:
                    source_pages.append(p_num)
        
        chunks.append(TextChunk(
            text=chunk_text_str.strip(),
            source_pages=source_pages,
            token_count=len(chunk_tokens_list)
        ))
        
        if end_token >= total_tokens:
            break
        start_token = end_token - overlap_tokens

    return chunks


def split_into_pages(pages: List[dict]) -> List[TextChunk]:
    """
    Sépare le texte par page (ou section logique selon format).
    """
    chunks = []
    for page_data in pages:
        text_content = page_data["text"].strip()
        if text_content:
            chunks.append(TextChunk(
                text=text_content,
                source_pages=[page_data["page"]],
                token_count=count_tokens(text_content)
            ))
    return chunks


def extract_and_chunk(
    file: BinaryIO,
    mode: Literal["page", "token"] = "page",
    max_tokens: int = 10000,
    overlap_tokens: int = 200
) -> List[TextChunk]:
    """
    Pipeline complet : extraction + chunking selon le mode choisi.
    """
    pages = extract_text_from_file(file)
    
    if not pages:
        return []

    if mode == "page":
        return split_into_pages(pages)
    
    elif mode == "token":
        return chunk_text(pages, max_tokens, overlap_tokens)
    
    else:
        raise ValueError(f"Mode inconnu : {mode}")


def get_full_text(pages: List[dict]) -> str:
    """Retourne le texte complet concaténé."""
    return "\n\n".join(p["text"] for p in pages)


def get_text_stats(file: BinaryIO) -> dict:
    """Retourne des statistiques sur le document."""
    pages = extract_text_from_file(file)
    full_text = get_full_text(pages)
    total_tokens = count_tokens(full_text)
    return {
        "num_pages": len(pages),
        "total_chars": len(full_text),
        "total_tokens": total_tokens,
        "avg_tokens_per_page": total_tokens // max(len(pages), 1)
    }
