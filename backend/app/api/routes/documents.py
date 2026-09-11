"""FastAPI routes for document processing, retrieval, and health check."""

import time
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.exceptions import AppError, DocumentNotFoundError, LLMExtractionError
from app.core.logging import get_logger
from app.models.document import DocumentRecord
from app.repositories.document_repository import DocumentRepository
from app.schemas.api import (
    DocumentListResponseEnvelope,
    DocumentResponseData,
    DocumentResponseEnvelope,
    HealthResponse,
    ProcessingMetadata,
)
from app.schemas.extraction import DocumentType
from app.services.document_validation_service import validate_document_file
from app.services.extraction_service import extract_structured_data
from app.services.financial_validation_service import validate_financial_calculations
from app.services.ocr_service import extract_document_text

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


def _calculate_overall_confidence(extracted_dict: dict) -> Optional[float]:
    """Recursively collect confidence scores and compute the mean."""
    confidences: list[float] = []

    def _walk(obj):
        if isinstance(obj, dict):
            if "confidence" in obj and isinstance(obj["confidence"], (int, float)):
                confidences.append(float(obj["confidence"]))
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(extracted_dict)
    if confidences:
        return round(sum(confidences) / len(confidences), 4)
    return None


def _build_document_response(record: DocumentRecord) -> DocumentResponseData:
    """Helper to convert a DocumentRecord into DocumentResponseData."""
    metadata = None
    if record.processing_metadata:
        try:
            metadata = ProcessingMetadata.model_validate(record.processing_metadata)
        except Exception:
            metadata = None

    return DocumentResponseData(
        id=record.id,
        document_name=record.document_name,
        document_type=record.document_type,
        file_type=record.file_type,
        page_count=record.page_count,
        file_size_bytes=record.file_size_bytes,
        processing_status=record.processing_status,
        validation_status=record.validation_status,
        overall_confidence=record.overall_confidence,
        extracted_data=record.extracted_data,
        validation_summary=record.validation_summary,
        processing_metadata=metadata,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


@router.post(
    "/api/v1/documents/process",
    response_model=DocumentResponseEnvelope,
    status_code=status.HTTP_201_CREATED,
    summary="Process a document through the full extraction & validation pipeline",
    description=(
        "Uploads a PDF, JPG, or PNG document (max 3 pages), extracts text via native/OCR methods, "
        "extracts structured fields matching the document_type schema using LLM, validates financial "
        "calculations, stores the result in the database, and returns the complete result."
    ),
)
async def process_document(
    file: UploadFile = File(..., description="Document file (PDF, JPG, or PNG, max 3 pages)"),
    document_type: DocumentType = Form(
        ...,
        description="Type of document: 'invoice', 'balance_sheet', 'profit_and_loss', or 'cash_flow_statement'",
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentResponseEnvelope:
    start_time = time.time()
    filename = file.filename or "unknown_document"
    logger.info("Received process request for file='%s' type='%s'", filename, document_type)

    # 1. Read file bytes
    content = await file.read()

    # 2. Input File Validation (Phase 1)
    # Raises FileValidationError subclasses (UnsupportedFileTypeError, PageLimitExceededError, etc.) on failure
    val_result = validate_document_file(content, filename=filename, settings=settings)

    # 3. OCR / Text Extraction Pipeline (Phase 3)
    ocr_result = extract_document_text(content, file_type=val_result.file_type, settings=settings)

    # 4. LLM Structured Extraction (Phase 4)
    extracted_obj = extract_structured_data(ocr_result, document_type=document_type, settings=settings)
    extracted_dict = extracted_obj.model_dump()

    # Calculate overall confidence
    overall_conf = _calculate_overall_confidence(extracted_dict)

    # 5. Deterministic Financial Validation (Phase 5)
    financial_summary = validate_financial_calculations(
        extracted_obj, document_type=document_type, settings=settings
    )

    elapsed_time = round(time.time() - start_time, 3)

    # Prepare processing metadata
    metadata = ProcessingMetadata(
        processing_time_seconds=elapsed_time,
        ocr_used=ocr_result.ocr_used,
        ocr_methods=[p.extraction_method for p in ocr_result.pages],
        llm_provider=settings.llm_provider,
        llm_model=settings.active_llm_model(),
    )

    # 6. Database Persistence (Phase 6)
    repo = DocumentRepository(db)
    record = repo.create(
        document_name=filename,
        document_type=document_type,
        file_type=val_result.file_type,
        page_count=val_result.page_count or 1,
        file_size_bytes=len(content),
        processing_status="PROCESSED",
        validation_status=financial_summary.overall_status,
        overall_confidence=overall_conf,
        extracted_data=extracted_dict,
        validation_summary=financial_summary.model_dump(),
        processing_metadata=metadata.model_dump(),
        raw_ocr_text=ocr_result.full_text,
    )

    logger.info(
        "Successfully processed and stored document id=%d name='%s' status=%s in %.2fs",
        record.id,
        filename,
        financial_summary.overall_status,
        elapsed_time,
    )

    return DocumentResponseEnvelope(data=_build_document_response(record))


@router.get(
    "/api/v1/documents/{document_name}",
    response_model=DocumentResponseEnvelope,
    summary="Retrieve the latest processed result for a document",
    description="Retrieves the most recent extraction and validation result for the given document name.",
)
def get_document_by_name(
    document_name: str,
    db: Session = Depends(get_db),
) -> DocumentResponseEnvelope:
    repo = DocumentRepository(db)
    record = repo.get_latest_by_name(document_name)
    if not record:
        raise DocumentNotFoundError(
            message=f"No processed document found matching '{document_name}'",
            details={"document_name": document_name},
        )
    return DocumentResponseEnvelope(data=_build_document_response(record))


@router.get(
    "/api/v1/documents",
    response_model=DocumentListResponseEnvelope,
    summary="List all processed documents",
    description="Returns a paginated list of processed documents, optionally filtered by type or validation status.",
)
def list_documents(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Limit of results per page"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    validation_status: Optional[str] = Query(None, description="Filter by validation status (PASS, FAIL, etc.)"),
    db: Session = Depends(get_db),
) -> DocumentListResponseEnvelope:
    repo = DocumentRepository(db)
    records = repo.list_documents(
        skip=skip,
        limit=limit,
        document_type=document_type,
        validation_status=validation_status,
    )
    total = repo.count_documents(
        document_type=document_type,
        validation_status=validation_status,
    )
    return DocumentListResponseEnvelope(
        data=[_build_document_response(r) for r in records],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns platform health status and runtime configuration summary.",
)
def health_check(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_env=settings.app_env,
        database="connected",
        llm_provider=settings.llm_provider,
        llm_model=settings.active_llm_model(),
    )
