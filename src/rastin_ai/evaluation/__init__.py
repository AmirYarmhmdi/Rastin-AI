"""File guide.

- Use: Exports Rastin-AI evaluation infrastructure.
- Usage: Import evaluation cases, loaders, thresholds, and runners.
- Duties: Keeps the public evaluation API framework-neutral by default.
- Depends on: Project evaluation modules.
"""

from rastin_ai.evaluation.dataset import (
    EvaluationDatasetError,
    load_evaluation_dataset,
)
from rastin_ai.evaluation.models import (
    EvaluationCase,
    EvaluationMetricResult,
    EvaluationRunResult,
    MetricThreshold,
)
from rastin_ai.evaluation.runner import EvaluationRunner, Evaluator
from rastin_ai.evaluation.thresholds import (
    EvaluationThresholds,
    thresholds_from_settings,
)

__all__ = [
    "EvaluationCase",
    "EvaluationDatasetError",
    "EvaluationMetricResult",
    "EvaluationRunResult",
    "EvaluationRunner",
    "EvaluationThresholds",
    "Evaluator",
    "MetricThreshold",
    "load_evaluation_dataset",
    "thresholds_from_settings",
]
