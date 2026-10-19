"""File guide.

- Use: Defines Pydantic input and output schemas for reading DOCX files.
- Usage: Import DOCXParagraph, DOCXReaderInput, DOCXReaderOutput, and 1 more from
  rastin_ai.skills.document_processing.tools.docx_reader.schemas.
- Duties: Defines DOCXParagraph, DOCXReaderInput, DOCXReaderOutput, and DOCXTable
  and related helper logic.
- Depends on: External packages only: pathlib, and pydantic.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class DOCXReaderInput(BaseModel):
    path: Path


class DOCXParagraph(BaseModel):
    index: int = Field(ge=1)
    text: str


class DOCXTable(BaseModel):
    index: int = Field(ge=1)
    rows: tuple[tuple[str, ...], ...]


class DOCXReaderOutput(BaseModel):
    path: Path
    paragraphs: tuple[DOCXParagraph, ...]
    tables: tuple[DOCXTable, ...]
    paragraph_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    metadata: dict[str, str | None]
