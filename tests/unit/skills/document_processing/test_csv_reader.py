"""File guide.

- Use: Contains unit tests for csv reader behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.skills.document_processing, and
  rastin_ai.skills.document_processing.tools.csv_reader.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.skills.document_processing.tools.csv_reader import (
    CSVReaderError,
    CSVReaderInput,
    CSVReaderTool,
)


def write_csv(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding, newline="")


def test_csv_reader_tool_exposes_metadata() -> None:
    tool = CSVReaderTool()

    assert tool.name == "csv_reader"
    assert "rows" in tool.description
    assert tool.capability == "document.read.csv"


def test_csv_reader_reads_comma_separated_csv(tmp_path: Path) -> None:
    path = tmp_path / "people.csv"
    write_csv(path, "name,age\nAlice,32\nBob,41\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.path == path
    assert result.rows == (("name", "age"), ("Alice", "32"), ("Bob", "41"))
    assert result.row_count == 3
    assert result.column_count == 2
    assert result.delimiter == ","
    assert result.encoding == "utf-8"
    assert result.truncated is False


def test_csv_reader_preserves_row_and_cell_order(tmp_path: Path) -> None:
    path = tmp_path / "ordered.csv"
    write_csv(path, "a,b,c\n1,2,3\nx,y,z\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.rows[0] == ("a", "b", "c")
    assert result.rows[1] == ("1", "2", "3")
    assert result.rows[2] == ("x", "y", "z")


def test_csv_reader_preserves_empty_cells(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    write_csv(path, "a,,c\n,second,\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.rows == (("a", "", "c"), ("", "second", ""))


def test_csv_reader_handles_quoted_fields_with_delimiters(tmp_path: Path) -> None:
    path = tmp_path / "quoted.csv"
    write_csv(path, 'name,note\nAlice,"hello, friend"\nBob,"quote ""inside"""\n')

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.rows == (
        ("name", "note"),
        ("Alice", "hello, friend"),
        ("Bob", 'quote "inside"'),
    )


