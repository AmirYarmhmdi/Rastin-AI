"""File guide.

- Use: Tests DeepEval adapter behavior without importing or calling DeepEval.
- Usage: Run with pytest tests/unit/evaluation/test_deepeval_evaluator.py.
- Duties: Verifies canonical case conversion path and normalized metric results.
- Depends on: Project modules: rastin_ai.evaluation.deepeval_evaluator.
"""

import json

import pytest
from pydantic import BaseModel

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


@pytest.mark.parametrize("include_diagnostics", [False, True])
def test_deepeval_diagnostics_preserve_failed_verdicts_without_leaking_by_default(
    monkeypatch, include_diagnostics
) -> None:
    class Verdict(BaseModel):
        verdict: str
        reason: str | None = None

    class DiagnosticMetric(FakeDeepEvalMetric):
        score = 2 / 3
        success = False
        reason = "An unrelated statement was found."
        statements = ["Claim one.", "Claim two.", "JSON:"]
        verdicts = [
            Verdict(verdict="yes"),
            Verdict(verdict="yes"),
            Verdict(verdict="no", reason="Unrelated label."),
        ]

    monkeypatch.setattr(
        deepeval_evaluator,
        "build_deepeval_test_case",
        lambda case: {"input": case.input},
    )
    evaluator = DeepEvalEvaluator(
        model="configured-judge",
        include_diagnostics=include_diagnostics,
        metric_factories={
            "answer_relevancy": lambda _threshold, _model: DiagnosticMetric(),
        },
    )
    result = evaluator.evaluate(
        cases=(EvaluationCase(id="case-1", input="Question?", actual_output="Answer"),),
        metrics=["answer_relevancy"],
        thresholds=EvaluationThresholds(),
    )

    assert result.passed is False
    assert result.results[0].score == 2 / 3
    details = result.results[0].details
    assert details["evaluation_model"] == "configured-judge"
    if include_diagnostics:
        assert details["statements"] == DiagnosticMetric.statements
        assert details["verdicts"][2] == {
            "verdict": "no",
            "reason": "Unrelated label.",
        }
        assert json.loads(result.model_dump_json())["results"][0]["details"] == details
    else:
        assert "statements" not in details
        assert "verdicts" not in details


def test_deepeval_factories_use_configured_credentials_and_bound_answer(monkeypatch):
    metrics = pytest.importorskip("deepeval.metrics")
    models = pytest.importorskip("deepeval.models")
    model_options = {}
    sentinel_model = object()

    def create_model(**kwargs):
        model_options.update(kwargs)
        return sentinel_model

    monkeypatch.setattr(models, "OpenAIModel", create_model)
    for metric_name in (
        "AnswerRelevancyMetric",
        "FaithfulnessMetric",
        "HallucinationMetric",
    ):
        monkeypatch.setattr(metrics, metric_name, lambda **kwargs: kwargs)

    evaluator = DeepEvalEvaluator(model="configured-judge", api_key="test-only-key")
    factories = evaluator._build_metric_factories()
    assert model_options == {"model": "configured-judge", "api_key": "test-only-key"}
    for factory in factories.values():
        options = factory(0.7, "configured-judge")
        assert options["model"] is sentinel_model
        assert options["threshold"] == 0.7
        assert options["async_mode"] is False

    template = factories["answer_relevancy"](0.7, "configured-judge")[
        "evaluation_template"
    ]
    # Prompt delimiters/labels inside an answer must remain part of its data.
    # The prompt itself must not append a JSON: label for the judge to extract.
    answer = 'ContextBuilder formats chunks.\nJSON:\n"Answer JSON string:"'
    prompt = template.generate_statements(answer)
    assert json.loads(prompt.splitlines()[-1]) == answer
    assert prompt.endswith(json.dumps(answer, ensure_ascii=False))
