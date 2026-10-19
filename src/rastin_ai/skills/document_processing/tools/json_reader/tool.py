"""File guide.

- Use: Implements the deterministic tool that reads JSON files.
- Usage: Import JSONReaderError, and JSONReaderTool from
  rastin_ai.skills.document_processing.tools.json_reader.tool.
- Duties: Defines JSONReaderError, and JSONReaderTool and related helper logic.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.json_reader.schemas, and
  rastin_ai.skills.tool.
"""

import json
from pathlib import Path

from rastin_ai.skills.tool import BaseTool

from .schemas import JSONReaderInput, JSONReaderOutput, JSONValue


class JSONReaderError(ValueError):
    pass


class JSONReaderTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="json_reader",
            description="Read and parse native JSON values from a local .json file.",
            capability="document.read.json",
            args_schema=JSONReaderInput,
        )

    def execute(self, tool_input: JSONReaderInput) -> JSONReaderOutput:
        path = self._validate_path(tool_input.path)

        try:
            text = path.read_text(encoding=tool_input.encoding)
        except LookupError as exc:
            msg = f"Unknown JSON encoding: {tool_input.encoding}"
            raise JSONReaderError(msg) from exc
        except UnicodeDecodeError as exc:
            msg = f"JSON file could not be decoded with encoding: {tool_input.encoding}"
            raise JSONReaderError(msg) from exc
        except OSError as exc:
            msg = f"Could not read JSON file: {path}"
            raise JSONReaderError(msg) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"Malformed JSON file: {path}"
            raise JSONReaderError(msg) from exc

        return JSONReaderOutput(
            path=path,
            data=data,
            encoding=tool_input.encoding,
            root_type=self._root_type(data),
            item_count=self._item_count(data),
        )

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser()

        if not normalized_path.exists():
            msg = f"JSON file does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"JSON input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() != ".json":
            msg = f"JSON input must use a .json extension: {normalized_path}"
            raise ValueError(msg)

        return normalized_path

    def _root_type(self, value: JSONValue) -> str:
        if isinstance(value, dict):
            return "object"

        if isinstance(value, list):
            return "array"

        if isinstance(value, str):
            return "string"

        if isinstance(value, bool):
            return "boolean"

        if value is None:
            return "null"

        return "number"

    def _item_count(self, value: JSONValue) -> int | None:
        if isinstance(value, dict | list):
            return len(value)

        return None
