"""OCR and Page Text Extraction schemas."""

from typing import Literal, Optional
from pydantic import BaseModel, Field

ExtractionMethod = Literal["native", "ocr"]


class PageTextResult(BaseModel):
    """Normalized text extraction result for an individual page."""

    page_number: int = Field(..., description="1-indexed page number")
    text: str = Field(..., description="Extracted textual content for the page")
    extraction_method: ExtractionMethod = Field(
        ..., description="Method used: 'native' for PDF character streams, 'ocr' for raster/scans"
    )
    char_count: int = Field(..., description="Number of characters in the extracted text")


class DocumentTextResult(BaseModel):
    """Normalized extraction result across all pages in the document."""

    pages: list[PageTextResult] = Field(default_factory=list)
    total_pages: int = Field(0, description="Total pages processed")
    ocr_used: bool = Field(False, description="Whether OCR was required on any page")
    total_characters: int = Field(0, description="Total characters extracted across all pages")

    @property
    def full_text(self) -> str:
        """Concatenated text across all pages separated by page markers."""
        return "\n\n".join(
            f"--- PAGE {p.page_number} ---\n{p.text}" for p in self.pages if p.text.strip()
        )
