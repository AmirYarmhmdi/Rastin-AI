"""File guide.

- Use: Contains unit tests for loaders behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.exceptions,
  rastin_ai.rag.loaders.pdf, and rastin_ai.rag.loaders.text.
"""

from pathlib import Path

import pytest

from rastin_ai.rag.exceptions import DocumentLoadError, EmptyDocumentError
from rastin_ai.rag.loaders.pdf import PDFLoader
from rastin_ai.rag.loaders.text import TextFileLoader


def write_text_pdf(
    path: Path,
    page_texts: tuple[str, ...],
    metadata: dict[str, str] | None = None,
) -> None:
    objects: list[bytes] = []
    page_numbers: list[int] = []

    def add_object(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    add_object(b"")
    add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for text in page_texts:
        page_number = len(objects) + 1
        content_number = len(objects) + 2
        page_numbers.append(page_number)
        add_object(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode()
        )
        content = f"BT\n/F1 12 Tf\n72 720 Td\n{pdf_string(text)} Tj\nET\n".encode()
        add_object(
            b"<< /Length "
            + str(len(content)).encode()
            + b" >>\nstream\n"
            + content
            + b"endstream"
        )

    kids = " ".join(f"{page_number} 0 R" for page_number in page_numbers)
    objects[1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>".encode()
    )

    info_number = None
    if metadata:
        entries = " ".join(
            f"/{key} {pdf_string(value)}" for key, value in metadata.items()
        )
        info_number = add_object(f"<< {entries} >>".encode())

    write_pdf_objects(path, objects, info_number)


def pdf_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})"


def write_pdf_objects(
    path: Path,
    objects: list[bytes],
    info_number: int | None,
) -> None:
    content = b"%PDF-1.4\n"
    offsets = []

    for object_number, object_content in enumerate(objects, start=1):
        offsets.append(len(content))
        content += f"{object_number} 0 obj\n".encode() + object_content + b"\nendobj\n"

    xref_start = len(content)
    content += f"xref\n0 {len(objects) + 1}\n".encode()
    content += b"0000000000 65535 f \n"

    for offset in offsets:
        content += f"{offset:010d} 00000 n \n".encode()

    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R"
    if info_number is not None:
        trailer += f" /Info {info_number} 0 R"
    trailer += f" >>\nstartxref\n{xref_start}\n%%EOF\n"
    path.write_bytes(content + trailer.encode())


def test_text_file_loader_loads_text_document(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Notes\nImportant text", encoding="utf-8")

    documents = TextFileLoader().load(path)

    assert len(documents) == 1
    assert documents[0].text == "# Notes\nImportant text"
    assert documents[0].metadata["filename"] == "notes.md"
    assert documents[0].metadata["file_type"] == "md"


def test_text_file_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.txt"):
        TextFileLoader().load(tmp_path / "missing.txt")


def test_text_file_loader_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "notes.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="Unsupported text document type"):
        TextFileLoader().load(path)


def test_text_file_loader_rejects_empty_document(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("  \n", encoding="utf-8")

    with pytest.raises(EmptyDocumentError, match="empty"):
        TextFileLoader().load(path)


def test_pdf_loader_preserves_page_numbers_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    write_text_pdf(path, ("First page", "Second page"), {"Title": "Report"})

    documents = PDFLoader().load(path)

    assert len(documents) == 2
    assert [document.metadata["page_number"] for document in documents] == [1, 2]
    assert documents[0].metadata["Title"] == "Report"
    assert documents[1].metadata["filename"] == "report.pdf"
    assert "Second page" in documents[1].text


def test_pdf_loader_rejects_malformed_pdf(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(DocumentLoadError, match="Could not read PDF document"):
        PDFLoader().load(path)
