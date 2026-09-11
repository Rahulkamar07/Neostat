"""API response envelope and request models for document processing endpoints."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.schemas.extraction import DocumentType
from app.schemas.validation import ValidationSummary


class ErrorDetail(BaseModel):
    """Standard error object inside the error envelope."""

    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable safe error message")
    details: Optional[dict[str, Any]] = Field(None, description="Additional context or validation issues")


class ErrorEnvelope(BaseModel):
    """Standardized error envelope adhering to specification: {"error": {"code": "...", "message": "..."}}."""

    error: ErrorDetail


class ProcessingMetadata(BaseModel):
    """Metadata regarding extraction execution."""

    processing_time_seconds: float = Field(..., description="Total pipeline latency in seconds")
    ocr_used: bool = Field(..., description="Whether OCR was performed")
    ocr_methods: list[str] = Field(default_factory=list, description="Extraction methods used per page")
    llm_provider: str = Field(..., description="Configured LLM provider name")
    llm_model: str = Field(..., description="Model name used for structured extraction")


class DocumentResponseData(BaseModel):
    """Payload for a processed document."""

    id: int = Field(..., description="Internal document record ID")
    document_name: str = Field(..., description="Original filename of the document")
    document_type: DocumentType = Field(..., description="Classification / document type")
    file_type: str = Field(..., description="MIME type of the file")
    page_count: int = Field(..., description="Number of pages in the document")
    file_size_bytes: int = Field(..., description="File size in bytes")
    processing_status: str = Field(..., description="Status: PROCESSED, FAILED, etc.")
    validation_status: Optional[str] = Field(None, description="Validation status: PASS, FAIL, NOT_APPLICABLE")
    overall_confidence: Optional[float] = Field(None, description="Average confidence across extracted fields")
    extracted_data: Optional[dict[str, Any]] = Field(None, description="Structured fields and line items")
    validation_summary: Optional[ValidationSummary] = Field(None, description="Detailed calculation checks")
    processing_metadata: Optional[ProcessingMetadata] = Field(None, description="Audit and performance metrics")
    created_at: Optional[str] = Field(None, description="ISO timestamp of creation")
    updated_at: Optional[str] = Field(None, description="ISO timestamp of last update")


class DocumentResponseEnvelope(BaseModel):
    """Standard success envelope for single document operations: {"data": {...}}."""

    data: DocumentResponseData


class DocumentListResponseEnvelope(BaseModel):
    """Paginated list response envelope for documents: {"data": [...], "total": int, "skip": int, "limit": int}."""

    data: list[DocumentResponseData]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    """Health check payload."""

    status: str = "ok"
    app_name: str
    app_env: str
    database: str
    llm_provider: str
    llm_model: str
