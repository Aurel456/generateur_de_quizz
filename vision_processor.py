"""
vision_processor.py — Extraction d'images de PDF et optimisation DPI pour le modèle vision.
Utilise PyMuPDF (fitz) pour le rendu des pages en images.
"""

import math
import io
import base64
from typing import List, Tuple, Optional, BinaryIO

import fitz  # PyMuPDF
from PIL import Image

# --- Constantes ---
PATCH_FACTOR = 32
DEFAULT_MODEL_SEQ_LEN = 80000


def encode_image(img: Image.Image) -> str:
    """Convertit une image PIL en chaîne base64 JPEG."""
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def calculate_page_tokens(width_pt: float, height_pt: float, dpi: int) -> int:
    """Calcule le nombre de tokens pour une page selon le DPI (modèle Qwen-VL patch-based)."""
    width_px = (width_pt / 72.0) * dpi
    height_px = (height_pt / 72.0) * dpi
    patches_w = math.ceil(width_px / PATCH_FACTOR)
    patches_h = math.ceil(height_px / PATCH_FACTOR)
    return patches_w * patches_h


def get_pdf_native_resolution(doc: fitz.Document, default_dpi: int = 300) -> int:
    """Analyse le PDF pour trouver la résolution maximale des images intégrées."""
    try:
        max_detected_dpi = 0
        for i in range(min(len(doc), 3)):
            page = doc[i]
            image_list = page.get_images(full=True)
            for img_info in image_list:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_width = base_image.get("width", 0)
                    page_width_pt = page.rect.width
                    if page_width_pt > 0 and img_width > 0:
                        dpi_w = (img_width / page_width_pt) * 72
                        max_detected_dpi = max(max_detected_dpi, dpi_w)
                except Exception:
                    continue
        return int(round(max_detected_dpi)) if max_detected_dpi > 0 else default_dpi
    except Exception:
        return default_dpi


def optimize_pdf_params(
    page_sizes_pt: List[Tuple[float, float]],
    token_budget: int,
    min_dpi: int,
    max_dpi: int,
) -> Tuple[int, int]:
    """Détermine le meilleur DPI et le nombre de pages à traiter selon le budget tokens."""

    # 1. Test au DPI maximum
    total_tokens_max = sum(calculate_page_tokens(w, h, max_dpi) for w, h in page_sizes_pt)
    if total_tokens_max <= token_budget:
        return max_dpi, len(page_sizes_pt)

    # 2. Test au DPI minimum
    total_tokens_min = sum(calculate_page_tokens(w, h, min_dpi) for w, h in page_sizes_pt)
    if total_tokens_min <= token_budget:
        # Recherche binaire de la meilleure qualité entre min et max
        low, high = min_dpi, max_dpi - 1
        best_dpi = min_dpi
        while low <= high:
            mid = (low + high) // 2
            current_tokens = sum(calculate_page_tokens(w, h, mid) for w, h in page_sizes_pt)
            if current_tokens <= token_budget:
                best_dpi = mid
                low = mid + 1
            else:
                high = mid - 1
        return best_dpi, len(page_sizes_pt)

    # 3. Tronquage des pages au DPI minimum
    current_tokens = 0
    pages_to_keep = 0
    for w, h in page_sizes_pt:
        t = calculate_page_tokens(w, h, min_dpi)
        if current_tokens + t <= token_budget:
            current_tokens += t
            pages_to_keep += 1
        else:
            break
    return min_dpi, pages_to_keep


def smart_prepare_media(
    file_input: BinaryIO,
    text_token_buffer: int = 2000,
    min_dpi: int = 72,
    max_dpi: int = 300,
    model_seq_len: int = DEFAULT_MODEL_SEQ_LEN,
) -> Tuple[List[Image.Image], int, int, int]:
    """
    Traite un PDF en optimisant le DPI pour respecter le budget de tokens.

    Args:
        file_input: Fichier PDF (BinaryIO).
        text_token_buffer: Tokens réservés pour le texte du prompt.
        min_dpi: DPI minimum.
        max_dpi: DPI maximum.
        model_seq_len: Fenêtre de contexte du modèle vision.

    Returns:
        (images: List[PIL.Image], target_dpi, num_pages_processed, native_dpi)
    """
    try:
        file_input.seek(0)
        file_bytes = file_input.read()
        file_input.seek(0)
    except Exception:
        return [], 0, 0, 0

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        # Pas un PDF — essayer comme image
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
            # Convertir l'image en PDF en mémoire pour traitement unifié
            pdf_bytes = io.BytesIO()
            img.save(pdf_bytes, format="PDF")
            pdf_bytes.seek(0)
            doc = fitz.open(stream=pdf_bytes.getvalue(), filetype="pdf")
        except Exception:
            return [], 0, 0, 0

    try:
        native_dpi = get_pdf_native_resolution(doc, default_dpi=max_dpi)
        effective_max_dpi = min(max_dpi, native_dpi)

        page_sizes_pt = []
        for page in doc:
            rect = page.rect
            page_sizes_pt.append((float(rect.width), float(rect.height)))

        tokens_budget = max(model_seq_len - text_token_buffer, 0)
        target_dpi, num_pages = optimize_pdf_params(
            page_sizes_pt, tokens_budget, min_dpi, effective_max_dpi
        )

        if num_pages == 0:
            doc.close()
            return [], target_dpi, 0, native_dpi

        # Rendu des pages avec PyMuPDF
        zoom = target_dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pil_images = []
        for i in range(num_pages):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pil_images.append(img)

        doc.close()
        return pil_images, target_dpi, num_pages, native_dpi

    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        print(f"Erreur vision_processor: {e}")
        return [], 0, 0, 0


def extract_pages_as_base64(
    file_input: BinaryIO,
    text_token_buffer: int = 2000,
    min_dpi: int = 72,
    max_dpi: int = 300,
    model_seq_len: int = DEFAULT_MODEL_SEQ_LEN,
) -> List[dict]:
    """
    Extrait les pages d'un PDF sous forme d'images base64 optimisées.

    Returns:
        Liste de dicts : [{"page": int, "base64": str, "tokens": int}, ...]
    """
    images, target_dpi, num_pages, native_dpi = smart_prepare_media(
        file_input,
        text_token_buffer=text_token_buffer,
        min_dpi=min_dpi,
        max_dpi=max_dpi,
        model_seq_len=model_seq_len,
    )

    if not images:
        return []

    # Relire les dimensions pour le calcul de tokens
    try:
        file_input.seek(0)
        file_bytes = file_input.read()
        file_input.seek(0)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_sizes_pt = [(float(doc[i].rect.width), float(doc[i].rect.height)) for i in range(num_pages)]
        doc.close()
    except Exception:
        page_sizes_pt = [(595.0, 842.0)] * num_pages  # A4 fallback

    result = []
    for i, img in enumerate(images):
        b64 = encode_image(img)
        w_pt, h_pt = page_sizes_pt[i] if i < len(page_sizes_pt) else (595.0, 842.0)
        tokens = calculate_page_tokens(w_pt, h_pt, target_dpi)
        result.append({
            "page": i + 1,
            "base64": b64,
            "tokens": tokens,
        })

    return result
