"""Tests for Phase 7: FastAPI endpoints, OpenAPI specs, exception handling, and full pipeline routes."""

import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.document import DocumentRecord
from app.schemas.extraction import ExtractedField, InvoiceData, InvoiceLineItem
from app.schemas.ocr import DocumentTextResult, PageTextResult
from app.schemas.validation import ValidationCheck, ValidationSummary


from sqlalchemy.pool import StaticPool

# Isolated SQLite database for API tests
@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db_session):
    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _valid_pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "llm_provider" in data


def test_openapi_documentation_accessible(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "paths" in spec
    assert "/api/v1/documents/process" in spec["paths"]
    assert "/api/v1/documents/{document_name}" in spec["paths"]
    assert "/api/v1/documents" in spec["paths"]
    assert "/api/v1/health" in spec["paths"]


def test_process_unsupported_file_type_returns_400_envelope(client):
    fake_txt = io.BytesIO(b"Hello world, this is a plain text file")
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("notes.txt", fake_txt, "text/plain")},
        data={"document_type": "invoice"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "PDF / JPG / PNG" in body["error"]["message"]


def test_process_empty_file_returns_400_envelope(client):
    empty_file = io.BytesIO(b"")
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("empty.pdf", empty_file, "application/pdf")},
        data={"document_type": "invoice"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "EMPTY_FILE"


def test_process_page_limit_exceeded_returns_400_envelope(client):
    four_page_pdf = _valid_pdf_bytes(pages=4)
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("large.pdf", io.BytesIO(four_page_pdf), "application/pdf")},
        data={"document_type": "balance_sheet"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "PAGE_LIMIT_EXCEEDED"


def test_process_invalid_document_type_returns_400_envelope(client):
    valid_pdf = _valid_pdf_bytes(pages=1)
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("doc.pdf", io.BytesIO(valid_pdf), "application/pdf")},
        data={"document_type": "unknown_type_not_supported"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "REQUEST_VALIDATION_ERROR"


@patch("app.api.routes.documents.extract_document_text")
@patch("app.api.routes.documents.extract_structured_data")
@patch("app.api.routes.documents.validate_financial_calculations")
def test_process_document_success_pipeline(
    mock_validate_fin,
    mock_extract_llm,
    mock_extract_ocr,
    client,
):
    valid_pdf = _valid_pdf_bytes(pages=1)

    # 1. Mock OCR result
    mock_extract_ocr.return_value = DocumentTextResult(
        total_pages=1,
        total_characters=100,
        ocr_used=False,
        pages=[PageTextResult(page_number=1, text="Invoice INV-999 Total: 100.00", extraction_method="native", char_count=100)],
    )

    # 2. Mock LLM extraction result
    mock_invoice = InvoiceData(
        invoice_number=ExtractedField(value="INV-999", confidence=0.99),
        subtotal=ExtractedField(value=100.0, confidence=0.98),
        total_amount=ExtractedField(value=100.0, confidence=0.98),
        line_items=[
            InvoiceLineItem(
                description="Consulting",
                quantity=1.0,
                unit_price=100.0,
                amount=100.0,
            )
        ],
    )
    mock_extract_llm.return_value = mock_invoice

    # 3. Mock Financial validation result
    mock_validate_fin.return_value = ValidationSummary(
        checks=[
            ValidationCheck(
                name="invoice_subtotal_tax_reconciliation",
                formula="subtotal + tax - discount = total_amount",
                operands={"subtotal": 100.0, "total_amount": 100.0},
                calculated_value=100.0,
                reported_value=100.0,
                variance=0.0,
                status="PASS",
            )
        ],
        overall_status="PASS",
        issues=[],
    )

    # Execute request
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("invoice_sample.pdf", io.BytesIO(valid_pdf), "application/pdf")},
        data={"document_type": "invoice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "data" in body
    data = body["data"]
    assert data["document_name"] == "invoice_sample.pdf"
    assert data["document_type"] == "invoice"
    assert data["processing_status"] == "PROCESSED"
    assert data["validation_status"] == "PASS"
    assert data["overall_confidence"] is not None
    assert data["extracted_data"]["invoice_number"]["value"] == "INV-999"
    assert data["validation_summary"]["overall_status"] == "PASS"
    assert data["processing_metadata"]["ocr_used"] is False

    # Verify retrieval by name
    get_res = client.get("/api/v1/documents/invoice_sample.pdf")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == data["id"]

    # Verify list documents
    list_res = client.get("/api/v1/documents")
    assert list_res.status_code == 200
    list_body = list_res.json()
    assert list_body["total"] == 1
    assert len(list_body["data"]) == 1
    assert list_body["data"][0]["document_name"] == "invoice_sample.pdf"


def test_get_document_not_found_returns_404(client):
    response = client.get("/api/v1/documents/non_existent_file.pdf")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "DOCUMENT_NOT_FOUND"
