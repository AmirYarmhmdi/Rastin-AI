"""File guide.

- Use: Implements the deterministic tool that reads plain text files.
- Usage: Import TextReaderError, and TextReaderTool from
  rastin_ai.skills.document_processing.tools.text_reader.tool.
- Duties: Defines TextReaderError, and TextReaderTool and related helper logic.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.text_reader.schemas, and
  rastin_ai.skills.tool.
"""

from pathlib import Path

from rastin_ai.skills.tool import BaseTool

from .schemas import TextReaderInput, TextReaderOutput


class TextReaderError(ValueError):
    pass


class TextReaderTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="text_reader",
            description="Read raw text from a local .txt file.",
            capability="document.read.text",
            args_schema=TextReaderInput,
        )

    def execute(self, tool_input: TextReaderInput) -> TextReaderOutput:
        path = self._validate_path(tool_input.path)

        try:
            text = path.read_text(encoding=tool_input.encoding)
        except LookupError as exc:
            msg = f"Unknown text encoding: {tool_input.encoding}"
            raise TextReaderError(msg) from exc
        except UnicodeDecodeError as exc:
            msg = f"Text file could not be decoded with encoding: {tool_input.encoding}"
            raise TextReaderError(msg) from exc
        except OSError as exc:
            msg = f"Could not read text file: {path}"
            raise TextReaderError(msg) from exc

        char_count = len(text)
        returned_text = self._limit_text(text, tool_input.max_chars)

        return TextReaderOutput(
            path=path,
            text=returned_text,
            encoding=tool_input.encoding,
            char_count=char_count,
            line_count=len(text.splitlines()),
            truncated=tool_input.max_chars is not None
            and tool_input.max_chars < char_count,
        )

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser()

        if not normalized_path.exists():
            msg = f"Text file does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"Text input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() != ".txt":
            msg = f"Text input must use a .txt extension: {normalized_path}"
            raise ValueError(msg)

        return normalized_path

    def _limit_text(self, text: str, max_chars: int | None) -> str:
        if max_chars is None:
            return text

        return text[:max_chars]
