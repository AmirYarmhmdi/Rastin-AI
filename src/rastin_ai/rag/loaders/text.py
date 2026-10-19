"""File guide.

- Use: Loads plain text files into RAG Document objects.
- Usage: Import TextFileLoader from rastin_ai.rag.loaders.text.
- Duties: Defines TextFileLoader and related helper logic.
- Depends on: Project modules: rastin_ai.rag.exceptions, and
  rastin_ai.rag.models.
"""

import hashlib
import logging
from pathlib import Path

from rastin_ai.rag.exceptions import DocumentLoadError, EmptyDocumentError
from rastin_ai.rag.models import Document

logger = logging.getLogger(__name__)

SUPPORTED_TEXT_EXTENSIONS = frozenset({".txt", ".md"})


class TextFileLoader:
    """Load plain text-like files into one normalized document."""

    def __init__(self, *, encoding: str = "utf-8") -> None:
        self._encoding = encoding

    def load(self, path: str | Path) -> list[Document]:
        normalized_path = self._validate_path(Path(path))

        try:
            text = normalized_path.read_text(encoding=self._encoding)
        except LookupError as exc:
            msg = f"Unknown text encoding: {self._encoding}"
            raise DocumentLoadError(msg) from exc
        except UnicodeDecodeError as exc:
            msg = f"Text file could not be decoded with encoding: {self._encoding}"
            raise DocumentLoadError(msg) from exc
        except OSError as exc:
            msg = f"Could not read text file: {normalized_path}"
            raise DocumentLoadError(msg) from exc

        if not text.strip():
            msg = f"Text document is empty: {normalized_path}"
            raise EmptyDocumentError(msg)

        source = str(normalized_path)
        document = Document(
            id=self._document_id(source),
            text=text,
            source=source,
            metadata={
                "source": source,
                "filename": normalized_path.name,
                "file_type": normalized_path.suffix.lower().lstrip("."),
            },
        )
        logger.info(
            "Document loaded",
            extra={
                "source": source,
                "document_id": document.id,
                "file_type": document.metadata["file_type"],
            },
        )
        return [document]

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser().resolve()

        if not normalized_path.exists():
            msg = f"Text document does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"Text document input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
            msg = f"Unsupported text document type: {normalized_path.suffix}"
            raise DocumentLoadError(msg)

        return normalized_path

    @staticmethod
    def _document_id(source: str) -> str:
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return f"doc_{digest[:24]}"
