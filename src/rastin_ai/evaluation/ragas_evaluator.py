"""File guide.

- Use: Adapts canonical Rastin-AI evaluation cases to Ragas.
- Usage: Import RagasEvaluator for RAG-oriented quality evaluation.
- Duties: Keeps Ragas imports and result shapes isolated from core runtime code.
- Depends on: Project evaluation models, thresholds, and settings.
"""

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

RAGAS_METRICS = (
    "answer_relevancy",
    "faithfulness",
    "context_precision",
    "context_recall",
)

MetricFactory = Callable[[Any | None, Any | None], Any]


class RagasEvaluatorConfig(BaseModel):
    """Configuration for the Ragas adapter."""

    model: str = Field(default="gpt-4.1-mini", min_length=1)
    embedding_model: str = Field(default="text-embedding-3-small", min_length=1)
    api_key: str | None = None


class RagasEvaluator:
    """Run Ragas metrics and normalize their results."""

    name = "ragas"

    def __init__(
        self,
        *,
        model: str | None = None,
        embedding_model: str | None = None,
        api_key: str | None = None,
        llm: Any | None = None,
        embeddings: Any | None = None,
        metric_factories: dict[str, MetricFactory] | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings
        needs_settings = metric_factories is None and (
            model is None or embedding_model is None or api_key is None
        )
        if resolved_settings is None and needs_settings:
            resolved_settings = get_settings()

        self._config = RagasEvaluatorConfig(
            model=model
            or (
                resolved_settings.EVALUATION_MODEL
                if resolved_settings is not None
                else "gpt-4.1-mini"
            ),
            embedding_model=embedding_model
            or (
                resolved_settings.EVALUATION_EMBEDDING_MODEL
                if resolved_settings is not None
                else "text-embedding-3-small"
            ),
            api_key=api_key
            or (
                resolved_settings.OPENAI_API_KEY
                if resolved_settings is not None
                else None
            ),
        )
        self._llm = llm
        self._embeddings = embeddings
        self._metric_factories = metric_factories

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
            for metric_name in normalized_metrics:
                if metric_name not in metric_factories:
                    msg = f"Unsupported Ragas metric: {metric_name}"
                    raise ValueError(msg)

                _validate_metric_inputs(case=case, metric_name=metric_name)
                threshold = thresholds.for_metric(metric_name)
                metric = metric_factories[metric_name](self._llm, self._embeddings)
                score_payload = _score_metric(metric=metric, case=case)
                score = _extract_score(score_payload)
                results.append(
                    EvaluationMetricResult(
                        case_id=case.id,
                        metric_name=metric_name,
                        score=score,
                        threshold=threshold.value,
                        threshold_comparison=threshold.comparison,
                        passed=threshold.passed(score),
                        evaluator=self.name,
                        reason=_extract_reason(score_payload),
                        details=_extract_details(score_payload),
                    )
                )

        return EvaluationRunResult(
            evaluator=self.name,
            case_count=len(cases),
            results=tuple(results),
        )

    def _build_metric_factories(self) -> dict[str, MetricFactory]:
        if self._llm is None or self._embeddings is None:
            self._llm, self._embeddings = self._build_ragas_clients()

        try:
            from ragas.metrics.collections import (
                AnswerRelevancy,
                ContextPrecision,
                ContextRecall,
                Faithfulness,
            )
        except ImportError as exc:
            msg = "Install the evaluation dependency group to use Ragas."
            raise RuntimeError(msg) from exc

        return {
            "answer_relevancy": lambda llm, embeddings: AnswerRelevancy(
                llm=llm,
                embeddings=embeddings,
            ),
            "faithfulness": lambda llm, _embeddings: Faithfulness(llm=llm),
            "context_precision": lambda llm, _embeddings: ContextPrecision(llm=llm),
            "context_recall": lambda llm, _embeddings: ContextRecall(llm=llm),
        }

    def _build_ragas_clients(self) -> tuple[Any, Any]:
        if not self._config.api_key:
            msg = "OPENAI_API_KEY must be set before running Ragas evaluation."
            raise RuntimeError(msg)

        try:
            from openai import AsyncOpenAI
            from ragas.embeddings.base import embedding_factory
            from ragas.llms import llm_factory
        except ImportError as exc:
            msg = "Install the evaluation dependency group to use Ragas."
            raise RuntimeError(msg) from exc

        client = AsyncOpenAI(api_key=self._config.api_key)
        llm = llm_factory(model=self._config.model, client=client)
        embeddings = embedding_factory(
            "openai",
            model=self._config.embedding_model,
            client=client,
        )
        return llm, embeddings


def _normalize_metrics(metrics: Sequence[str]) -> tuple[str, ...]:
    normalized_metrics = tuple(metric.strip().lower() for metric in metrics)
    if any(not metric for metric in normalized_metrics):
        msg = "Metric names must be non-empty strings."
        raise ValueError(msg)
    return normalized_metrics


def _validate_metric_inputs(*, case: EvaluationCase, metric_name: str) -> None:
    if metric_name in {"answer_relevancy", "faithfulness"} and not case.actual_output:
        msg = f"Metric {metric_name} requires actual_output for case {case.id}."
        raise ValueError(msg)
    if metric_name in {"faithfulness", "context_precision", "context_recall"}:
        if not case.retrieved_contexts:
            msg = (
                f"Metric {metric_name} requires retrieved_contexts for case {case.id}."
            )
            raise ValueError(msg)
    if metric_name in {"context_precision", "context_recall"}:
        if not case.expected_output:
            msg = f"Metric {metric_name} requires expected_output for case {case.id}."
            raise ValueError(msg)


def _score_metric(*, metric: Any, case: EvaluationCase) -> Any:
    return metric.score(
        user_input=case.input,
        response=case.actual_output,
        retrieved_contexts=list(case.retrieved_contexts),
        reference=case.expected_output,
    )


def _extract_score(score_payload: Any) -> float:
    raw_score = getattr(score_payload, "value", score_payload)
    return float(raw_score)


def _extract_reason(score_payload: Any) -> str | None:
    reason = getattr(score_payload, "reason", None)
    return reason if isinstance(reason, str) and reason.strip() else None


def _extract_details(score_payload: Any) -> dict[str, Any]:
    if isinstance(score_payload, BaseModel):
        return score_payload.model_dump(mode="json")
    if isinstance(score_payload, dict):
        return dict(score_payload)
    return {}
