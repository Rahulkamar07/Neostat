"""SQLAlchemy model for storing processed documents, extraction results, and validation outcomes."""

import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    DateTime,
    JSON,
    Index,
)

from app.core.database import Base


class DocumentRecord(Base):
    """Represents an ingested and processed document in the platform."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_name = Column(String(255), nullable=False, index=True)
    document_type = Column(String(50), nullable=False, index=True)  # invoice, balance_sheet, profit_loss, cash_flow
    file_type = Column(String(50), nullable=False)  # application/pdf, image/jpeg, image/png
    page_count = Column(Integer, nullable=False, default=1)
    file_size_bytes = Column(Integer, nullable=False, default=0)

    processing_status = Column(
        String(50), nullable=False, default="PROCESSED", index=True
    )  # PROCESSED, FAILED, PARTIAL
    validation_status = Column(
        String(50), nullable=True, index=True
    )  # PASS, FAIL, NOT_APPLICABLE

    overall_confidence = Column(Float, nullable=True)

    # Structured JSON data fields
    extracted_data = Column(JSON, nullable=True)  # Raw schema dict from extraction
    validation_summary = Column(JSON, nullable=True)  # Checks list and status
    processing_metadata = Column(JSON, nullable=True)  # OCR method, timings, model name

    # Raw OCR full text preserved for inspection & audit
    raw_ocr_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_documents_name_created", "document_name", "created_at"),
    )

    def to_dict(self) -> dict:
        """Helper to convert the record into a clean dictionary representation."""
        return {
            "id": self.id,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "file_size_bytes": self.file_size_bytes,
            "processing_status": self.processing_status,
            "validation_status": self.validation_status,
            "overall_confidence": self.overall_confidence,
            "extracted_data": self.extracted_data,
            "validation_summary": self.validation_summary,
            "processing_metadata": self.processing_metadata,
            "raw_ocr_text": self.raw_ocr_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
