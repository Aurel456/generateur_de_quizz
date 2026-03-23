"""
vision_processor.py — Extraction d'images de documents et optimisation DPI pour le modèle vision.
Utilise PyMuPDF (fitz) pour le rendu des pages en images.
Supporte PDF nativement, DOCX/PPTX/ODT/ODP via conversion LibreOffice ou MS Office.
"""

import math
import io
import os
import base64
import subprocess
import tempfile
import platform
import logging
from pathlib import Path
from typing import List, Tuple, Optional, BinaryIO

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# --- Constantes ---
PATCH_FACTOR = 32
DEFAULT_MODEL_SEQ_LEN = 80000

# Extensions supportées pour la conversion vers PDF
OFFICE_EXTENSIONS = {".docx", ".doc", ".pptx", ".ppt", ".odt", ".odp"}


# --- Conversion Office → PDF ---------------------------------------------------

def _find_libreoffice() -> Optional[str]:
    """Trouve l'exécutable LibreOffice sur le système."""
    if platform.system() == "Windows":
        for prog_dir in [os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                         os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")]:
            candidate = Path(prog_dir) / "LibreOffice" / "program" / "soffice.exe"
            if candidate.exists():
                return str(candidate)
    else:
        for cmd in ("libreoffice", "soffice"):
            try:
                subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
                return cmd
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
    return None


def _convert_with_libreoffice(input_path: Path, output_dir: str) -> Optional[Path]:
    """Convertit un document en PDF via LibreOffice headless."""
    soffice = _find_libreoffice()
    if not soffice:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf",
             "--outdir", output_dir, str(input_path)],
            capture_output=True, timeout=120,
        )
        pdf_path = Path(output_dir) / (input_path.stem + ".pdf")
        return pdf_path if pdf_path.exists() else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _convert_with_msoffice(input_path: Path, output_path: Path, suffix: str) -> bool:
    """Convertit via MS Office COM (Windows uniquement, via PowerShell)."""
    if platform.system() != "Windows":
        return False

    abs_in = str(input_path.resolve())
    abs_out = str(output_path.resolve())

    if suffix in (".docx", ".doc", ".odt"):
        # wdFormatPDF = 17
        ps_script = (
            f'$w = New-Object -ComObject Word.Application; '
            f'$w.Visible = $false; '
            f'try {{ '
            f'$d = $w.Documents.Open("{abs_in}"); '
            f'$d.SaveAs([ref]"{abs_out}", [ref]17); '
            f'$d.Close() '
            f'}} finally {{ $w.Quit() }}'
        )
    elif suffix in (".pptx", ".ppt", ".odp"):
        # ppSaveAsPDF = 32, msoTrue = -1, msoFalse = 0
        ps_script = (
            f'$p = New-Object -ComObject PowerPoint.Application; '
            f'try {{ '
            f'$pres = $p.Presentations.Open("{abs_in}", -1, 0, 0); '
            f'$pres.SaveAs("{abs_out}", 32); '
            f'$pres.Close() '
            f'}} finally {{ $p.Quit() }}'
        )
    else:
        return False

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, timeout=120,
        )
        logger.info(f"COM conversion stdout: {result.stdout[:200] if result.stdout else ''}")
        if result.stderr:
            logger.warning(f"COM conversion stderr: {result.stderr[:500]}")
        return output_path.exists()
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"COM conversion error: {e}")
        return False


