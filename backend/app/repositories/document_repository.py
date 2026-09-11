"""Repository for querying, saving, and updating DocumentRecord entries."""

from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.document import DocumentRecord


class DocumentRepository:
    """Encapsulates all database operations for documents."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        document_name: str,
        document_type: str,
        file_type: str,
        page_count: int,
        file_size_bytes: int,
        processing_status: str = "PROCESSED",
        validation_status: Optional[str] = None,
        overall_confidence: Optional[float] = None,
        extracted_data: Optional[dict] = None,
        validation_summary: Optional[dict] = None,
        processing_metadata: Optional[dict] = None,
        raw_ocr_text: Optional[str] = None,
    ) -> DocumentRecord:
        """Create and persist a new DocumentRecord."""
        record = DocumentRecord(
            document_name=document_name,
            document_type=document_type,
            file_type=file_type,
            page_count=page_count,
            file_size_bytes=file_size_bytes,
            processing_status=processing_status,
            validation_status=validation_status,
            overall_confidence=overall_confidence,
            extracted_data=extracted_data,
            validation_summary=validation_summary,
            processing_metadata=processing_metadata,
            raw_ocr_text=raw_ocr_text,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, doc_id: int) -> Optional[DocumentRecord]:
        """Fetch a document record by primary key."""
        return self.db.query(DocumentRecord).filter(DocumentRecord.id == doc_id).first()

    def get_latest_by_name(self, document_name: str) -> Optional[DocumentRecord]:
        """Fetch the most recently created document record matching document_name."""
        return (
            self.db.query(DocumentRecord)
            .filter(DocumentRecord.document_name == document_name)
            .order_by(desc(DocumentRecord.created_at))
            .first()
        )

    def list_documents(
        self,
        skip: int = 0,
        limit: int = 50,
        document_type: Optional[str] = None,
        validation_status: Optional[str] = None,
    ) -> list[DocumentRecord]:
        """List documents ordered by newest first, optionally filtered by type or status."""
        query = self.db.query(DocumentRecord)
        if document_type:
            query = query.filter(DocumentRecord.document_type == document_type)
        if validation_status:
            query = query.filter(DocumentRecord.validation_status == validation_status)
        return query.order_by(desc(DocumentRecord.created_at)).offset(skip).limit(limit).all()

    def count_documents(
        self,
        document_type: Optional[str] = None,
        validation_status: Optional[str] = None,
    ) -> int:
        """Count total matching records for pagination/stats."""
        query = self.db.query(DocumentRecord)
        if document_type:
            query = query.filter(DocumentRecord.document_type == document_type)
        if validation_status:
            query = query.filter(DocumentRecord.validation_status == validation_status)
        return query.count()

    def delete(self, doc_id: int) -> bool:
        """Delete a document record by ID."""
        record = self.get_by_id(doc_id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False
