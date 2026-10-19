"""File guide.

- Use: Defines framework-independent evaluation dataset and result models.
- Usage: Import EvaluationCase, EvaluationMetricResult, and EvaluationRunResult.
- Duties: Keeps evaluation data owned by Rastin-AI instead of Ragas/DeepEval.
- Depends on: External packages only: pydantic and typing.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

Metadata = dict[str, Any]

MetricComparison = Literal["gte", "lte"]


class EvaluationCase(BaseModel):
    """Canonical Rastin-AI evaluation case.

    The model is intentionally framework-neutral so the same dataset can feed RAG,
    agent, tool-calling, and future analytical evaluators.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StrictStr = Field(min_length=1)
    input: StrictStr = Field(min_length=1)
    expected_output: StrictStr | None = None
    actual_output: StrictStr | None = None
    expected_contexts: tuple[StrictStr, ...] = ()
    retrieved_contexts: tuple[StrictStr, ...] = ()
    metadata: Metadata = Field(default_factory=dict)
    tags: tuple[StrictStr, ...] = ()
    expected_tool_name: StrictStr | None = None
    expected_tool_arguments: Metadata | None = None
    expected_behavior: StrictStr | None = None

    @field_validator(
        "id",
        "input",
        "expected_output",
        "actual_output",
        "expected_tool_name",
        "expected_behavior",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped_value = value.strip()
        if not stripped_value:
            msg = "Evaluation text fields must be non-empty when provided."
            raise ValueError(msg)

        return stripped_value

    @field_validator("expected_contexts", "retrieved_contexts", "tags", mode="before")
    @classmethod
    def normalize_string_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list | tuple):
            msg = "Evaluation list fields must be arrays of non-empty strings."
            raise ValueError(msg)

        normalized_values: list[str] = []
        for item in value:
            if not isinstance(item, str):
                msg = "Evaluation list fields must contain only strings."
                raise ValueError(msg)
            stripped_item = item.strip()
            if not stripped_item:
                msg = "Evaluation list fields must not contain empty strings."
                raise ValueError(msg)
            normalized_values.append(stripped_item)

        return tuple(normalized_values)


class MetricThreshold(BaseModel):
    """Threshold rule for a normalized metric score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_name: StrictStr = Field(min_length=1)
    value: float = Field(ge=0.0, le=1.0)
    comparison: MetricComparison = "gte"

    def passed(self, score: float) -> bool:
        if self.comparison == "gte":
            return score >= self.value

        return score <= self.value


class EvaluationMetricResult(BaseModel):
    """Normalized result for one metric on one evaluation case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: StrictStr = Field(min_length=1)
    metric_name: StrictStr = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    threshold_comparison: MetricComparison = "gte"
    passed: bool
    evaluator: StrictStr = Field(min_length=1)
    reason: StrictStr | None = None
    details: Metadata = Field(default_factory=dict)


class EvaluationRunResult(BaseModel):
    """Aggregate result for an evaluation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluator: StrictStr = Field(min_length=1)
    case_count: int = Field(ge=0)
    results: tuple[EvaluationMetricResult, ...] = ()

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        return len(self.results) - self.passed_count

    @property
    def passed(self) -> bool:
        return self.failed_count == 0

    @property
    def average_scores(self) -> dict[str, float]:
        scores_by_metric: dict[str, list[float]] = {}
        for result in self.results:
            scores_by_metric.setdefault(result.metric_name, []).append(result.score)

        return {
            metric_name: sum(scores) / len(scores)
            for metric_name, scores in scores_by_metric.items()
        }
