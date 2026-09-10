"""Tests for Phase 3: OCR and unified text extraction pipeline."""

from pathlib import Path
import pytest

from app.core.exceptions import OCRError
from app.schemas.ocr import DocumentTextResult, PageTextResult
from app.services.ocr_service import extract_document_text, extract_text_from_image, extract_text_from_pdf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = PROJECT_ROOT / "New Dataset 1" / "New Dataset"


@pytest.fixture
def balance_sheet_pdf() -> bytes:
    sample_path = DATASET_DIR / "Balance Sheet" / "Consolidated Balance Sheet 2017.pdf"
    assert sample_path.exists(), f"Missing dataset file: {sample_path}"
    return sample_path.read_bytes()


@pytest.fixture
def cash_flow_pdf() -> bytes:
    sample_path = DATASET_DIR / "Cash Flows" / "Consolidated Cash Flow Statement 2017.pdf"
    assert sample_path.exists(), f"Missing dataset file: {sample_path}"
    return sample_path.read_bytes()


@pytest.fixture
def profit_loss_pdf() -> bytes:
    sample_path = DATASET_DIR / "Profit & Loss" / "Consolidated Profit & Loss 2017.pdf"
    assert sample_path.exists(), f"Missing dataset file: {sample_path}"
    return sample_path.read_bytes()


@pytest.fixture
def invoice_image() -> bytes:
    sample_path = DATASET_DIR / "Invoices" / "X00016469619.jpg"
    assert sample_path.exists(), f"Missing dataset file: {sample_path}"
    return sample_path.read_bytes()


def test_invoice_image_ocr_extraction(invoice_image: bytes):
    """Invoice JPG is scanned/raster and must be extracted using OCR into a single page result."""
    result = extract_document_text(invoice_image, file_type="image/jpeg")

    assert isinstance(result, DocumentTextResult)
    assert result.total_pages == 1
    assert result.ocr_used is True
    assert len(result.pages) == 1

    page = result.pages[0]
    assert isinstance(page, PageTextResult)
    assert page.page_number == 1
    assert page.extraction_method == "ocr"
    assert page.char_count > 20
    assert len(page.text.strip()) > 0


def test_balance_sheet_vector_pdf_extraction(balance_sheet_pdf: bytes):
    """Balance sheet PDF contains vector-drawn text with no native font glyphs;

    the service must rasterize at 200 DPI and extract text via OCR.
    """
    result = extract_document_text(balance_sheet_pdf, file_type="application/pdf")

    assert isinstance(result, DocumentTextResult)
    assert result.total_pages == 1
    assert result.ocr_used is True
    assert len(result.pages) == 1

    page = result.pages[0]
    assert page.page_number == 1
    assert page.extraction_method == "ocr"
    assert page.char_count > 50
    # Common financial terms expected in Balance Sheet
    lower_text = page.text.lower()
    assert any(term in lower_text for term in ["balance", "sheet", "asset", "capital", "liabilities", "total"])


def test_cash_flow_multipage_pdf_extraction(cash_flow_pdf: bytes):
    """Cash Flow PDF has 2 pages; verify all pages are processed and numbered correctly."""
    result = extract_document_text(cash_flow_pdf, file_type="application/pdf")

    assert isinstance(result, DocumentTextResult)
    assert result.total_pages == 2
    assert len(result.pages) == 2
    assert [p.page_number for p in result.pages] == [1, 2]
    assert all(p.char_count > 0 for p in result.pages)
    assert "PAGE 1" in result.full_text
    assert "PAGE 2" in result.full_text


def test_profit_loss_pdf_extraction(profit_loss_pdf: bytes):
    """Profit & Loss statement PDF extraction."""
    result = extract_document_text(profit_loss_pdf, file_type="application/pdf")

    assert isinstance(result, DocumentTextResult)
    assert result.total_pages == 1
    assert len(result.pages) == 1
    assert result.pages[0].char_count > 50
    lower_text = result.pages[0].text.lower()
    assert any(term in lower_text for term in ["profit", "loss", "income", "expenditure", "revenue", "net"])


def test_invalid_file_type_raises_ocr_error():
    """Unsupported MIME types passed directly to extract_document_text raise OCRError."""
    with pytest.raises(OCRError) as exc_info:
        extract_document_text(b"some fake content", file_type="text/plain")
    assert exc_info.value.code == "OCR_FAILED"
