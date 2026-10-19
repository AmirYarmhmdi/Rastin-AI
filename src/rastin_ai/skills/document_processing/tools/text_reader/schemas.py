"""File guide.

- Use: Defines Pydantic input and output schemas for reading plain text files.
- Usage: Import TextReaderInput, and TextReaderOutput from
  rastin_ai.skills.document_processing.tools.text_reader.schemas.
- Duties: Defines TextReaderInput, and TextReaderOutput and related helper logic.
- Depends on: External packages only: pathlib, and pydantic.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class TextReaderInput(BaseModel):
    path: Path
    encoding: str = Field(default="utf-8", min_length=1)
    max_chars: int | None = Field(default=None, ge=1)


class TextReaderOutput(BaseModel):
    path: Path
    text: str
    encoding: str
    char_count: int = Field(ge=0)
    line_count: int = Field(ge=0)
    truncated: bool
