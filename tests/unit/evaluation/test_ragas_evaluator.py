"""File guide.

- Use: Tests Ragas adapter behavior without importing or calling Ragas.
- Usage: Run with pytest tests/unit/evaluation/test_ragas_evaluator.py.
- Duties: Verifies metric input validation and normalized result generation.
- Depends on: Project modules: rastin_ai.evaluation.ragas_evaluator.
"""

import pytest

from rastin_ai.evaluation.models import EvaluationCase
from rastin_ai.evaluation.ragas_evaluator import RagasEvaluator
from rastin_ai.evaluation.thresholds import EvaluationThresholds


class FakeRagasScore:
    value = 0.88
    reason = "grounded"


class FakeRagasMetric:
    def score(self, **_kwargs):
        return FakeRagasScore()


def test_ragas_evaluator_normalizes_metric_results() -> None:
    evaluator = RagasEvaluator(
        metric_factories={
            "faithfulness": lambda _llm, _embeddings: FakeRagasMetric(),
        }
    )
    case = EvaluationCase(
        id="case-1",
        input="What is ContextBuilder?",
        actual_output="It formats retrieved chunks.",
        retrieved_contexts=("ContextBuilder formats retrieved chunks.",),
    )

    result = evaluator.evaluate(
        cases=(case,),
        metrics=["faithfulness"],
        thresholds=EvaluationThresholds(faithfulness=0.8),
    )

    assert result.passed is True
    metric_result = result.results[0]
    assert metric_result.evaluator == "ragas"
    assert metric_result.metric_name == "faithfulness"
    assert metric_result.score == 0.88
    assert metric_result.threshold == 0.8
    assert metric_result.reason == "grounded"


def test_ragas_evaluator_requires_retrieved_contexts_for_faithfulness() -> None:
    evaluator = RagasEvaluator(
        metric_factories={
            "faithfulness": lambda _llm, _embeddings: FakeRagasMetric(),
        }
    )
    case = EvaluationCase(
        id="case-1",
        input="What is ContextBuilder?",
        actual_output="It formats retrieved chunks.",
    )

    with pytest.raises(ValueError, match="requires retrieved_contexts"):
        evaluator.evaluate(
            cases=(case,),
            metrics=["faithfulness"],
            thresholds=EvaluationThresholds(),
        )
