"""File guide.

- Use: Tests live evaluation orchestration without external services.
- Usage: Run with pytest tests/unit/evaluation/test_live.py.
- Duties: Verifies runtime-generated cases, reporting, and opt-in guard behavior.
- Depends on: Project modules: rastin_ai.evaluation.live.
"""

import asyncio
import inspect
from collections.abc import Sequence

import pytest

import rastin_ai.agent.response_generator as response_generator_module
import rastin_ai.evaluation.live as live_module
from rastin_ai.evaluation.live import (
    LiveEvaluationError,
    LiveEvaluationRunner,
    RuntimeCaseResult,
    _document_fixtures,
    _require_live_evaluation_enabled,
)
from rastin_ai.evaluation.models import (
    EvaluationCase,
    EvaluationMetricResult,
    EvaluationRunResult,
)
from rastin_ai.evaluation.thresholds import EvaluationThresholds


class FakeRuntimeExecutor:
    def __init__(self) -> None:
        self.calls: list[EvaluationCase] = []

    async def execute(self, case: EvaluationCase) -> RuntimeCaseResult:
        self.calls.append(case)
        return RuntimeCaseResult(
            case_id=case.id,
            actual_output="Runtime answer from indexed context.",
            retrieved_contexts=(
                "Full retrieved context that should stay out of reports.",
            ),
            model_name="runtime-model",
            token_usage={"input_tokens": 12, "output_tokens": 6},
            latency_ms=25.4,
            workflow_id="workflow-1",
            trace_id="trace-1",
            document_ids=("document-1",),
        )


class FakeEvaluator:
    name = "fake"

    def __init__(self) -> None:
        self.cases: Sequence[EvaluationCase] = ()

    def evaluate(
        self,
        *,
        cases: Sequence[EvaluationCase],
        metrics: Sequence[str],
        thresholds: EvaluationThresholds,
    ) -> EvaluationRunResult:
        self.cases = cases
        results = []
        for case in cases:
            for metric in metrics:
                threshold = thresholds.for_metric(metric)
                results.append(
                    EvaluationMetricResult(
                        case_id=case.id,
                        metric_name=metric,
                        score=0.92,
                        threshold=threshold.value,
                        threshold_comparison=threshold.comparison,
                        passed=threshold.passed(0.92),
                        evaluator=self.name,
                    )
                )
        return EvaluationRunResult(
            evaluator=self.name,
            case_count=len(cases),
            results=tuple(results),
        )


def test_live_runner_builds_generated_case_and_redacted_report() -> None:
    runtime = FakeRuntimeExecutor()
    evaluator = FakeEvaluator()
    runner = LiveEvaluationRunner(
        runtime_executor=runtime,
        evaluator=evaluator,
        thresholds=EvaluationThresholds(),
    )
    source_case = EvaluationCase(
        id="live-case",
        input="Question?",
        expected_output="Reference answer.",
        expected_contexts=("Reference context.",),
        metadata={
            "live": {
                "safe_report_text": True,
                "documents": [
                    {
                        "filename": "fixture.txt",
                        "content": "Reference context.",
                    }
                ],
            }
        },
        tags=("live",),
    )

    report = asyncio.run(
        runner.run_cases(
            (source_case,),
            dataset="live.jsonl",
            metrics=("answer_relevancy", "faithfulness"),
        )
    )

    generated_case = evaluator.cases[0]
    assert generated_case.actual_output == "Runtime answer from indexed context."
    assert generated_case.retrieved_contexts == (
        "Full retrieved context that should stay out of reports.",
    )
    assert source_case.actual_output is None
    assert source_case.retrieved_contexts == ()
    assert report.passed is True
    assert report.cases[0].retrieved_context_count == 1
    assert report.cases[0].retrieved_context_chars == len(
        "Full retrieved context that should stay out of reports."
    )
    assert "Full retrieved context" not in report.model_dump_json()
    assert report.cases[0].report_text_included is False
    assert report.cases[0].report_text_policy == "omitted_by_default"


def test_live_runner_reports_runtime_errors_without_evaluating() -> None:
    class FailingRuntimeExecutor:
        async def execute(self, case: EvaluationCase) -> RuntimeCaseResult:
            return RuntimeCaseResult(
                case_id=case.id,
                actual_output=None,
                retrieved_contexts=(),
                model_name=None,
                token_usage=None,
                latency_ms=3.0,
                workflow_id=None,
                trace_id=None,
                error="runtime unavailable",
            )

    evaluator = FakeEvaluator()
    runner = LiveEvaluationRunner(
        runtime_executor=FailingRuntimeExecutor(),
        evaluator=evaluator,
        thresholds=EvaluationThresholds(),
    )

    report = asyncio.run(
        runner.run_cases(
            (EvaluationCase(id="case-1", input="Question?"),),
            dataset="live.jsonl",
            metrics=("answer_relevancy",),
        )
    )

    assert report.passed is False
    assert report.evaluated_case_count == 0
    assert report.cases[0].error == "runtime unavailable"
    assert evaluator.cases == ()


