"""File guide.

- Use: Tests evaluation runner orchestration.
- Usage: Run with pytest tests/unit/evaluation/test_runner.py.
- Duties: Verifies normalized aggregate results through a fake evaluator.
- Depends on: Project modules: rastin_ai.evaluation.
"""

from collections.abc import Sequence

import pytest

from rastin_ai.evaluation.models import (
    EvaluationCase,
    EvaluationMetricResult,
    EvaluationRunResult,
)
from rastin_ai.evaluation.runner import EvaluationRunner
from rastin_ai.evaluation.thresholds import EvaluationThresholds


class FakeEvaluator:
    name = "fake"

    def evaluate(
        self,
        *,
        cases: Sequence[EvaluationCase],
        metrics: Sequence[str],
        thresholds: EvaluationThresholds,
    ) -> EvaluationRunResult:
        metric_name = metrics[0]
        threshold = thresholds.for_metric(metric_name)
        score = 0.91
        return EvaluationRunResult(
            evaluator=self.name,
            case_count=len(cases),
            results=(
                EvaluationMetricResult(
                    case_id=cases[0].id,
                    metric_name=metric_name,
                    score=score,
                    threshold=threshold.value,
                    threshold_comparison=threshold.comparison,
                    passed=threshold.passed(score),
                    evaluator=self.name,
                ),
            ),
        )


def test_runner_returns_normalized_aggregate_result() -> None:
    runner = EvaluationRunner(evaluator=FakeEvaluator())
    cases = (EvaluationCase(id="case-1", input="Question"),)

    result = runner.run_cases(cases, metrics=["answer_relevancy"])

    assert result.evaluator == "fake"
    assert result.case_count == 1
    assert result.passed is True
    assert result.passed_count == 1
    assert result.failed_count == 0
    assert result.average_scores == {"answer_relevancy": 0.91}


def test_runner_rejects_empty_cases() -> None:
    runner = EvaluationRunner(evaluator=FakeEvaluator())

    with pytest.raises(ValueError, match="at least one case"):
        runner.run_cases((), metrics=["answer_relevancy"])


def test_runner_rejects_empty_metrics() -> None:
    runner = EvaluationRunner(evaluator=FakeEvaluator())
    cases = (EvaluationCase(id="case-1", input="Question"),)

    with pytest.raises(ValueError, match="at least one metric"):
        runner.run_cases(cases, metrics=[])
