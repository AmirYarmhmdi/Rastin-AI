"""File guide.

- Use: Contains unit tests for json reader behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.skills.document_processing,
  rastin_ai.skills.document_processing.tools.json_reader, and
  rastin_ai.skills.tool.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.skills.document_processing.tools.json_reader import (
    JSONReaderError,
    JSONReaderInput,
    JSONReaderOutput,
    JSONReaderTool,
)
from rastin_ai.skills.tool import BaseTool


def write_json_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding)


def write_json_value(path: Path, value: object, encoding: str = "utf-8") -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding=encoding)


def test_json_reader_tool_exposes_contract_metadata() -> None:
    tool = JSONReaderTool()

    assert isinstance(tool, BaseTool)
    assert tool.name == "json_reader"
    assert tool.description
    assert tool.capability == "document.read.json"


@pytest.mark.parametrize(
    ("value", "root_type", "item_count"),
    [
        ({}, "object", 0),
        ({"name": "Rastin-AI"}, "object", 1),
        ({"a": 1, "b": {"c": True}, "d": None}, "object", 3),
        ([], "array", 0),
        ([1, 2, 3], "array", 3),
        (["x", 1, 2.5, True, False, None], "array", 6),
        ([[1], [2, 3]], "array", 2),
        ([{"name": "Alice"}, {"name": "Bob"}], "array", 2),
        ("Rastin-AI", "string", None),
        (42, "number", None),
        (12.5, "number", None),
        (True, "boolean", None),
        (False, "boolean", None),
        (None, "null", None),
    ],
)
def test_json_reader_supports_all_json_root_types(
    tmp_path: Path,
    value: object,
    root_type: str,
    item_count: int | None,
) -> None:
    path = tmp_path / "document.json"
    write_json_value(path, value)

    result = JSONReaderTool().execute(JSONReaderInput(path=path))

    assert isinstance(result, JSONReaderOutput)
    assert result.path == path
    assert result.data == value
    assert result.root_type == root_type
    assert result.item_count == item_count
    assert result.encoding == "utf-8"


def test_json_reader_preserves_json_value_types_and_nesting(tmp_path: Path) -> None:
    path = tmp_path / "types.json"
    value = {
        "string": "text",
        "integer": 42,
        "float": 3.14,
        "true": True,
        "false": False,
        "null": None,
        "numeric_string": "42",
        "date_string": "2026-08-10",
        "array": [1, "2", False, None],
        "object": {"nested": {"active": True}},
    }
    write_json_value(path, value)

    result = JSONReaderTool().execute(JSONReaderInput(path=path))

    assert result.data["string"] == "text"
    assert isinstance(result.data["integer"], int)
    assert isinstance(result.data["float"], float)
    assert isinstance(result.data["true"], bool)
    assert isinstance(result.data["false"], bool)
    assert result.data["null"] is None
    assert result.data["numeric_string"] == "42"
    assert isinstance(result.data["numeric_string"], str)
    assert result.data["date_string"] == "2026-08-10"
    assert isinstance(result.data["date_string"], str)
    assert result.data["array"] == [1, "2", False, None]
    assert result.data["object"] == {"nested": {"active": True}}


def test_json_reader_preserves_array_order(tmp_path: Path) -> None:
    path = tmp_path / "ordered.json"
    write_json_value(path, ["first", "second", "third"])

    result = JSONReaderTool().execute(JSONReaderInput(path=path))

    assert result.data == ["first", "second", "third"]


def test_json_reader_handles_unicode_keys_and_values(tmp_path: Path) -> None:
    path = tmp_path / "unicode.json"
    value = {"نام": "Rastin-AI", "city": "München", "emoji": "plain text"}
    write_json_value(path, value)

    result = JSONReaderTool().execute(JSONReaderInput(path=path))

    assert result.data == value


def test_json_reader_uses_explicit_valid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "latin.json"
    write_json_text(path, '{"name": "André"}', encoding="latin-1")

    result = JSONReaderTool().execute(JSONReaderInput(path=path, encoding="latin-1"))

    assert result.data == {"name": "André"}
    assert result.encoding == "latin-1"


def test_json_reader_rejects_unknown_encoding(tmp_path: Path) -> None:
    path = tmp_path / "unknown-encoding.json"
    write_json_value(path, {"ok": True})

    with pytest.raises(JSONReaderError, match="Unknown JSON encoding"):
        JSONReaderTool().execute(JSONReaderInput(path=path, encoding="not-a-codec"))


def test_json_reader_reports_decoding_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad-encoding.json"
    path.write_bytes('{"name": "André"}'.encode("latin-1"))

    with pytest.raises(JSONReaderError, match="could not be decoded"):
        JSONReaderTool().execute(JSONReaderInput(path=path))


def test_json_reader_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="missing.json"):
        JSONReaderTool().execute(JSONReaderInput(path=path))


def test_json_reader_rejects_directory_input(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError, match="not a file"):
        JSONReaderTool().execute(JSONReaderInput(path=tmp_path))


def test_json_reader_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "document.jsonl"
    write_json_text(path, '{"ok": true}\n')

    with pytest.raises(ValueError, match=".json extension"):
        JSONReaderTool().execute(JSONReaderInput(path=path))


def test_json_reader_accepts_uppercase_json_extension(tmp_path: Path) -> None:
    path = tmp_path / "DOCUMENT.JSON"
    write_json_value(path, {"ok": True})

    result = JSONReaderTool().execute(JSONReaderInput(path=path))

    assert result.data == {"ok": True}


@pytest.mark.parametrize(
    "content",
    [
        "",
        "   \n\t",
        '{"missing": ',
        '{"valid": true} trailing',
    ],
)
def test_json_reader_reports_malformed_json(tmp_path: Path, content: str) -> None:
    path = tmp_path / "malformed.json"
    write_json_text(path, content)

    with pytest.raises(JSONReaderError, match="Malformed JSON file"):
        JSONReaderTool().execute(JSONReaderInput(path=path))


def test_json_reader_validates_empty_encoding() -> None:
    with pytest.raises(ValidationError):
        JSONReaderInput(path=Path("document.json"), encoding="")


def test_json_reader_output_serializes_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "serializable.json"
    write_json_value(path, {"items": [1, True, None, {"name": "Rastin-AI"}]})

    result = JSONReaderTool().execute(JSONReaderInput(path=path))
    dumped = result.model_dump()
    encoded = json.loads(result.model_dump_json())

    assert dumped["data"] == {"items": [1, True, None, {"name": "Rastin-AI"}]}
    assert encoded["path"] == str(path)
    assert encoded["data"] == {"items": [1, True, None, {"name": "Rastin-AI"}]}
    assert "JSONDecoder" not in str(encoded)


def test_json_reader_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "repeatable.json"
    write_json_value(path, {"items": [1, 2, 3]})
    tool = JSONReaderTool()
    tool_input = JSONReaderInput(path=path)

    assert tool.execute(tool_input) == tool.execute(tool_input)


def test_document_processing_skill_exposes_json_reader_tool() -> None:
    skill = DocumentProcessingSkill()

    assert "document.read.json" in skill.executable_capabilities
    assert "document.read.docx" in skill.executable_capabilities
    assert skill.get_tool("json_reader") is not None
