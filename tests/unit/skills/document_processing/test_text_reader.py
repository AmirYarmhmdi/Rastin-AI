"""File guide.

- Use: Contains unit tests for text reader behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.skills.document_processing,
  rastin_ai.skills.document_processing.tools.text_reader, and
  rastin_ai.skills.tool.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.skills.document_processing.tools.text_reader import (
    TextReaderError,
    TextReaderInput,
    TextReaderOutput,
    TextReaderTool,
)
from rastin_ai.skills.tool import BaseTool


def write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding)


def test_text_reader_tool_exposes_contract_metadata() -> None:
    tool = TextReaderTool()

    assert isinstance(tool, BaseTool)
    assert tool.name == "text_reader"
    assert tool.description
    assert tool.capability == "document.read.text"


def test_text_reader_reads_normal_utf8_text_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    write_text(path, "hello\nworld\n")

    result = TextReaderTool().execute(TextReaderInput(path=path))

    assert isinstance(result, TextReaderOutput)
    assert result.path == path
    assert result.text == "hello\nworld\n"
    assert result.encoding == "utf-8"
    assert result.char_count == len("hello\nworld\n")
    assert result.line_count == 2
    assert result.truncated is False


def test_text_reader_reads_empty_text_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    write_text(path, "")

    result = TextReaderTool().execute(TextReaderInput(path=path))

    assert result.text == ""
    assert result.char_count == 0
    assert result.line_count == 0


@pytest.mark.parametrize(
    ("content", "expected_line_count"),
    [
        ("one line", 1),
        ("one line\n", 1),
        ("one\ntwo\nthree", 3),
        ("one\n\nthree\n", 3),
    ],
)
def test_text_reader_line_count_policy(
    tmp_path: Path,
    content: str,
    expected_line_count: int,
) -> None:
    path = tmp_path / "lines.txt"
    write_text(path, content)

    result = TextReaderTool().execute(TextReaderInput(path=path))

    assert result.line_count == expected_line_count


def test_text_reader_preserves_unicode_whitespace_and_blank_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unicode.txt"
    content = "  سلام\n\n\tindented café\ntrailing spaces   "
    write_text(path, content)

    result = TextReaderTool().execute(TextReaderInput(path=path))

    assert result.text == content
    assert result.text.startswith("  ")
    assert result.text.endswith("   ")
    assert "\n\n" in result.text
    assert "\tindented" in result.text


def test_text_reader_uses_explicit_valid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "latin.txt"
    write_text(path, "André", encoding="latin-1")

    result = TextReaderTool().execute(TextReaderInput(path=path, encoding="latin-1"))

    assert result.text == "André"
    assert result.encoding == "latin-1"


def test_text_reader_rejects_unknown_encoding(tmp_path: Path) -> None:
    path = tmp_path / "unknown-encoding.txt"
    write_text(path, "hello")

    with pytest.raises(TextReaderError, match="Unknown text encoding"):
        TextReaderTool().execute(TextReaderInput(path=path, encoding="not-a-codec"))


def test_text_reader_reports_decoding_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad-encoding.txt"
    path.write_bytes("André".encode("latin-1"))

    with pytest.raises(TextReaderError, match="could not be decoded"):
        TextReaderTool().execute(TextReaderInput(path=path))


def test_text_reader_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match="missing.txt"):
        TextReaderTool().execute(TextReaderInput(path=path))


def test_text_reader_rejects_directory_input(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError, match="not a file"):
        TextReaderTool().execute(TextReaderInput(path=tmp_path))


def test_text_reader_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    write_text(path, "# markdown")

    with pytest.raises(ValueError, match=".txt extension"):
        TextReaderTool().execute(TextReaderInput(path=path))


def test_text_reader_accepts_uppercase_txt_extension(tmp_path: Path) -> None:
    path = tmp_path / "NOTES.TXT"
    write_text(path, "uppercase")

    result = TextReaderTool().execute(TextReaderInput(path=path))

    assert result.text == "uppercase"


def test_text_reader_validates_empty_encoding() -> None:
    with pytest.raises(ValidationError):
        TextReaderInput(path=Path("notes.txt"), encoding="")


def test_text_reader_validates_max_chars() -> None:
    with pytest.raises(ValidationError):
        TextReaderInput(path=Path("notes.txt"), max_chars=0)


def test_text_reader_max_chars_non_truncated_file(tmp_path: Path) -> None:
    path = tmp_path / "short.txt"
    write_text(path, "short")

    result = TextReaderTool().execute(TextReaderInput(path=path, max_chars=10))

    assert result.text == "short"
    assert result.char_count == 5
    assert result.line_count == 1
    assert result.truncated is False


def test_text_reader_max_chars_truncated_file(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    content = "first line\nsecond line\n"
    write_text(path, content)

    result = TextReaderTool().execute(TextReaderInput(path=path, max_chars=5))

    assert result.text == "first"
    assert result.char_count == len(content)
    assert result.line_count == 2
    assert result.truncated is True


def test_text_reader_max_chars_exact_boundary(tmp_path: Path) -> None:
    path = tmp_path / "boundary.txt"
    write_text(path, "abc")

    result = TextReaderTool().execute(TextReaderInput(path=path, max_chars=3))

    assert result.text == "abc"
    assert result.char_count == 3
    assert result.truncated is False


def test_text_reader_output_serializes_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "serializable.txt"
    write_text(path, "hello")

    result = TextReaderTool().execute(TextReaderInput(path=path))
    dumped = result.model_dump()
    encoded = json.loads(result.model_dump_json())

    assert dumped["text"] == "hello"
    assert encoded["path"] == str(path)
    assert encoded["text"] == "hello"


def test_text_reader_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "repeatable.txt"
    write_text(path, "same text")
    tool = TextReaderTool()
    tool_input = TextReaderInput(path=path)

    assert tool.execute(tool_input) == tool.execute(tool_input)


def test_document_processing_skill_exposes_text_reader_tool() -> None:
    skill = DocumentProcessingSkill()

    assert "document.read.text" in skill.executable_capabilities
    assert "document.read.json" in skill.executable_capabilities
    assert "document.read.docx" in skill.executable_capabilities
    assert skill.get_tool("text_reader") is not None
