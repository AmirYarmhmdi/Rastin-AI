"""File guide.

- Use: Tests DeepEval adapter behavior without importing or calling DeepEval.
- Usage: Run with pytest tests/unit/evaluation/test_deepeval_evaluator.py.
- Duties: Verifies canonical case conversion path and normalized metric results.
- Depends on: Project modules: rastin_ai.evaluation.deepeval_evaluator.
"""

import pytest

from rastin_ai.evaluation import deepeval_evaluator
from rastin_ai.evaluation.deepeval_evaluator import DeepEvalEvaluator
from rastin_ai.evaluation.models import EvaluationCase
from rastin_ai.evaluation.thresholds import EvaluationThresholds


class FakeDeepEvalMetric:
    score = 0.12
    reason = "low hallucination"
    success = True

    def measure(self, test_case) -> None:
        assert test_case["input"] == "Question?"


def test_deepeval_evaluator_normalizes_metric_results(monkeypatch) -> None:
    monkeypatch.setattr(
        deepeval_evaluator,
        "build_deepeval_test_case",
        lambda case: {"input": case.input},
    )
    evaluator = DeepEvalEvaluator(
        metric_factories={
            "hallucination": lambda _threshold, _model: FakeDeepEvalMetric(),
        }
    )
    case = EvaluationCase(
        id="case-1",
        input="Question?",
        actual_output="Grounded answer",
        expected_contexts=("Grounded answer",),
    )

    result = evaluator.evaluate(
        cases=(case,),
        metrics=["hallucination"],
        thresholds=EvaluationThresholds(hallucination=0.2),
    )

    assert result.passed is True
    metric_result = result.results[0]
    assert metric_result.evaluator == "deepeval"
    assert metric_result.metric_name == "hallucination"
    assert metric_result.threshold_comparison == "lte"
    assert metric_result.score == 0.12
    assert metric_result.reason == "low hallucination"


def test_deepeval_evaluator_requires_actual_output(monkeypatch) -> None:
    monkeypatch.setattr(
        deepeval_evaluator,
        "build_deepeval_test_case",
        lambda case: {"input": case.input},
    )
    evaluator = DeepEvalEvaluator(
        metric_factories={
            "answer_relevancy": lambda _threshold, _model: FakeDeepEvalMetric(),
        }
    )
    case = EvaluationCase(id="case-1", input="Question?")

    with pytest.raises(ValueError, match="requires actual_output"):
        evaluator.evaluate(
            cases=(case,),
            metrics=["answer_relevancy"],
            thresholds=EvaluationThresholds(),
        )
