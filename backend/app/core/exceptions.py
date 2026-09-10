"""Domain exceptions mapped to stable error codes and HTTP statuses.

Handlers (Phase 7) convert these to the spec error envelope:

    {"error": {"code": "...", "message": "..."}}

Messages are safe for clients: no stack traces, paths, or secrets.
"""

from typing import Any, Optional


class AppError(Exception):
    """Base application error."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details = details or {}
        super().__init__(self.message)

    def to_error_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            body["error"]["details"] = self.details
        return body


class FileValidationError(AppError):
    """Generic input-file validation failure (HTTP 400)."""

    code = "FILE_VALIDATION_FAILED"
    http_status = 400
    message = "The uploaded file failed validation."


class UnsupportedFileTypeError(FileValidationError):
    code = "UNSUPPORTED_FILE_TYPE"
    http_status = 400
    message = "Only PDF / JPG / PNG documents are supported."


class EmptyFileError(FileValidationError):
    code = "EMPTY_FILE"
    http_status = 400
    message = "The uploaded file is empty."


class CorruptedFileError(FileValidationError):
    code = "CORRUPTED_FILE"
    http_status = 400
    message = "The uploaded file is unreadable or corrupted."


class PageLimitExceededError(FileValidationError):
    code = "PAGE_LIMIT_EXCEEDED"
    http_status = 400
    message = "Documents must not exceed 3 pages."


class FileTooLargeError(FileValidationError):
    code = "FILE_TOO_LARGE"
    http_status = 413
    message = "The uploaded file exceeds the maximum allowed size."


class DocumentNotFoundError(AppError):
    code = "DOCUMENT_NOT_FOUND"
    http_status = 404
    message = "No processed result was found for the given document name."


class OCRError(AppError):
    code = "OCR_FAILED"
    http_status = 502
    message = "Text extraction from the document failed."


class LLMExtractionError(AppError):
    code = "LLM_EXTRACTION_FAILED"
    http_status = 502
    message = "Structured field extraction failed."


class LLMTimeoutError(LLMExtractionError):
    code = "LLM_TIMEOUT"
    http_status = 504
    message = "The extraction model did not respond in time."


class LLMConfigurationError(AppError):
    code = "LLM_NOT_CONFIGURED"
    http_status = 500
    message = "The language-model provider is not configured."


class DatabaseError(AppError):
    code = "DATABASE_ERROR"
    http_status = 500
    message = "A database error occurred while storing or retrieving results."


class UnexpectedProcessingError(AppError):
    code = "UNEXPECTED_ERROR"
    http_status = 500
    message = "Document processing failed due to an unexpected error."
