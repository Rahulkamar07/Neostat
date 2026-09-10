"""File validation tests: supported types, integrity, size, and page limit."""

import io

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.core.config import Settings
from app.core.exceptions import (
    CorruptedFileError,
    EmptyFileError,
    FileTooLargeError,
    PageLimitExceededError,
    UnsupportedFileTypeError,
)
from app.services.document_validation_service import validate_document_file


def _settings(**overrides) -> Settings:
    data = {
        "max_pages": 3,
        "max_upload_bytes": 1024 * 1024,
        "openai_api_key": "",
    }
    data.update(overrides)
    return Settings(**data)


def _pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _encrypted_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt("not-a-password-we-know")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _image_bytes(fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", (16, 16), color=(200, 40, 40))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def test_valid_single_page_pdf_passes():
    result = validate_document_file(_pdf_bytes(1), "statement.pdf", settings=_settings())
    assert result.status == "PASS"
    assert result.is_supported is True
    assert result.is_readable is True
    assert result.file_type == "application/pdf"
    assert result.page_count == 1


def test_valid_three_page_pdf_is_within_limit():
    result = validate_document_file(_pdf_bytes(3), "three.pdf", settings=_settings())
    assert result.status == "PASS"
    assert result.page_count == 3


def test_valid_jpeg_passes():
    result = validate_document_file(_image_bytes("JPEG"), "invoice.jpg", settings=_settings())
    assert result.status == "PASS"
    assert result.file_type == "image/jpeg"
    assert result.page_count == 1


def test_valid_png_passes():
    result = validate_document_file(_image_bytes("PNG"), "invoice.png", settings=_settings())
    assert result.status == "PASS"
    assert result.file_type == "image/png"
    assert result.page_count == 1


def test_empty_file_rejected():
    with pytest.raises(EmptyFileError) as exc:
        validate_document_file(b"", "empty.pdf", settings=_settings())
    assert exc.value.code == "EMPTY_FILE"
    assert exc.value.http_status == 400


def test_oversized_file_rejected():
    content = _pdf_bytes(1)
    with pytest.raises(FileTooLargeError) as exc:
        validate_document_file(content, "big.pdf", settings=_settings(max_upload_bytes=10))
    assert exc.value.code == "FILE_TOO_LARGE"
    assert exc.value.http_status == 413


def test_four_page_pdf_rejected():
    with pytest.raises(PageLimitExceededError) as exc:
        validate_document_file(_pdf_bytes(4), "too-long.pdf", settings=_settings())
    assert exc.value.code == "PAGE_LIMIT_EXCEEDED"
    assert exc.value.details["page_count"] == 4


def test_plain_text_rejected_as_unsupported():
    with pytest.raises(UnsupportedFileTypeError) as exc:
        validate_document_file(b"this is not a document", "notes.txt", settings=_settings())
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"
    body = exc.value.to_error_body()
    assert "stack" not in str(body).lower()
    assert "Only PDF / JPG / PNG" in body["error"]["message"]


def test_gif_rejected_as_unsupported():
    gif = _image_bytes("GIF")
    with pytest.raises(UnsupportedFileTypeError):
        validate_document_file(gif, "anim.gif", settings=_settings())


def test_truncated_pdf_rejected_as_corrupted():
    with pytest.raises(CorruptedFileError) as exc:
        validate_document_file(b"%PDF-1.4\n% truncated", "broken.pdf", settings=_settings())
    assert exc.value.code == "CORRUPTED_FILE"


def test_truncated_jpeg_rejected_as_corrupted():
    with pytest.raises(CorruptedFileError):
        validate_document_file(b"\xff\xd8\xff\xe0broken", "broken.jpg", settings=_settings())


def test_encrypted_pdf_rejected_as_unreadable():
    with pytest.raises(CorruptedFileError):
        validate_document_file(_encrypted_pdf_bytes(), "secret.pdf", settings=_settings())