def test_csv_reader_uses_explicit_comma_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "comma.csv"
    write_csv(path, "a,b\n1,2\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.delimiter == ","
    assert result.rows == (("a", "b"), ("1", "2"))


def test_csv_reader_uses_explicit_semicolon_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "semicolon.csv"
    write_csv(path, "a;b\n1;2\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=";"))

    assert result.delimiter == ";"
    assert result.rows == (("a", "b"), ("1", "2"))


def test_csv_reader_uses_explicit_tab_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "tab.csv"
    write_csv(path, "a\tb\n1\t2\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter="\t"))

    assert result.delimiter == "\t"
    assert result.rows == (("a", "b"), ("1", "2"))


def test_csv_reader_detects_common_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "detected.csv"
    write_csv(path, "a|b|c\n1|2|3\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path))

    assert result.delimiter == "|"
    assert result.rows == (("a", "b", "c"), ("1", "2", "3"))


def test_csv_reader_reports_delimiter_detection_failure(tmp_path: Path) -> None:
    path = tmp_path / "unknown.csv"
    write_csv(path, "single column\nanother row\n")

    with pytest.raises(CSVReaderError, match="Could not detect CSV delimiter"):
        CSVReaderTool().execute(CSVReaderInput(path=path))


def test_csv_reader_defaults_to_utf8(tmp_path: Path) -> None:
    path = tmp_path / "utf8.csv"
    write_csv(path, "name\nAmir\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.encoding == "utf-8"
    assert result.rows == (("name",), ("Amir",))


def test_csv_reader_uses_explicit_encoding(tmp_path: Path) -> None:
    path = tmp_path / "latin.csv"
    write_csv(path, "name\nAndré\n", encoding="latin-1")

    result = CSVReaderTool().execute(
        CSVReaderInput(path=path, delimiter=",", encoding="latin-1")
    )

    assert result.encoding == "latin-1"
    assert result.rows == (("name",), ("André",))


def test_csv_reader_rejects_unknown_encoding(tmp_path: Path) -> None:
    path = tmp_path / "unknown-encoding.csv"
    write_csv(path, "a,b\n1,2\n")

    with pytest.raises(CSVReaderError, match="Unknown CSV encoding"):
        CSVReaderTool().execute(
            CSVReaderInput(path=path, delimiter=",", encoding="not-a-codec")
        )


def test_csv_reader_reports_decoding_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad-encoding.csv"
    path.write_bytes("name\nAndré\n".encode("latin-1"))

    with pytest.raises(CSVReaderError, match="could not be decoded"):
        CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))


def test_csv_reader_preserves_irregular_row_widths(tmp_path: Path) -> None:
    path = tmp_path / "irregular.csv"
    write_csv(path, "a,b,c\n1,2\nx,y,z,w\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.rows == (("a", "b", "c"), ("1", "2"), ("x", "y", "z", "w"))
    assert result.column_count == 4


def test_csv_reader_preserves_first_row_as_ordinary_row(tmp_path: Path) -> None:
    path = tmp_path / "headers.csv"
    write_csv(path, "name,age\nAlice,32\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))

    assert result.rows[0] == ("name", "age")
    assert isinstance(result.rows[0], tuple)


def test_csv_reader_limits_rows_and_reports_total_row_count(tmp_path: Path) -> None:
    path = tmp_path / "limited.csv"
    write_csv(path, "a,b\n1,2\n3,4\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, max_rows=2))

    assert result.row_count == 3
    assert result.rows == (("a", "b"), ("1", "2"))
    assert result.truncated is True


def test_csv_reader_max_rows_without_truncation(tmp_path: Path) -> None:
    path = tmp_path / "not-truncated.csv"
    write_csv(path, "a,b\n1,2\n")

    result = CSVReaderTool().execute(CSVReaderInput(path=path, max_rows=5))

    assert result.row_count == 2
    assert result.rows == (("a", "b"), ("1", "2"))
    assert result.truncated is False


def test_csv_reader_validates_delimiter() -> None:
    with pytest.raises(ValidationError):
        CSVReaderInput(path=Path("data.csv"), delimiter="::")


def test_csv_reader_validates_encoding() -> None:
    with pytest.raises(ValidationError):
        CSVReaderInput(path=Path("data.csv"), encoding="")


def test_csv_reader_validates_max_rows() -> None:
    with pytest.raises(ValidationError):
        CSVReaderInput(path=Path("data.csv"), max_rows=0)


def test_csv_reader_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="missing.csv"):
        CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))


def test_csv_reader_rejects_directory_input(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError, match="not a file"):
        CSVReaderTool().execute(CSVReaderInput(path=tmp_path, delimiter=","))


def test_csv_reader_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    write_csv(path, "a,b\n1,2\n")

    with pytest.raises(ValueError, match=".csv extension"):
        CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))


def test_csv_reader_reports_malformed_csv(tmp_path: Path) -> None:
    path = tmp_path / "malformed.csv"
    write_csv(path, 'name,note\nAlice,"unterminated\n')

    with pytest.raises(CSVReaderError, match="Could not read CSV file"):
        CSVReaderTool().execute(CSVReaderInput(path=path, delimiter=","))


def test_document_processing_skill_exposes_csv_reader_tool() -> None:
    skill = DocumentProcessingSkill()

    assert "document.read.pdf" in skill.executable_capabilities
    assert "document.read.excel.workbook" in skill.executable_capabilities
    assert "document.read.excel.sheet" in skill.executable_capabilities
    assert "document.read.csv" in skill.executable_capabilities
    assert "document.read.text" in skill.executable_capabilities
    assert "document.read.json" in skill.executable_capabilities
    assert "document.read.docx" in skill.executable_capabilities
    assert skill.get_tool("csv_reader") is not None
