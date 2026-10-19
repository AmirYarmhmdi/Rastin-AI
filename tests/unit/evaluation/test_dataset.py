"""File guide.

- Use: Tests evaluation dataset loading and validation behavior.
- Usage: Run with pytest tests/unit/evaluation/test_dataset.py.
- Duties: Verifies JSONL parsing, tag filtering, and actionable failures.
- Depends on: Project modules: rastin_ai.evaluation.dataset.
"""

import pytest

from rastin_ai.evaluation.dataset import (
    EvaluationDatasetError,
    load_evaluation_dataset,
)


def test_load_evaluation_dataset_accepts_valid_jsonl(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":"Question?",'
        '"expected_output":"Answer","actual_output":"Answer",'
        '"expected_contexts":["gold"],"retrieved_contexts":["gold"],'
        '"tags":["smoke","rag"],"metadata":{"area":"rag"}}\n'
    )

    cases = load_evaluation_dataset(dataset_path)

    assert len(cases) == 1
    assert cases[0].id == "case-1"
    assert cases[0].tags == ("smoke", "rag")
    assert cases[0].metadata["area"] == "rag"


def test_load_evaluation_dataset_filters_by_tags(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":"A","tags":["rag"]}\n'
        '{"id":"case-2","input":"B","tags":["agent"]}\n'
    )

    cases = load_evaluation_dataset(dataset_path, tags=["agent"])

    assert [case.id for case in cases] == ["case-2"]


def test_load_evaluation_dataset_rejects_missing_required_field(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text('{"id":"case-1"}\n')

    with pytest.raises(EvaluationDatasetError, match="line 1"):
        load_evaluation_dataset(dataset_path)


def test_load_evaluation_dataset_rejects_invalid_json(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text('{"id":')

    with pytest.raises(EvaluationDatasetError, match="Invalid JSON"):
        load_evaluation_dataset(dataset_path)


def test_load_evaluation_dataset_rejects_duplicate_ids(tmp_path) -> None:
    dataset_path = tmp_path / "cases.jsonl"
    dataset_path.write_text(
        '{"id":"case-1","input":"A"}\n' '{"id":"case-1","input":"B"}\n'
    )

    with pytest.raises(EvaluationDatasetError, match="Duplicate evaluation case id"):
        load_evaluation_dataset(dataset_path)
