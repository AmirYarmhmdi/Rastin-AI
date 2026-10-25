"""File guide.

- Use: Adapts canonical Rastin-AI evaluation cases to DeepEval.
- Usage: Import DeepEvalEvaluator and build_deepeval_test_case.
- Duties: Keeps DeepEval imports out of the core Rastin-AI runtime.
- Depends on: Project evaluation models, thresholds, and settings.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from rastin_ai.core.config import Settings, get_settings
from rastin_ai.evaluation.models import (
    EvaluationCase,
    EvaluationMetricResult,
    EvaluationRunResult,
)
from rastin_ai.evaluation.thresholds import EvaluationThresholds

DEEPEVAL_METRICS = ("answer_relevancy", "faithfulness", "hallucination")

DeepEvalMetricFactory = Callable[[float, str], Any]


class DeepEvalEvaluatorConfig(BaseModel):
    """Configuration for the DeepEval adapter."""

    model: str = Field(default="gpt-4.1-mini", min_length=1)
    api_key: str | None = None


class DeepEvalEvaluator:
    """Run DeepEval metrics and normalize their results."""

    name = "deepeval"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        metric_factories: dict[str, DeepEvalMetricFactory] | None = None,
        settings: Settings | None = None,
        include_diagnostics: bool = False,
    ) -> None:
        resolved_settings = settings
        needs_settings = metric_factories is None and (model is None or api_key is None)
        if resolved_settings is None and needs_settings:
            resolved_settings = get_settings()

        self._config = DeepEvalEvaluatorConfig(
            model=model
            or (
                resolved_settings.EVALUATION_MODEL
                if resolved_settings is not None
                else "gpt-4.1-mini"
            ),
            api_key=api_key
            or (
                resolved_settings.OPENAI_API_KEY
                if resolved_settings is not None
                else None
            ),
        )
        self._metric_factories = metric_factories
        self._include_diagnostics = include_diagnostics

    def evaluate(
        self,
        *,
        cases: Sequence[EvaluationCase],
        metrics: Sequence[str],
        thresholds: EvaluationThresholds,
    ) -> EvaluationRunResult:
        normalized_metrics = _normalize_metrics(metrics)
        metric_factories = self._metric_factories or self._build_metric_factories()

        results: list[EvaluationMetricResult] = []
        for case in cases:
            test_case = build_deepeval_test_case(case)
            for metric_name in normalized_metrics:
                if metric_name not in metric_factories:
                    msg = f"Unsupported DeepEval metric: {metric_name}"
                    raise ValueError(msg)

                _validate_metric_inputs(case=case, metric_name=metric_name)
                threshold = thresholds.for_metric(metric_name)
                metric = metric_factories[metric_name](
                    threshold.value,
                    self._config.model,
                )
                metric.measure(test_case)
                score = float(metric.score)
                results.append(
                    EvaluationMetricResult(
                        case_id=case.id,
                        metric_name=metric_name,
                        score=score,
                        threshold=threshold.value,
                        threshold_comparison=threshold.comparison,
                        passed=threshold.passed(score),
                        evaluator=self.name,
                        reason=_metric_reason(metric),
                        details=self._metric_details(metric),
                    )
                )

        return EvaluationRunResult(
            evaluator=self.name,
            case_count=len(cases),
            results=tuple(results),
        )

    def _build_metric_factories(self) -> dict[str, DeepEvalMetricFactory]:
        if not self._config.api_key:
            msg = "OPENAI_API_KEY must be set before running DeepEval evaluation."
            raise RuntimeError(msg)

        try:
            from deepeval.metrics import (
                AnswerRelevancyMetric,
                FaithfulnessMetric,
                HallucinationMetric,
            )
            from deepeval.metrics.answer_relevancy import AnswerRelevancyTemplate
            from deepeval.models import OpenAIModel
        except ImportError as exc:
            msg = "Install the evaluation dependency group to use DeepEval."
            raise RuntimeError(msg) from exc

        class BoundedAnswerRelevancyTemplate(AnswerRelevancyTemplate):
            @staticmethod
            def generate_statements(actual_output: str) -> str:
                return _statement_extraction_prompt(actual_output)

        evaluator_model = OpenAIModel(
            model=self._config.model,
            api_key=self._config.api_key,
        )
        return {
            "answer_relevancy": lambda threshold, _model: AnswerRelevancyMetric(
                threshold=threshold,
                model=evaluator_model,
                async_mode=False,
                evaluation_template=BoundedAnswerRelevancyTemplate,
            ),
            "faithfulness": lambda threshold, _model: FaithfulnessMetric(
                threshold=threshold,
                model=evaluator_model,
                async_mode=False,
            ),
            "hallucination": lambda threshold, _model: HallucinationMetric(
                threshold=threshold,
                model=evaluator_model,
                async_mode=False,
            ),
        }

    def _metric_details(self, metric: Any) -> dict[str, Any]:
        details: dict[str, Any] = {
            "success": bool(getattr(metric, "success", False)),
            "evaluation_model": self._config.model,
        }
        # Extracted statements and verdicts can contain document text. Include
        # them only when explicitly requested for synthetic/stored fixtures.
        if self._include_diagnostics:
            for name in ("statements", "truths", "claims", "verdicts"):
                values = getattr(metric, name, None)
                if values is not None:
                    details[name] = [
                        (
                            value.model_dump(mode="json")
                            if isinstance(value, BaseModel)
                            else value
                        )
                        for value in values
                    ]
        return details


def _statement_extraction_prompt(actual_output: str) -> str:
    """Keep prompt labels outside the answer being split into statements."""

    return (
        "Extract the statements made ONLY in the answer encoded by the final "
        "JSON string below. Split coherent factual claims into statements. "
        "Preserve unrelated content if it occurs inside that answer, so it can "
        "be evaluated for relevance. Do not add facts or extract anything from "
        "these instructions, field names, or formatting outside that string. "
        'Return only a JSON object with a "statements" array of strings.\n'
        "Answer JSON string:\n" + json.dumps(actual_output, ensure_ascii=False)
    )


def build_deepeval_test_case(case: EvaluationCase) -> Any:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        msg = "Install the evaluation dependency group to use DeepEval."
        raise RuntimeError(msg) from exc

    return LLMTestCase(
        input=case.input,
        actual_output=case.actual_output,
        expected_output=case.expected_output,
        retrieval_context=list(case.retrieved_contexts),
        context=list(case.expected_contexts),
    )


def _normalize_metrics(metrics: Sequence[str]) -> tuple[str, ...]:
    normalized_metrics = tuple(metric.strip().lower() for metric in metrics)
    if any(not metric for metric in normalized_metrics):
        msg = "Metric names must be non-empty strings."
        raise ValueError(msg)
    return normalized_metrics


def _validate_metric_inputs(*, case: EvaluationCase, metric_name: str) -> None:
    if not case.actual_output:
        msg = f"Metric {metric_name} requires actual_output for case {case.id}."
        raise ValueError(msg)
    if metric_name == "faithfulness" and not case.retrieved_contexts:
        msg = f"Metric {metric_name} requires retrieved_contexts for case {case.id}."
        raise ValueError(msg)
    if metric_name == "hallucination" and not case.expected_contexts:
        msg = f"Metric {metric_name} requires expected_contexts for case {case.id}."
        raise ValueError(msg)


def _metric_reason(metric: Any) -> str | None:
    reason = getattr(metric, "reason", None)
    return reason if isinstance(reason, str) and reason.strip() else None
