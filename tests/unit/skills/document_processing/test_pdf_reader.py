"""File guide.

- Use: Contains unit tests for pdf reader behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.skills.document_processing, and
  rastin_ai.skills.document_processing.tools.pdf_reader.
"""

from pathlib import Path

import pytest

from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.skills.document_processing.tools.pdf_reader import (
    PDFReaderError,
    PDFReaderInput,
    PDFReaderTool,
)


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


def test_pdf_reader_tool_exposes_metadata() -> None:
    tool = PDFReaderTool()

    assert tool.name == "pdf_reader"
    assert tool.capability == "document.read.pdf"
    assert "text" in tool.description


def test_pdf_reader_reads_one_page_text_pdf(tmp_path: Path) -> None:
    path = tmp_path / "one-page.pdf"
    write_text_pdf(path, ("Hello from page one",), {"Title": "One Page"})

    result = PDFReaderTool().execute(PDFReaderInput(path=path))

    assert result.path == path
    assert result.page_count == 1
    assert result.pages[0].page_number == 1
    assert "Hello from page one" in result.pages[0].text
    assert result.metadata["Title"] == "One Page"


def test_pdf_reader_reads_multi_page_text_pdf(tmp_path: Path) -> None:
    path = tmp_path / "multi-page.pdf"
    write_text_pdf(path, ("First page text", "Second page text"))

    result = PDFReaderTool().execute(PDFReaderInput(path=path))

    assert result.page_count == 2
    assert [page.page_number for page in result.pages] == [1, 2]
    assert "First page text" in result.pages[0].text
    assert "Second page text" in result.pages[1].text


def test_pdf_reader_uses_one_based_page_numbers(tmp_path: Path) -> None:
    path = tmp_path / "numbered.pdf"
    write_text_pdf(path, ("alpha", "beta", "gamma"))

    result = PDFReaderTool().execute(PDFReaderInput(path=path))

    assert tuple(page.page_number for page in result.pages) == (1, 2, 3)


def test_pdf_reader_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="missing.pdf"):
        PDFReaderTool().execute(PDFReaderInput(path=path))


def test_pdf_reader_rejects_non_pdf_input(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("plain text", encoding="utf-8")

    with pytest.raises(ValueError, match=".pdf extension"):
        PDFReaderTool().execute(PDFReaderInput(path=path))


def test_pdf_reader_rejects_malformed_pdf(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a real pdf")

    with pytest.raises(PDFReaderError, match="Could not read PDF file"):
        PDFReaderTool().execute(PDFReaderInput(path=path))


def test_document_processing_skill_exposes_pdf_reader_tool() -> None:
    skill = DocumentProcessingSkill()

    assert "document.read.pdf" in skill.executable_capabilities
    assert skill.get_tool("pdf_reader") is not None
    assert "document.read.excel" not in skill.executable_capabilities
    assert "document.read.csv" in skill.executable_capabilities
    assert "document.read.text" in skill.executable_capabilities
    assert "document.read.json" in skill.executable_capabilities
    assert "document.read.docx" in skill.executable_capabilities
