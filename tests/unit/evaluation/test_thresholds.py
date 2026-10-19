"""File guide.

- Use: Tests centralized evaluation threshold behavior.
- Usage: Run with pytest tests/unit/evaluation/test_thresholds.py.
- Duties: Ensures pass/fail comparisons and settings mapping stay deterministic.
- Depends on: Project modules: rastin_ai.evaluation.thresholds.
"""

import pytest

from rastin_ai.core.config import Settings
from rastin_ai.evaluation.thresholds import (
    EvaluationThresholds,
    thresholds_from_settings,
)


def test_thresholds_use_greater_than_or_equal_for_quality_metrics() -> None:
    threshold = EvaluationThresholds(answer_relevancy=0.8).for_metric(
        "answer_relevancy"
    )

    assert threshold.passed(0.8) is True
    assert threshold.passed(0.79) is False
    assert threshold.comparison == "gte"


def test_thresholds_use_less_than_or_equal_for_hallucination() -> None:
    threshold = EvaluationThresholds(hallucination=0.2).for_metric("hallucination")

    assert threshold.passed(0.2) is True
    assert threshold.passed(0.21) is False
    assert threshold.comparison == "lte"


def test_thresholds_reject_unknown_metrics() -> None:
    with pytest.raises(ValueError, match="No evaluation threshold"):
        EvaluationThresholds().for_metric("unsupported")


def test_thresholds_can_be_built_from_settings(monkeypatch) -> None:
    monkeypatch.delenv("EVALUATION_ANSWER_RELEVANCY_THRESHOLD", raising=False)
    settings = Settings(
        _env_file=None,
        DEBUG=False,
        EVALUATION_ANSWER_RELEVANCY_THRESHOLD=0.81,
        EVALUATION_FAITHFULNESS_THRESHOLD=0.82,
        EVALUATION_CONTEXT_PRECISION_THRESHOLD=0.83,
        EVALUATION_CONTEXT_RECALL_THRESHOLD=0.84,
        EVALUATION_HALLUCINATION_THRESHOLD=0.18,
    )

    thresholds = thresholds_from_settings(settings)

    assert thresholds.answer_relevancy == 0.81
    assert thresholds.faithfulness == 0.82
    assert thresholds.context_precision == 0.83
    assert thresholds.context_recall == 0.84
    assert thresholds.hallucination == 0.18
