"""File guide.

- Use: Provides centralized configurable evaluation thresholds.
- Usage: Import EvaluationThresholds or thresholds_from_settings.
- Duties: Avoids scattering metric cutoffs through evaluators and tests.
- Depends on: Project modules: rastin_ai.core.config and evaluation models.
"""

from pydantic import BaseModel, ConfigDict, Field

from rastin_ai.core.config import Settings, get_settings
from rastin_ai.evaluation.models import MetricThreshold


class EvaluationThresholds(BaseModel):
    """Baseline quality thresholds for normalized evaluator metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_relevancy: float = Field(default=0.70, ge=0.0, le=1.0)
    faithfulness: float = Field(default=0.70, ge=0.0, le=1.0)
    context_precision: float = Field(default=0.70, ge=0.0, le=1.0)
    context_recall: float = Field(default=0.70, ge=0.0, le=1.0)
    hallucination: float = Field(default=0.30, ge=0.0, le=1.0)

    def for_metric(self, metric_name: str) -> MetricThreshold:
        normalized_metric_name = metric_name.strip().lower()
        if normalized_metric_name == "hallucination":
            return MetricThreshold(
                metric_name=normalized_metric_name,
                value=self.hallucination,
                comparison="lte",
            )

        threshold_by_metric = {
            "answer_relevancy": self.answer_relevancy,
            "faithfulness": self.faithfulness,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
        }
        if normalized_metric_name not in threshold_by_metric:
            msg = f"No evaluation threshold is configured for metric: {metric_name}"
            raise ValueError(msg)

        return MetricThreshold(
            metric_name=normalized_metric_name,
            value=threshold_by_metric[normalized_metric_name],
            comparison="gte",
        )


def thresholds_from_settings(settings: Settings | None = None) -> EvaluationThresholds:
    """Build evaluation thresholds from application settings."""

    resolved_settings = settings or get_settings()
    return EvaluationThresholds(
        answer_relevancy=resolved_settings.EVALUATION_ANSWER_RELEVANCY_THRESHOLD,
        faithfulness=resolved_settings.EVALUATION_FAITHFULNESS_THRESHOLD,
        context_precision=resolved_settings.EVALUATION_CONTEXT_PRECISION_THRESHOLD,
        context_recall=resolved_settings.EVALUATION_CONTEXT_RECALL_THRESHOLD,
        hallucination=resolved_settings.EVALUATION_HALLUCINATION_THRESHOLD,
    )
