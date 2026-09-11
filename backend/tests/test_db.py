"""Tests for Phase 6: Database models, session lifecycle, and DocumentRepository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.document import DocumentRecord
from app.repositories.document_repository import DocumentRepository


@pytest.fixture
def in_memory_db():
    """Provides an isolated in-memory SQLite database session for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_and_get_by_id(in_memory_db):
    repo = DocumentRepository(in_memory_db)
    record = repo.create(
        document_name="test_invoice.pdf",
        document_type="invoice",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=1024,
        processing_status="PROCESSED",
        validation_status="PASS",
        overall_confidence=0.98,
        extracted_data={"invoice_number": {"value": "INV-1001"}},
        validation_summary={"overall_status": "PASS", "checks": []},
        processing_metadata={"ocr_method": "native_text", "model": "gemini-3.5-flash-lite"},
        raw_ocr_text="Sample text on page 1",
    )

    assert record.id is not None
    assert record.document_name == "test_invoice.pdf"
    assert record.created_at is not None
    assert record.updated_at is not None

    fetched = repo.get_by_id(record.id)
    assert fetched is not None
    assert fetched.document_name == "test_invoice.pdf"
    assert fetched.extracted_data["invoice_number"]["value"] == "INV-1001"
    assert fetched.overall_confidence == 0.98

    # Test to_dict helper
    d = fetched.to_dict()
    assert d["id"] == record.id
    assert d["document_name"] == "test_invoice.pdf"
    assert d["validation_status"] == "PASS"


def test_get_latest_by_name(in_memory_db):
    repo = DocumentRepository(in_memory_db)
    # Create two records with the same document name
    repo.create(
        document_name="balance_sheet_2017.pdf",
        document_type="balance_sheet",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=2048,
        validation_status="FAIL",
    )
    r2 = repo.create(
        document_name="balance_sheet_2017.pdf",
        document_type="balance_sheet",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=2048,
        validation_status="PASS",
    )

    latest = repo.get_latest_by_name("balance_sheet_2017.pdf")
    assert latest is not None
    assert latest.id == r2.id
    assert latest.validation_status == "PASS"

    # Non-existent document name
    assert repo.get_latest_by_name("unknown.pdf") is None


def test_list_and_count_with_filters(in_memory_db):
    repo = DocumentRepository(in_memory_db)
    repo.create(
        document_name="inv1.pdf",
        document_type="invoice",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=500,
        validation_status="PASS",
    )
    repo.create(
        document_name="inv2.pdf",
        document_type="invoice",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=600,
        validation_status="FAIL",
    )
    repo.create(
        document_name="bs1.pdf",
        document_type="balance_sheet",
        file_type="application/pdf",
        page_count=2,
        file_size_bytes=1500,
        validation_status="PASS",
    )

    # Total count
    assert repo.count_documents() == 3

    # Filter by document_type
    invoices = repo.list_documents(document_type="invoice")
    assert len(invoices) == 2
    assert repo.count_documents(document_type="invoice") == 2

    # Filter by validation_status
    passed = repo.list_documents(validation_status="PASS")
    assert len(passed) == 2
    assert repo.count_documents(validation_status="PASS") == 2

    # Combined filter
    invoice_failed = repo.list_documents(document_type="invoice", validation_status="FAIL")
    assert len(invoice_failed) == 1
    assert invoice_failed[0].document_name == "inv2.pdf"


def test_delete_document(in_memory_db):
    repo = DocumentRepository(in_memory_db)
    rec = repo.create(
        document_name="delete_me.pdf",
        document_type="cash_flow",
        file_type="application/pdf",
        page_count=1,
        file_size_bytes=100,
    )
    doc_id = rec.id
    assert repo.get_by_id(doc_id) is not None

    deleted = repo.delete(doc_id)
    assert deleted is True
    assert repo.get_by_id(doc_id) is None

    # Deleting non-existent returns False
    assert repo.delete(99999) is False
