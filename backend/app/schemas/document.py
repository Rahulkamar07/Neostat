"""Shared document API schemas used across validation and later extraction."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

FileValidationStatus = Literal["PASS", "FAILED"]
SupportedMediaType = Literal["application/pdf", "image/jpeg", "image/png"]


class FileValidationResult(BaseModel):
    """Input-control result from section 4.1 of the case study."""

    file_type: str
    is_supported: bool
    is_readable: bool
    page_count: Optional[int] = None
    status: FileValidationStatus
    issues: list[str] = Field(default_factory=list)
