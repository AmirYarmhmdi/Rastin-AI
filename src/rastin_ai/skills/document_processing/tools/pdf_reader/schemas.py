"""File guide.

- Use: Defines Pydantic input and output schemas for reading PDF files.
- Usage: Import PDFPage, PDFReaderInput, and PDFReaderOutput from
  rastin_ai.skills.document_processing.tools.pdf_reader.schemas.
- Duties: Defines PDFPage, PDFReaderInput, and PDFReaderOutput and related helper
  logic.
- Depends on: External packages only: pathlib, and pydantic.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class PDFReaderInput(BaseModel):
    path: Path


class PDFPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str


class PDFReaderOutput(BaseModel):
    path: Path
    page_count: int = Field(ge=0)
    pages: tuple[PDFPage, ...]
    metadata: dict[str, str | None]
