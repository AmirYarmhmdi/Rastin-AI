"""File guide.

- Use: Implements the deterministic tool that reads PDF files.
- Usage: Import PDFReaderError, and PDFReaderTool from
  rastin_ai.skills.document_processing.tools.pdf_reader.tool.
- Duties: Defines PDFReaderError, and PDFReaderTool and related helper logic.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.pdf_reader.schemas, and
  rastin_ai.skills.tool.
"""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rastin_ai.skills.document_processing.tools.pdf_reader.schemas import (
    PDFPage,
    PDFReaderInput,
    PDFReaderOutput,
)
from rastin_ai.skills.tool import BaseTool


class PDFReaderError(ValueError):
    pass


class PDFReaderTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="pdf_reader",
            description="Extract text and basic metadata from a local text-based PDF.",
            capability="document.read.pdf",
            args_schema=PDFReaderInput,
        )

    def execute(self, tool_input: PDFReaderInput) -> PDFReaderOutput:
        path = self._validate_path(tool_input.path)

        try:
            reader = PdfReader(path)
        except PdfReadError as exc:
            msg = f"Could not read PDF file: {path}"
            raise PDFReaderError(msg) from exc

        if reader.is_encrypted:
            msg = f"Encrypted PDF files are not supported: {path}"
            raise PDFReaderError(msg)

        pages = tuple(
            PDFPage(page_number=index, text=page.extract_text() or "")
            for index, page in enumerate(reader.pages, start=1)
        )

        return PDFReaderOutput(
            path=path,
            page_count=len(pages),
            pages=pages,
            metadata=self._normalize_metadata(reader.metadata),
        )

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser()

        if not normalized_path.exists():
            msg = f"PDF file does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"PDF input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() != ".pdf":
            msg = f"PDF input must use a .pdf extension: {normalized_path}"
            raise ValueError(msg)

        return normalized_path

    def _normalize_metadata(self, metadata: object) -> dict[str, str | None]:
        if metadata is None:
            return {}

        return {
            str(key).lstrip("/"): None if value is None else str(value)
            for key, value in dict(metadata).items()
        }
