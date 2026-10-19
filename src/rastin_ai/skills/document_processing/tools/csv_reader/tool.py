"""File guide.

- Use: Implements the deterministic tool that reads CSV files.
- Usage: Import CSVReaderError, and CSVReaderTool from
  rastin_ai.skills.document_processing.tools.csv_reader.tool.
- Duties: Defines CSVReaderError, and CSVReaderTool and related helper logic.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.csv_reader.schemas, and
  rastin_ai.skills.tool.
"""

import csv
from pathlib import Path

from rastin_ai.skills.tool import BaseTool

from .schemas import CSVReaderInput, CSVReaderOutput


class CSVReaderError(ValueError):
    pass


class CSVReaderTool(BaseTool):
    _DETECTABLE_DELIMITERS = ",;\t|"

    def __init__(self) -> None:
        super().__init__(
            name="csv_reader",
            description="Read rows and string cells from a local .csv file.",
            capability="document.read.csv",
            args_schema=CSVReaderInput,
        )

    def execute(self, tool_input: CSVReaderInput) -> CSVReaderOutput:
        path = self._validate_path(tool_input.path)
        delimiter = tool_input.delimiter or self._detect_delimiter(
            path,
            tool_input.encoding,
        )

        rows: list[tuple[str, ...]] = []
        row_count = 0
        column_count = 0

        try:
            with path.open(newline="", encoding=tool_input.encoding) as csv_file:
                reader = csv.reader(csv_file, delimiter=delimiter, strict=True)
                for row in reader:
                    row_count += 1
                    column_count = max(column_count, len(row))

                    if tool_input.max_rows is None or len(rows) < tool_input.max_rows:
                        rows.append(tuple(row))
        except LookupError as exc:
            msg = f"Unknown CSV encoding: {tool_input.encoding}"
            raise CSVReaderError(msg) from exc
        except UnicodeDecodeError as exc:
            msg = f"CSV file could not be decoded with encoding: {tool_input.encoding}"
            raise CSVReaderError(msg) from exc
        except csv.Error as exc:
            msg = f"Could not read CSV file: {path}"
            raise CSVReaderError(msg) from exc

        return CSVReaderOutput(
            path=path,
            row_count=row_count,
            column_count=column_count,
            rows=tuple(rows),
            delimiter=delimiter,
            encoding=tool_input.encoding,
            truncated=tool_input.max_rows is not None and len(rows) < row_count,
        )

    def _validate_path(self, path: Path) -> Path:
        normalized_path = path.expanduser()

        if not normalized_path.exists():
            msg = f"CSV file does not exist: {normalized_path}"
            raise FileNotFoundError(msg)

        if not normalized_path.is_file():
            msg = f"CSV input is not a file: {normalized_path}"
            raise IsADirectoryError(msg)

        if normalized_path.suffix.lower() != ".csv":
            msg = f"CSV input must use a .csv extension: {normalized_path}"
            raise ValueError(msg)

        return normalized_path

    def _detect_delimiter(self, path: Path, encoding: str) -> str:
        try:
            with path.open(newline="", encoding=encoding) as csv_file:
                sample = csv_file.read(4096)
        except LookupError as exc:
            msg = f"Unknown CSV encoding: {encoding}"
            raise CSVReaderError(msg) from exc
        except UnicodeDecodeError as exc:
            msg = f"CSV file could not be decoded with encoding: {encoding}"
            raise CSVReaderError(msg) from exc

        try:
            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=self._DETECTABLE_DELIMITERS,
            )
        except csv.Error as exc:
            msg = (
                "Could not detect CSV delimiter. Provide one of ',', ';', tab, or '|'."
            )
            raise CSVReaderError(msg) from exc

        return dialect.delimiter
