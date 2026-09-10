"""OCR and text extraction pipeline.

Supports:
1. Native PDF character stream extraction via pdfplumber / pypdf.
2. Rasterization (via PyMuPDF / fitz at 200-300 DPI) + OCR for scanned documents
   or vector-curve PDF documents (such as financial statements rendered as vector paths).
3. Direct image OCR for JPEG / PNG files.
4. Flexible OCR engine support:
   - Tesseract OCR (via pytesseract, honoring TESSERACT_CMD / PATH).
   - In-process fallback OCR (e.g. rapidocr_onnxruntime if installed) for zero-system-dependency environments.
5. Normalized PageTextResult and DocumentTextResult per-page data structures.
"""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path
from typing import Optional, Union

import fitz  # PyMuPDF
from PIL import Image
import pdfplumber
import pytesseract

from app.core.config import Settings, get_settings
from app.core.exceptions import OCRError
from app.core.logging import get_logger
from app.schemas.ocr import DocumentTextResult, PageTextResult

logger = get_logger(__name__)

# Minimum character count on a page to consider native text extraction successful
NATIVE_TEXT_CHAR_THRESHOLD = 30


def get_tesseract_cmd(settings: Optional[Settings] = None) -> Optional[str]:
    """Resolve tesseract executable from settings, environment, or common Windows paths."""
    cfg = settings or get_settings()

    # 1. Config / env variable
    if cfg.tesseract_cmd and os.path.isfile(cfg.tesseract_cmd):
        return cfg.tesseract_cmd

    # 2. System PATH
    found = shutil.which("tesseract")
    if found:
        return found

    # 3. Known Windows locations
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def run_ocr_on_image(
    image: Image.Image,
    *,
    language: str = "eng",
    tesseract_cmd: Optional[str] = None,
) -> str:
    """Perform OCR on a PIL Image using Tesseract or an available in-process fallback."""
    cmd = tesseract_cmd or get_tesseract_cmd()

    if cmd:
        try:
            pytesseract.pytesseract.tesseract_cmd = cmd
            text = pytesseract.image_to_string(image, lang=language)
            return text.strip()
        except Exception as exc:
            logger.warning("pytesseract failed with %s: %s", type(exc).__name__, exc)

    # Optional in-process fallback: rapidocr_onnxruntime if available
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        img_np = np.array(image.convert("RGB"))
        ocr_result, _ = engine(img_np)
        if ocr_result:
            lines = [box[1] for box in ocr_result]
            return "\n".join(lines).strip()
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("RapidOCR fallback failed: %s", exc)

    if not cmd:
        raise OCRError(
            message=(
                "Tesseract executable not found. Please install Tesseract OCR "
                "or set TESSERACT_CMD in your environment."
            ),
            details={"tesseract_cmd": cmd},
        )

    raise OCRError(
        message="OCR processing failed on the document image.",
        details={"language": language},
    )


def extract_text_from_pdf(
    content: bytes,
    *,
    settings: Optional[Settings] = None,
    dpi: int = 200,
) -> DocumentTextResult:
    """Extract per-page text from a PDF.

    First tries native text extraction on each page.
    If a page has fewer than NATIVE_TEXT_CHAR_THRESHOLD chars (e.g. vector curves or scanned),
    it rasterizes that page at specified DPI and applies OCR.
    """
    cfg = settings or get_settings()
    tess_cmd = get_tesseract_cmd(cfg)

    pages_result: list[PageTextResult] = []
    ocr_used = False

    # Open PDF with PyMuPDF for page count and rasterization
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF for extraction: %s", exc)
        raise OCRError(message="Failed to read PDF for text extraction.") from None

    # Open with pdfplumber for native text extraction
    plumber_pdf = None
    try:
        plumber_pdf = pdfplumber.open(io.BytesIO(content))
    except Exception as exc:
        logger.warning("pdfplumber open failed, will use fitz: %s", exc)

    try:
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            extracted_text = ""
            method = "native"

            # 1. Try native text extraction
            if plumber_pdf and page_idx < len(plumber_pdf.pages):
                try:
                    native_text = plumber_pdf.pages[page_idx].extract_text() or ""
                    if len(native_text.strip()) >= NATIVE_TEXT_CHAR_THRESHOLD:
                        extracted_text = native_text.strip()
                except Exception as exc:
                    logger.debug("pdfplumber extract_text page %d failed: %s", page_num, exc)

            if not extracted_text:
                # Try PyMuPDF native text
                fitz_text = doc[page_idx].get_text() or ""
                if len(fitz_text.strip()) >= NATIVE_TEXT_CHAR_THRESHOLD:
                    extracted_text = fitz_text.strip()

            # 2. If native text is insufficient (e.g. vector curves / scan), rasterize & OCR
            if len(extracted_text.strip()) < NATIVE_TEXT_CHAR_THRESHOLD:
                logger.info(
                    "Page %d has insufficient native text (len=%d); rasterizing for OCR (dpi=%d)",
                    page_num,
                    len(extracted_text),
                    dpi,
                )
                pix = doc[page_idx].get_pixmap(dpi=dpi)
                page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                extracted_text = run_ocr_on_image(
                    page_img,
                    language=cfg.ocr_language,
                    tesseract_cmd=tess_cmd,
                )
                method = "ocr"
                ocr_used = True

            pages_result.append(
                PageTextResult(
                    page_number=page_num,
                    text=extracted_text,
                    extraction_method=method,
                    char_count=len(extracted_text),
                )
            )
    finally:
        doc.close()
        if plumber_pdf:
            try:
                plumber_pdf.close()
            except Exception:
                pass

    total_chars = sum(p.char_count for p in pages_result)
    return DocumentTextResult(
        pages=pages_result,
        total_pages=len(pages_result),
        ocr_used=ocr_used,
        total_characters=total_chars,
    )


def extract_text_from_image(
    content: bytes,
    *,
    settings: Optional[Settings] = None,
) -> DocumentTextResult:
    """Extract text from a single image (JPEG / PNG)."""
    cfg = settings or get_settings()
    tess_cmd = get_tesseract_cmd(cfg)

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception as exc:
        logger.error("Failed to open image for OCR: %s", exc)
        raise OCRError(message="Failed to read image for OCR.") from None

    text = run_ocr_on_image(
        image,
        language=cfg.ocr_language,
        tesseract_cmd=tess_cmd,
    )

    page = PageTextResult(
        page_number=1,
        text=text,
        extraction_method="ocr",
        char_count=len(text),
    )

    return DocumentTextResult(
        pages=[page],
        total_pages=1,
        ocr_used=True,
        total_characters=len(text),
    )


def extract_document_text(
    content: bytes,
    file_type: str,
    *,
    settings: Optional[Settings] = None,
    dpi: int = 200,
) -> DocumentTextResult:
    """Unified entrypoint for document text extraction across PDF, JPG, and PNG."""
    if file_type == "application/pdf":
        return extract_text_from_pdf(content, settings=settings, dpi=dpi)
    elif file_type in {"image/jpeg", "image/png"}:
        return extract_text_from_image(content, settings=settings)
    else:
        raise OCRError(
            message=f"Unsupported file type for text extraction: {file_type}",
            details={"file_type": file_type},
        )
