"""File guide.

- Use: Loads Rastin-AI canonical JSONL evaluation datasets.
- Usage: Import load_evaluation_dataset.
- Duties: Handles file I/O, Pydantic validation, and optional tag filtering.
- Depends on: External package json and project evaluation models.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from rastin_ai.evaluation.models import EvaluationCase


class EvaluationDatasetError(ValueError):
    """Raised when an evaluation dataset cannot be read or validated."""


def load_evaluation_dataset(
    path: str | Path,
    *,
    tags: Iterable[str] | None = None,
) -> tuple[EvaluationCase, ...]:
    """Load and validate a JSONL evaluation dataset."""

    dataset_path = Path(path)
    if not dataset_path.exists():
        msg = f"Evaluation dataset does not exist: {dataset_path}"
        raise EvaluationDatasetError(msg)
    if not dataset_path.is_file():
        msg = f"Evaluation dataset path is not a file: {dataset_path}"
        raise EvaluationDatasetError(msg)

    requested_tags = {tag.strip() for tag in tags or () if tag.strip()}
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()

    for line_number, line in enumerate(dataset_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue

        raw_record = _parse_json_line(
            line=line, path=dataset_path, line_number=line_number
        )
        case = _validate_case(
            raw_record=raw_record,
            path=dataset_path,
            line_number=line_number,
        )
        if case.id in seen_ids:
            msg = (
                f"Duplicate evaluation case id {case.id!r} in {dataset_path} "
                f"at line {line_number}."
            )
            raise EvaluationDatasetError(msg)
        seen_ids.add(case.id)

        if requested_tags and requested_tags.isdisjoint(case.tags):
            continue

        cases.append(case)

    if not cases:
        tag_suffix = f" for tags {sorted(requested_tags)}" if requested_tags else ""
        msg = f"Evaluation dataset contains no cases{tag_suffix}: {dataset_path}"
        raise EvaluationDatasetError(msg)

    return tuple(cases)


def _parse_json_line(
    *,
    line: str,
    path: Path,
    line_number: int,
) -> dict[str, Any]:
    try:
        parsed_line = json.loads(line)
    except json.JSONDecodeError as exc:
        msg = (
            f"Invalid JSON in evaluation dataset {path} at line {line_number}: "
            f"{exc.msg}"
        )
        raise EvaluationDatasetError(msg) from exc

    if not isinstance(parsed_line, dict):
        msg = (
            f"Invalid evaluation dataset {path} at line {line_number}: "
            "each JSONL record must be an object."
        )
        raise EvaluationDatasetError(msg)

    return parsed_line


def _validate_case(
    *,
    raw_record: dict[str, Any],
    path: Path,
    line_number: int,
) -> EvaluationCase:
    try:
        return EvaluationCase.model_validate(raw_record)
    except ValidationError as exc:
        msg = (
            f"Invalid evaluation case in {path} at line {line_number}: "
            f"{exc.errors()[0]['msg']}"
        )
        raise EvaluationDatasetError(msg) from exc
