"""File guide.

- Use: Provides one deterministic document-content extraction boundary for RAG.
- Usage: Import DefaultDocumentExtractor, ExtractionResult, and
  SharedDocumentLoader from rastin_ai.rag.extraction.
- Duties: Converts supported file formats from paths or bytes into RAG Document
  segments with source-location metadata and safe structured errors.
- Depends on: External packages: hashlib, json, pathlib, tempfile.
  Project modules: rastin_ai.rag.exceptions, rastin_ai.rag.models, and
  rastin_ai.skills.document_processing readers.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rastin_ai.rag.exceptions import DocumentLoadError
from rastin_ai.rag.models import Document, Metadata
from rastin_ai.skills.document_processing.tools.csv_reader import (
    CSVReaderError,
    CSVReaderInput,
    CSVReaderOutput,
    CSVReaderTool,
)
from rastin_ai.skills.document_processing.tools.docx_reader import (
    DOCXReaderError,
    DOCXReaderInput,
    DOCXReaderOutput,
    DOCXReaderTool,
)
from rastin_ai.skills.document_processing.tools.excel_sheet_reader import (
    ExcelSheetReaderError,
    ExcelSheetReaderInput,
    ExcelSheetReaderOutput,
    ExcelSheetReaderTool,
)
from rastin_ai.skills.document_processing.tools.excel_workbook_reader import (
    ExcelWorkbookReaderError,
    ExcelWorkbookReaderInput,
    ExcelWorkbookReaderTool,
)
from rastin_ai.skills.document_processing.tools.json_reader import (
    JSONReaderError,
    JSONReaderInput,
    JSONReaderOutput,
    JSONReaderTool,
)
from rastin_ai.skills.document_processing.tools.pdf_reader import (
    PDFReaderError,
    PDFReaderInput,
    PDFReaderOutput,
    PDFReaderTool,
)
from rastin_ai.skills.document_processing.tools.text_reader import (
    TextReaderError,
    TextReaderInput,
    TextReaderTool,
)

SUPPORTED_EXTRACTION_EXTENSIONS = frozenset(
    {".pdf", ".txt", ".md", ".csv", ".json", ".docx", ".xlsx"}
)
DEFAULT_LINE_GROUP_SIZE = 80
DEFAULT_ROW_GROUP_SIZE = 25
MAX_JSON_SEGMENT_CHARS = 2_000

UNSUPPORTED_EXTRACTION_FORMAT = "UNSUPPORTED_EXTRACTION_FORMAT"
TEXT_DECODE_FAILED = "TEXT_DECODE_FAILED"
MALFORMED_CSV = "MALFORMED_CSV"
MALFORMED_JSON = "MALFORMED_JSON"
MALFORMED_DOCX = "MALFORMED_DOCX"
MALFORMED_XLSX = "MALFORMED_XLSX"
ENCRYPTED_PDF = "ENCRYPTED_PDF"
EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
EXTRACTION_FAILED = "EXTRACTION_FAILED"


@dataclass(frozen=True)
class ExtractionResult:
    """Normalized extracted document segments ready for chunking."""

    documents: tuple[Document, ...]
    source: str
    format: str


class DocumentExtractor(Protocol):
    def extract_path(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        source: str | None = None,
    ) -> ExtractionResult:
        """Extract RAG documents from a local parser path."""

    def extract_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        source_id: str | None = None,
        source: str | None = None,
    ) -> ExtractionResult:
        """Extract RAG documents from in-memory file bytes."""


class DocumentExtractionError(DocumentLoadError):
    """Safe structured extraction failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message[:512]