def convert_office_to_pdf(file_bytes: bytes, filename: str) -> Optional[bytes]:
    """
    Convertit un document Office (DOCX, PPTX, ODT, ODP) en PDF.
    Essaie LibreOffice d'abord, puis MS Office COM sur Windows.

    Returns:
        Bytes du PDF, ou None si la conversion échoue.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in OFFICE_EXTENSIONS:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / f"input{suffix}"
        input_path.write_bytes(file_bytes)

        # 1. Essayer LibreOffice
        pdf_path = _convert_with_libreoffice(input_path, tmpdir)
        if pdf_path and pdf_path.exists():
            logger.info(f"Conversion LibreOffice réussie : {filename}")
            return pdf_path.read_bytes()

        # 2. Fallback MS Office COM (Windows)
        pdf_out = Path(tmpdir) / "input.pdf"
        if _convert_with_msoffice(input_path, pdf_out, suffix):
            logger.info(f"Conversion MS Office réussie : {filename}")
            return pdf_out.read_bytes()

    logger.warning(f"Conversion impossible pour {filename} — ni LibreOffice ni MS Office disponible.")
    return None


def extract_images_from_odf(file_bytes: bytes) -> List[Image.Image]:
    """
    Extrait les images embarquées d'un fichier ODF (ODT/ODP) en lisant le ZIP.
    Cherche dans tout le ZIP, pas uniquement dans Pictures/.

    Returns:
        Liste d'images PIL triées par nom de fichier.
    """
    import zipfile

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg"}
    images = []
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            # Chercher toutes les images dans le ZIP (Pictures/, media/, thumbnails, etc.)
            img_names = sorted(
                n for n in zf.namelist()
                if not n.endswith("/")
                and any(n.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
                and "thumbnail" not in n.lower()  # Ignorer les miniatures
            )
            for name in img_names:
                try:
                    data = zf.read(name)
                    img = Image.open(io.BytesIO(data))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    images.append(img)
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Erreur extraction images ODF : {e}")
    return images


def _extract_text_from_odf_xml(file_bytes: bytes, filename: str) -> List[str]:
    """
    Parse le content.xml d'un fichier ODF (ZIP) avec ElementTree.
    N'utilise PAS odfpy ni defusedxml (évite le bug pyexpat/DLL).

    Pour ODT : retourne une liste avec un seul élément (tout le texte).
    Pour ODP : retourne une liste de textes, un par slide.
    """
    import zipfile
    from lxml.etree import fromstring

    # Namespaces ODF
    NS = {
        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
        "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
        "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
        "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    }

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            content_xml = zf.read("content.xml")
    except Exception as e:
        logger.warning(f"Impossible de lire content.xml dans {filename}: {e}")
        return []

    try:
        root = fromstring(content_xml)
    except Exception as e:
        logger.warning(f"Impossible de parser content.xml: {e}")
        return []

    suffix = Path(filename).suffix.lower()

    def _iter_text(element) -> str:
        """Récupère tout le texte d'un élément et ses enfants."""
        parts = []
        if element.text:
            parts.append(element.text)
        for child in element:
            parts.append(_iter_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    if suffix == ".odp":
        # Présentation : chercher les draw:page dans office:presentation
        pages = root.findall(".//draw:page", NS)
        if not pages:
            # Fallback: chercher tout élément avec le tag contenant 'page'
            pages = [e for e in root.iter() if "page" in e.tag.lower() and "master" not in e.tag.lower()]
        result = []
        for page in pages:
            texts = []
            # Extraire le texte de tous les text:p et text:h dans la page
            for elem in page.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag in ("p", "h", "span", "list-item"):
                    t = _iter_text(elem).strip()
                    if t:
                        texts.append(t)
            # Dédupliquer (les <p> imbriqués dans <span> etc.)
            seen = set()
            unique = []
            for t in texts:
                if t not in seen:
                    seen.add(t)
                    unique.append(t)
            result.append("\n".join(unique) if unique else " ")
        return result
    else:
        # ODT : extraire tous les paragraphes et titres du body
        body = root.find(".//office:body/office:text", NS)
        if body is None:
            body = root  # fallback
        paragraphs = []
        for elem in body.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ("p", "h"):
                t = _iter_text(elem).strip()
                if t:
                    paragraphs.append(t)
        if paragraphs:
            return ["\n\n".join(paragraphs)]
        return []


def render_odf_to_pdf(file_bytes: bytes, filename: str) -> Optional[bytes]:
    """
    Convertit un fichier ODF (ODT/ODP) en PDF via ElementTree (texte) + fitz (rendu PDF).
    Fallback pur Python quand ni LibreOffice ni MS Office ne sont disponibles.
    N'utilise PAS odfpy — parse directement le content.xml du ZIP.

    Le PDF généré contient le texte avec wrapping automatique via fitz.insert_textbox().
    Pour ODP : une page paysage par slide.
    Pour ODT : pages A4 avec le texte intégral, multi-pages automatique.

    Returns:
        Bytes du PDF, ou None si la conversion échoue.
    """
    suffix = Path(filename).suffix.lower()

    pages_text = _extract_text_from_odf_xml(file_bytes, filename)

    if not pages_text:
        return None

    # Créer le PDF avec fitz
    pdf_doc = fitz.open()

    if suffix == ".odp":
        page_w, page_h = 960, 540  # 16:9 paysage en points
        fontsize = 14
    else:
        page_w, page_h = 595, 842  # A4 portrait
        fontsize = 11

    margin = 40

    for page_text in pages_text:
        remaining = page_text
        while remaining:
            page = pdf_doc.new_page(width=page_w, height=page_h)
            rect = fitz.Rect(margin, margin, page_w - margin, page_h - margin)
            # insert_textbox retourne le surplus de texte qui ne rentre pas
            rc = page.insert_textbox(
                rect, remaining,
                fontsize=fontsize,
                fontname="helv",
                align=0,  # left-align
            )
            if rc >= 0:
                # Tout le texte a été inséré
                break
            # rc < 0 : overflow — estimer combien de texte rentre par page
            # On prend environ 80% du texte et on passe au suivant
            chars_per_page = max(int(len(remaining) * 0.7), 100)
            # Trouver une coupure propre (fin de ligne ou de mot)
            cut = remaining.rfind("\n", 0, chars_per_page)
            if cut < 100:
                cut = remaining.rfind(" ", 0, chars_per_page)
            if cut < 50:
                cut = chars_per_page
            remaining = remaining[cut:].lstrip()

    try:
        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()
        logger.info(f"Rendu ODF→PDF réussi pour {filename} ({len(pages_text)} section(s))")
        return pdf_bytes
    except Exception as e:
        logger.warning(f"Erreur lors de la génération du PDF : {e}")
        pdf_doc.close()
        return None


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
    min_dpi: int = 65,
    max_dpi: int = 80,
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
        page_sizes_pt = []
        for page in doc:
            rect = page.rect
            page_sizes_pt.append((float(rect.width), float(rect.height)))

        tokens_budget = max(model_seq_len - text_token_buffer, 0)
        target_dpi, num_pages = optimize_pdf_params(
            page_sizes_pt, tokens_budget, min_dpi, max_dpi
        )

        if num_pages == 0:
            doc.close()
            return [], target_dpi, 0, 0

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
        return pil_images, target_dpi, num_pages, 0

    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        print(f"Erreur vision_processor: {e}")
        return [], 0, 0, 0


def analyze_pdf_dpi(
    file_input: BinaryIO,
    text_token_buffer: int = 2000,
    min_dpi: int = 65,
    max_dpi: int = 80,
    model_seq_len: int = DEFAULT_MODEL_SEQ_LEN,
) -> dict:
    """
    Analyse un PDF et retourne les informations DPI sans rendre toutes les pages.

    Returns:
        {
            "auto_dpi": int,          # DPI sélectionné par l'algorithme
            "native_dpi": int,        # DPI natif détecté dans le PDF
            "num_pages": int,         # Nombre total de pages
            "pages_processed": int,   # Pages traitées dans le budget
            "total_tokens": int,      # Tokens estimés au DPI auto
            "page_sizes_pt": list,    # [(w, h), ...] en points
        }
    """
    try:
        file_input.seek(0)
        file_bytes = file_input.read()
        file_input.seek(0)
    except Exception:
        return {}

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        return {}

    try:
        page_sizes_pt = []
        for page in doc:
            page_sizes_pt.append((float(page.rect.width), float(page.rect.height)))

        tokens_budget = max(model_seq_len - text_token_buffer, 0)
        auto_dpi, pages_processed = optimize_pdf_params(
            page_sizes_pt, tokens_budget, min_dpi, max_dpi
        )

        total_tokens = sum(
            calculate_page_tokens(w, h, auto_dpi)
            for w, h in page_sizes_pt[:pages_processed]
        )

        doc.close()
        return {
            "auto_dpi": auto_dpi,
            "num_pages": len(page_sizes_pt),
            "pages_processed": pages_processed,
            "total_tokens": total_tokens,
            "page_sizes_pt": page_sizes_pt,
        }
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        return {}


def render_page_preview(
    file_input: BinaryIO,
    page_num: int = 0,
    dpi: int = 150,
) -> Optional[Image.Image]:
    """Rend une seule page d'un PDF en image PIL au DPI spécifié."""
    try:
        file_input.seek(0)
        file_bytes = file_input.read()
        file_input.seek(0)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if page_num >= len(doc):
            doc.close()
            return None
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = doc[page_num].get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return img
    except Exception:
        return None


def estimate_tokens_for_dpi(
    page_sizes_pt: List[Tuple[float, float]],
    dpi: int,
) -> int:
    """Calcule le total de tokens pour toutes les pages à un DPI donné."""
    return sum(calculate_page_tokens(w, h, dpi) for w, h in page_sizes_pt)


def extract_pages_as_base64(
    file_input: BinaryIO,
    text_token_buffer: int = 2000,
    min_dpi: int = 65,
    max_dpi: int = 80,
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
