"""Input-file validation (type, emptiness, integrity, size, page limit).

This is the document-control layer. It does not classify invoices vs statements.
Must run before OCR or LLM extraction.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    CorruptedFileError,
    EmptyFileError,
    FileTooLargeError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)
from app.core.logging import get_logger
from app.schemas.document import FileValidationResult

logger = get_logger(__name__)

PDF_MAGIC = b"%PDF"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

MEDIA_PDF = "application/pdf"
MEDIA_JPEG = "image/jpeg"
MEDIA_PNG = "image/png"

SUPPORTED_MEDIA_TYPES = {MEDIA_PDF, MEDIA_JPEG, MEDIA_PNG}


def detect_media_type(content: bytes) -> Optional[str]:
    """Return a supported MIME type from magic bytes, else None."""
    if not content:
        return None
    head = content.lstrip()
    if head.startswith(PDF_MAGIC):
        return MEDIA_PDF
    if content.startswith(JPEG_MAGIC):
        return MEDIA_JPEG
    if content.startswith(PNG_MAGIC):
        return MEDIA_PNG
    return None


def validate_document_file(
    content: bytes,
    filename: Optional[str] = None,
    *,
    settings: Optional[Settings] = None,
) -> FileValidationResult:
    """Validate bytes before any OCR/extraction.

    Raises a FileValidationError subclass on failure. Returns a PASS result
    only when the file is a readable PDF/JPG/PNG of at most max_pages.
    """
    cfg = settings or get_settings()
    label = filename or "upload"

    logger.info("File validation started name=%s size_bytes=%s", label, len(content) if content else 0)

    if content is None or len(content) == 0:
        logger.warning("File validation failed name=%s reason=empty", label)
        raise EmptyFileError(details={"file_name": label})

    if len(content) > cfg.max_upload_bytes:
        logger.warning(
            "File validation failed name=%s reason=too_large size_bytes=%s max_bytes=%s",
            label,
            len(content),
            cfg.max_upload_bytes,
        )
        raise FileTooLargeError(
            details={
                "file_name": label,
                "size_bytes": len(content),
                "max_bytes": cfg.max_upload_bytes,
            }
        )

    media_type = detect_media_type(content)
    if media_type not in SUPPORTED_MEDIA_TYPES:
        logger.warning("File validation failed name=%s reason=unsupported_type", label)
        raise UnsupportedFileTypeError(details={"file_name": label})

    try:
        page_count = _count_pages(content, media_type)
    except (CorruptedFileError, PageLimitExceededError):
        raise
    except Exception:
        logger.exception("File validation failed name=%s reason=unreadable", label)
        raise CorruptedFileError(details={"file_name": label}) from None

    if page_count < 1:
        logger.warning("File validation failed name=%s reason=no_pages", label)
        raise CorruptedFileError(details={"file_name": label})

    if page_count > cfg.max_pages:
        logger.warning(
            "File validation failed name=%s reason=page_limit page_count=%s max_pages=%s",
            label,
            page_count,
            cfg.max_pages,
        )
        raise PageLimitExceededError(
            details={
                "file_name": label,
                "page_count": page_count,
                "max_pages": cfg.max_pages,
            }
        )

    result = FileValidationResult(
        file_type=media_type,
        is_supported=True,
        is_readable=True,
        page_count=page_count,
        status="PASS",
    )
    logger.info(
        "File validation passed name=%s file_type=%s page_count=%s",
        label,
        media_type,
        page_count,
    )
    return result


def _count_pages(content: bytes, media_type: str) -> int:
    if media_type == MEDIA_PDF:
        return _pdf_page_count(content)
    return _image_page_count(content)


def _pdf_page_count(content: bytes) -> int:
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        logger.warning("PDF parse failed: %s", type(exc).__name__)
        raise CorruptedFileError() from None

    if getattr(reader, "is_encrypted", False):
        logger.warning("Encrypted PDF rejected as unreadable")
        raise CorruptedFileError()

    try:
        return len(reader.pages)
    except Exception:
        logger.warning("PDF page enumeration failed")
        raise CorruptedFileError() from None


def _image_page_count(content: bytes) -> int:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            if image.format not in {"JPEG", "PNG"}:
                raise UnsupportedFileTypeError()
            if not image.size[0] or not image.size[1]:
                raise CorruptedFileError()
            n_frames = getattr(image, "n_frames", 1) or 1
            return int(n_frames)
    except UnsupportedFileTypeError:
        raise
    except CorruptedFileError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        logger.warning("Image parse failed: %s", type(exc).__name__)
        raise CorruptedFileError() from None