class DefaultDocumentExtractor:
    """Extract all public upload formats through one deterministic boundary."""

    def extract_path(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        source: str | None = None,
    ) -> ExtractionResult:
        normalized_path = Path(path).expanduser()
        extension = normalized_path.suffix.lower()
        if extension not in SUPPORTED_EXTRACTION_EXTENSIONS:
            raise DocumentExtractionError(
                UNSUPPORTED_EXTRACTION_FORMAT,
                f"Extraction is not available for {extension or 'unknown'} files.",
            )

        source_name = source or str(normalized_path)
        base_metadata = _base_metadata(
            source=source_name,
            filename=normalized_path.name,
            extension=extension,
            source_id=source_id,
        )

        try:
            if extension in {".txt", ".md"}:
                documents = self._extract_text(normalized_path, base_metadata)
            elif extension == ".pdf":
                documents = self._extract_pdf(normalized_path, base_metadata)
            elif extension == ".csv":
                documents = self._extract_csv(normalized_path, base_metadata)
            elif extension == ".json":
                documents = self._extract_json(normalized_path, base_metadata)
            elif extension == ".docx":
                documents = self._extract_docx(normalized_path, base_metadata)
            else:
                documents = self._extract_xlsx(normalized_path, base_metadata)
        except DocumentExtractionError:
            raise
        except FileNotFoundError:
            raise
        except IsADirectoryError:
            raise
        except TextReaderError as exc:
            raise DocumentExtractionError(TEXT_DECODE_FAILED, str(exc)) from exc
        except CSVReaderError as exc:
            raise DocumentExtractionError(MALFORMED_CSV, str(exc)) from exc
        except JSONReaderError as exc:
            raise DocumentExtractionError(MALFORMED_JSON, str(exc)) from exc
        except DOCXReaderError as exc:
            raise DocumentExtractionError(MALFORMED_DOCX, str(exc)) from exc
        except ExcelSheetReaderError as exc:
            raise DocumentExtractionError(MALFORMED_XLSX, str(exc)) from exc
        except ExcelWorkbookReaderError as exc:
            raise DocumentExtractionError(MALFORMED_XLSX, str(exc)) from exc
        except PDFReaderError as exc:
            code = ENCRYPTED_PDF if "Encrypted PDF" in str(exc) else EXTRACTION_FAILED
            raise DocumentExtractionError(code, str(exc)) from exc
        except Exception as exc:
            raise DocumentExtractionError(
                EXTRACTION_FAILED,
                f"Could not extract document: {source_name}",
            ) from exc

        if not documents:
            raise DocumentExtractionError(
                EMPTY_DOCUMENT,
                f"Document contains no extractable text: {source_name}",
            )

        return ExtractionResult(
            documents=tuple(documents),
            source=source_name,
            format=extension.lstrip("."),
        )

    def extract_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        source_id: str | None = None,
        source: str | None = None,
    ) -> ExtractionResult:
        extension = Path(filename).suffix.lower()
        with tempfile.TemporaryDirectory(prefix="rastin_ai-extract-") as directory:
            path = Path(directory) / f"source{extension}"
            path.write_bytes(content)
            result = self.extract_path(
                path,
                source_id=source_id,
                source=source or filename,
            )
            return ExtractionResult(
                documents=tuple(
                    _with_metadata(
                        document,
                        {
                            "filename": filename,
                            "source": source or filename,
                        },
                    )
                    for document in result.documents
                ),
                source=source or filename,
                format=result.format,
            )

    def _extract_text(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        if path.suffix.lower() == ".txt":
            text = TextReaderTool().execute(TextReaderInput(path=path)).text
        else:
            text = _read_text(path)

        lines = text.splitlines()
        documents = []
        for group_index, start in enumerate(
            range(0, len(lines), DEFAULT_LINE_GROUP_SIZE)
        ):
            group_lines = lines[start : start + DEFAULT_LINE_GROUP_SIZE]
            segment_text = "\n".join(group_lines).strip()
            if not segment_text:
                continue
            line_start = start + 1
            line_end = start + len(group_lines)
            metadata = {
                **base_metadata,
                "location_type": "line_range",
                "line_start": line_start,
                "line_end": line_end,
            }
            documents.append(
                _document(
                    text=segment_text,
                    metadata=metadata,
                    location=f"lines:{line_start}-{line_end}",
                    group_index=group_index,
                )
            )
        return documents

    def _extract_pdf(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        output: PDFReaderOutput = PDFReaderTool().execute(PDFReaderInput(path=path))
        documents = []
        for page in output.pages:
            text = page.text.strip()
            if not text:
                continue
            metadata = {
                **base_metadata,
                **_prefixed_metadata("pdf", output.metadata),
                "location_type": "page",
                "page_number": page.page_number,
                "page_count": output.page_count,
            }
            documents.append(
                _document(
                    text=f"Page {page.page_number}\n{text}",
                    metadata=metadata,
                    location=f"page:{page.page_number}",
                    group_index=page.page_number - 1,
                )
            )
        return documents

    def _extract_csv(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        output: CSVReaderOutput = CSVReaderTool().execute(CSVReaderInput(path=path))
        rows = [tuple(cell for cell in row) for row in output.rows]
        if not _has_non_empty_rows(rows):
            return []

        columns = _columns_from_header(rows[0], output.column_count)
        data_rows = rows[1:] if len(rows) > 1 else rows
        row_offset = 2 if len(rows) > 1 else 1
        return _tabular_documents(
            rows=data_rows,
            columns=columns,
            base_metadata={
                **base_metadata,
                "delimiter": output.delimiter,
                "total_row_count": output.row_count,
                "column_count": output.column_count,
            },
            location_prefix="rows",
            row_offset=row_offset,
        )

    def _extract_json(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        output: JSONReaderOutput = JSONReaderTool().execute(JSONReaderInput(path=path))
        if output.data in ({}, []):
            return []

        return _json_documents(
            output.data,
            path="$",
            base_metadata={
                **base_metadata,
                "root_type": output.root_type,
                "item_count": output.item_count,
            },
        )

    def _extract_docx(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        output: DOCXReaderOutput = DOCXReaderTool().execute(DOCXReaderInput(path=path))
        documents = []
        for paragraph in output.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            metadata = {
                **base_metadata,
                **_prefixed_metadata("docx", output.metadata),
                "location_type": "paragraph",
                "paragraph_index": paragraph.index,
            }
            documents.append(
                _document(
                    text=f"Paragraph {paragraph.index}\n{text}",
                    metadata=metadata,
                    location=f"paragraph:{paragraph.index}",
                    group_index=len(documents),
                )
            )

        for table in output.tables:
            rows = [tuple(str(cell) for cell in row) for row in table.rows]
            columns = _columns_from_header(rows[0], len(rows[0]) if rows else 0)
            table_documents = _tabular_documents(
                rows=rows[1:] if len(rows) > 1 else rows,
                columns=columns,
                base_metadata={
                    **base_metadata,
                    **_prefixed_metadata("docx", output.metadata),
                    "location_type": "table_rows",
                    "table_index": table.index,
                },
                location_prefix=f"table:{table.index}:rows",
                row_offset=2 if len(rows) > 1 else 1,
                group_offset=len(documents),
            )
            documents.extend(table_documents)

        return documents

    def _extract_xlsx(
        self,
        path: Path,
        base_metadata: Metadata,
    ) -> list[Document]:
        workbook = ExcelWorkbookReaderTool().execute(
            ExcelWorkbookReaderInput(path=path)
        )
        documents = []
        for sheet in workbook.sheets:
            output: ExcelSheetReaderOutput = ExcelSheetReaderTool().execute(
                ExcelSheetReaderInput(path=path, sheet_name=sheet.name)
            )
            rows = [
                tuple("" if cell is None else str(cell) for cell in row)
                for row in output.rows
            ]
            if not _has_non_empty_rows(rows):
                continue

            columns = _columns_from_header(rows[0], output.column_count)
            documents.extend(
                _tabular_documents(
                    rows=rows[1:] if len(rows) > 1 else rows,
                    columns=columns,
                    base_metadata={
                        **base_metadata,
                        **_prefixed_metadata("xlsx", workbook.metadata),
                        "location_type": "sheet_rows",
                        "sheet_name": output.sheet_name,
                        "sheet_index": sheet.index,
                        "total_row_count": output.row_count,
                        "column_count": output.column_count,
                    },
                    location_prefix=f"sheet:{output.sheet_name}:rows",
                    row_offset=2 if len(rows) > 1 else 1,
                    group_offset=len(documents),
                )
            )

        return documents


class SharedDocumentLoader:
    """DocumentLoader adapter over the shared extractor."""

    def __init__(
        self,
        *,
        extractor: DocumentExtractor | None = None,
        source_id: str | None = None,
        source: str | None = None,
    ) -> None:
        self._extractor = extractor or DefaultDocumentExtractor()
        self._source_id = source_id
        self._source = source

    def load(self, path: str | Path) -> list[Document]:
        return list(
            self._extractor.extract_path(
                path,
                source_id=self._source_id,
                source=self._source,
            ).documents
        )


def _base_metadata(
    *,
    source: str,
    filename: str,
    extension: str,
    source_id: str | None,
) -> Metadata:
    metadata: Metadata = {
        "source": source,
        "filename": filename,
        "file_type": extension.lstrip("."),
    }
    if source_id is not None:
        metadata["document_id"] = source_id
    return metadata


def _read_text(path: Path, encoding: str = "utf-8") -> str:
    try:
        return path.read_text(encoding=encoding)
    except LookupError as exc:
        msg = f"Unknown text encoding: {encoding}"
        raise TextReaderError(msg) from exc
    except UnicodeDecodeError as exc:
        msg = f"Text file could not be decoded with encoding: {encoding}"
        raise TextReaderError(msg) from exc
    except OSError as exc:
        msg = f"Could not read text file: {path}"
        raise TextReaderError(msg) from exc


def _tabular_documents(
    *,
    rows: list[tuple[str, ...]],
    columns: list[str],
    base_metadata: Metadata,
    location_prefix: str,
    row_offset: int,
    group_offset: int = 0,
) -> list[Document]:
    documents = []
    non_empty_rows = [
        (row_index, row)
        for row_index, row in enumerate(rows, start=row_offset)
        if any(str(cell).strip() for cell in row)
    ]
    for group_index, start in enumerate(
        range(0, len(non_empty_rows), DEFAULT_ROW_GROUP_SIZE)
    ):
        group = non_empty_rows[start : start + DEFAULT_ROW_GROUP_SIZE]
        if not group:
            continue
        row_start = group[0][0]
        row_end = group[-1][0]
        metadata = {
            **base_metadata,
            "location_type": base_metadata.get("location_type", "row_range"),
            "row_start": row_start,
            "row_end": row_end,
            "columns": columns,
        }
        text = _serialize_rows(group, columns)
        documents.append(
            _document(
                text=text,
                metadata=metadata,
                location=f"{location_prefix}:{row_start}-{row_end}",
                group_index=group_offset + group_index,
            )
        )
    return documents


def _serialize_rows(rows: list[tuple[int, tuple[str, ...]]], columns: list[str]) -> str:
    parts = [f"Columns: {', '.join(columns)}"]
    for row_index, row in rows:
        values = []
        for column_index, column in enumerate(columns):
            value = row[column_index] if column_index < len(row) else ""
            values.append(f"{column}={value}")
        parts.append(f"Row {row_index}: " + " | ".join(values))
    return "\n".join(parts)


def _json_documents(
    value: object,
    *,
    path: str,
    base_metadata: Metadata,
    group_offset: int = 0,
) -> list[Document]:
    if _json_is_scalar(value):
        return [
            _json_document(
                value,
                path=path,
                base_metadata=base_metadata,
                group_index=group_offset,
            )
        ]

    if isinstance(value, dict):
        documents = []
        for key, child in value.items():
            child_path = f"{path}.{_json_path_key(key)}"
            documents.extend(
                _json_value_documents(
                    child,
                    path=child_path,
                    key=key,
                    base_metadata=base_metadata,
                    group_offset=group_offset + len(documents),
                )
            )
        return documents

    if isinstance(value, list):
        documents = []
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            documents.extend(
                _json_value_documents(
                    child,
                    path=child_path,
                    key=None,
                    base_metadata=base_metadata,
                    group_offset=group_offset + len(documents),
                )
            )
        return documents

    return []


def _json_value_documents(
    value: object,
    *,
    path: str,
    key: str | None,
    base_metadata: Metadata,
    group_offset: int,
) -> list[Document]:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    if len(serialized) <= MAX_JSON_SEGMENT_CHARS or _json_is_scalar(value):
        metadata = {**base_metadata, "location_type": "json_path", "json_path": path}
        if key is not None:
            metadata["json_key"] = key
        return [
            _document(
                text=f"JSON path {path}\n{serialized}",
                metadata=metadata,
                location=f"json:{path}",
                group_index=group_offset,
            )
        ]
    return _json_documents(
        value,
        path=path,
        base_metadata=base_metadata,
        group_offset=group_offset,
    )


def _json_document(
    value: object,
    *,
    path: str,
    base_metadata: Metadata,
    group_index: int,
) -> Document:
    metadata = {**base_metadata, "location_type": "json_path", "json_path": path}
    return _document(
        text=f"JSON path {path}\n{json.dumps(value, ensure_ascii=False)}",
        metadata=metadata,
        location=f"json:{path}",
        group_index=group_index,
    )


def _document(
    *,
    text: str,
    metadata: Metadata,
    location: str,
    group_index: int,
) -> Document:
    source = str(metadata["source"])
    document_id = _stable_document_id(source, location, group_index, text)
    return Document(
        id=document_id,
        text=text,
        source=source,
        metadata={**metadata, "source_location": location},
    )


def _stable_document_id(
    source: str,
    location: str,
    group_index: int,
    text: str,
) -> str:
    digest = hashlib.sha256(
        f"{source}:{location}:{group_index}:{text}".encode()
    ).hexdigest()
    return f"doc_{digest[:24]}"


def _columns_from_header(header: tuple[object, ...], column_count: int) -> list[str]:
    columns = []
    for index in range(max(column_count, len(header))):
        raw = header[index] if index < len(header) else ""
        value = str(raw).strip()
        columns.append(value or f"column_{index + 1}")
    return columns


def _has_non_empty_rows(rows: list[tuple[object, ...]]) -> bool:
    return any(any(str(cell).strip() for cell in row) for row in rows)


def _json_is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _json_path_key(key: str) -> str:
    if key.replace("_", "").isalnum() and not key[:1].isdigit():
        return key
    return json.dumps(key, ensure_ascii=False)


def _prefixed_metadata(
    prefix: str,
    metadata: dict[str, str | None],
) -> Metadata:
    return {
        f"{prefix}_{key}": value for key, value in metadata.items() if value is not None
    }


def _with_metadata(document: Document, metadata: Metadata) -> Document:
    merged = {**document.metadata, **metadata}
    return document.model_copy(update={"source": merged["source"], "metadata": merged})
