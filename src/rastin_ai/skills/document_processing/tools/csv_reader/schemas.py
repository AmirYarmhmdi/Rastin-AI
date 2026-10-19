"""File guide.

- Use: Defines Pydantic input and output schemas for reading CSV files.
- Usage: Import CSVReaderInput, and CSVReaderOutput from
  rastin_ai.skills.document_processing.tools.csv_reader.schemas.
- Duties: Defines CSVReaderInput, and CSVReaderOutput and related helper logic.
- Depends on: External packages only: pathlib, and pydantic.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class CSVReaderInput(BaseModel):
    path: Path
    delimiter: str | None = Field(default=None, min_length=1, max_length=1)
    encoding: str = Field(default="utf-8", min_length=1)
    max_rows: int | None = Field(default=None, ge=1)


class CSVReaderOutput(BaseModel):
    path: Path
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    rows: tuple[tuple[str, ...], ...]
    delimiter: str
    encoding: str
    truncated: bool