def test_live_runner_reports_evaluator_errors_per_case() -> None:
    class ExplodingEvaluator:
        name = "exploding"

        def evaluate(
            self,
            *,
            cases: Sequence[EvaluationCase],
            metrics: Sequence[str],
            thresholds: EvaluationThresholds,
        ) -> EvaluationRunResult:
            _ = cases
            _ = metrics
            _ = thresholds
            raise RuntimeError("metric provider unavailable")

    runner = LiveEvaluationRunner(
        runtime_executor=FakeRuntimeExecutor(),
        evaluator=ExplodingEvaluator(),
        thresholds=EvaluationThresholds(),
    )

    report = asyncio.run(
        runner.run_cases(
            (EvaluationCase(id="case-1", input="Question?"),),
            dataset="live.jsonl",
            metrics=("answer_relevancy",),
        )
    )

    assert report.passed is False
    assert report.cases[0].error == "metric provider unavailable"
    assert report.cases[0].metrics == ()


def test_live_report_can_include_safe_fixture_text_with_bounded_context() -> None:
    runtime = FakeRuntimeExecutor()
    evaluator = FakeEvaluator()
    runner = LiveEvaluationRunner(
        runtime_executor=runtime,
        evaluator=evaluator,
        thresholds=EvaluationThresholds(),
    )
    source_case = EvaluationCase(
        id="safe-live-case",
        input="Question?",
        expected_output="Reference answer.",
        expected_contexts=("Reference context.",),
        metadata={
            "live": {
                "safe_report_text": True,
                "documents": [
                    {
                        "filename": "fixture.txt",
                        "content": "Reference context.",
                    }
                ],
            }
        },
        tags=("live",),
    )

    report = asyncio.run(
        runner.run_cases(
            (source_case,),
            dataset="live.jsonl",
            metrics=("answer_relevancy",),
            include_report_text=True,
            context_preview_chars=12,
        )
    )

    case_report = report.cases[0]
    assert report.contains_safe_test_text is True
    assert case_report.report_text_included is True
    assert case_report.report_text_policy == "safe_test_only"
    assert case_report.input == "Question?"
    assert case_report.expected_output == "Reference answer."
    assert case_report.actual_output == "Runtime answer from indexed context."
    assert case_report.retrieved_context_preview == ("Full retriev...<truncated>",)
    assert case_report.retrieved_context_preview_chars == 12


def test_live_report_omits_text_when_case_is_not_marked_safe() -> None:
    runner = LiveEvaluationRunner(
        runtime_executor=FakeRuntimeExecutor(),
        evaluator=FakeEvaluator(),
        thresholds=EvaluationThresholds(),
    )

    report = asyncio.run(
        runner.run_cases(
            (EvaluationCase(id="case-1", input="Question?"),),
            dataset="live.jsonl",
            metrics=("answer_relevancy",),
            include_report_text=True,
        )
    )

    case_report = report.cases[0]
    assert report.contains_safe_test_text is False
    assert case_report.report_text_included is False
    assert case_report.report_text_policy == "omitted_case_not_marked_safe"
    assert case_report.input is None
    assert case_report.actual_output is None
    assert case_report.retrieved_context_preview == ()


def test_live_environment_guard_requires_explicit_flag(monkeypatch) -> None:
    monkeypatch.delenv("RUN_LIVE_EVALUATION", raising=False)

    with pytest.raises(LiveEvaluationError, match="RUN_LIVE_EVALUATION=1"):
        _require_live_evaluation_enabled()


def test_live_document_fixtures_parse_from_case_metadata() -> None:
    case = EvaluationCase(
        id="case-1",
        input="Question?",
        metadata={
            "live": {
                "documents": [
                    {
                        "filename": "fixture.md",
                        "content_type": "text/markdown",
                        "content": "# Fixture",
                    }
                ]
            }
        },
    )

    fixtures = _document_fixtures(case)

    assert fixtures[0].filename == "fixture.md"
    assert fixtures[0].content == b"# Fixture"
    assert fixtures[0].content_type == "text/markdown"


def test_live_eval_does_not_hard_code_smoke_case_answer() -> None:
    live_source = inspect.getsource(live_module)
    response_source = inspect.getsource(response_generator_module)
    combined_source = f"{live_source}\n{response_source}"

    assert "live-rag-smoke-rastin_ai-context" not in combined_source
    assert (
        "Rastin-AI uses ContextBuilder to format retrieved chunks into "
        "source-aware context for response generation."
    ) not in combined_source
