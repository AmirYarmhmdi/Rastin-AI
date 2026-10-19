"""File guide.

- Use: Defines Pydantic input and output schemas for reading JSON files.
- Usage: Import JSONReaderInput, and JSONReaderOutput from
  rastin_ai.skills.document_processing.tools.json_reader.schemas.
- Duties: Defines JSONReaderInput, and JSONReaderOutput and related helper logic.
- Depends on: External packages only: pathlib, and pydantic.
"""

from pathlib import Path

from pydantic import BaseModel, Field

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class JSONReaderInput(BaseModel):
    path: Path
    encoding: str = Field(default="utf-8", min_length=1)


class JSONReaderOutput(BaseModel):
    path: Path
    data: JSONValue
    encoding: str
    root_type: str
    item_count: int | None
