"""File guide.

- Use: Loads PDF files into RAG Document objects.
- Usage: Import PDFLoader from rastin_ai.rag.loaders.pdf.
- Duties: Defines PDFLoader and related helper logic.
- Depends on: Project modules: rastin_ai.rag.exceptions, and
  rastin_ai.rag.models.
"""

import hashlib
import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rastin_ai.rag.exceptions import DocumentLoadError, EmptyDocumentError
from rastin_ai.rag.models import Document

logger = logging.getLogger(__name__)


class PDFLoader:
    """Load text-based PDFs into page-level normalized documents."""

    def load(self, path: str | Path) -> list[Document]:
        normalized_path = self._validate_path(Path(path))

        try:
            reader = PdfReader(normalized_path)
        except PdfReadError as exc:
            msg = f"Could not read PDF document: {normalized_path}"
            raise DocumentLoadError(msg) from exc

        if reader.is_encrypted:
            msg = f"Encrypted PDF documents are not supported: {normalized_path}"
            raise DocumentLoadError(msg)

        source = str(normalized_path)
        metadata = self._normalize_metadata(reader.metadata)
        documents: list[Document] = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            page_metadata = {
                **metadata,
                "source": source,
                "filename": normalized_path.name,
                "file_type": "pdf",
                "page_number": page_number,
            }
            documents.append(
                Document(
                    id=self._document_id(source, page_number),
                    text=text,
                    source=source,
                    metadata=page_metadata,
                )
            )

        if not documents:
            msg = f"PDF document contains no extractable text: {normalized_path}"
            raise EmptyDocumentError(msg)

        logger.info(
            "Document loaded",
            extra={
                "source": source,
                "document_count": len(documents),
                "file_type": "pdf",
            },
        )
        return documents

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser().resolve()

        if not normalized_path.exists():
            msg = f"PDF document does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"PDF document input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() != ".pdf":
            msg = f"PDF document input must use a .pdf extension: {normalized_path}"
            raise DocumentLoadError(msg)

        return normalized_path

    @staticmethod
    def _document_id(source: str, page_number: int) -> str:
        digest = hashlib.sha256(
            f"{source}#{page_number}".encode(),
        ).hexdigest()
        return f"doc_{digest[:24]}"

    @staticmethod
    def _normalize_metadata(metadata: object) -> dict[str, str | None]:
        if metadata is None:
            return {}

        return {
            str(key).lstrip("/"): None if value is None else str(value)
            for key, value in dict(metadata).items()
        }
