"""File guide.

- Use: Orchestrates evaluation execution behind Rastin-AI-owned interfaces.
- Usage: Import EvaluationRunner and Evaluator.
- Duties: Keeps callers independent from Ragas, DeepEval, or future frameworks.
- Depends on: Project evaluation models and thresholds.
"""

from collections.abc import Sequence
from typing import Protocol

from rastin_ai.evaluation.dataset import load_evaluation_dataset
from rastin_ai.evaluation.models import EvaluationCase, EvaluationRunResult
from rastin_ai.evaluation.thresholds import EvaluationThresholds


class Evaluator(Protocol):
    """Framework adapter contract for Rastin-AI evaluators."""

    @property
    def name(self) -> str:
        """Stable evaluator identifier."""

    def evaluate(
        self,
        *,
        cases: Sequence[EvaluationCase],
        metrics: Sequence[str],
        thresholds: EvaluationThresholds,
    ) -> EvaluationRunResult:
        """Evaluate cases and return normalized results."""


class EvaluationRunner:
    """Reusable service for executing evaluation adapters."""

    def __init__(
        self,
        *,
        evaluator: Evaluator,
        thresholds: EvaluationThresholds | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._thresholds = thresholds or EvaluationThresholds()

    def run_cases(
        self,
        cases: Sequence[EvaluationCase],
        *,
        metrics: Sequence[str],
    ) -> EvaluationRunResult:
        if not cases:
            msg = "Evaluation runner requires at least one case."
            raise ValueError(msg)
        if not metrics:
            msg = "Evaluation runner requires at least one metric."
            raise ValueError(msg)

        return self._evaluator.evaluate(
            cases=cases,
            metrics=metrics,
            thresholds=self._thresholds,
        )

    def run_dataset(
        self,
        dataset_path: str,
        *,
        metrics: Sequence[str],
        tags: Sequence[str] = (),
    ) -> EvaluationRunResult:
        cases = load_evaluation_dataset(dataset_path, tags=tags)
        return self.run_cases(cases, metrics=metrics)
