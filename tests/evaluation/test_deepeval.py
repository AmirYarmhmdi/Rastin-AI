"""LLM-backed regression checks of stored synthetic observations."""

import json
from pathlib import Path

import pytest

from rastin_ai.core.config import get_settings
from rastin_ai.evaluation.dataset import load_evaluation_dataset
from rastin_ai.evaluation.deepeval_evaluator import DEEPEVAL_METRICS, DeepEvalEvaluator
from rastin_ai.evaluation.models import EvaluationCase
from rastin_ai.evaluation.runner import EvaluationRunner
from rastin_ai.evaluation.thresholds import thresholds_from_settings

pytestmark = pytest.mark.evaluation
SMOKE_CASES = load_evaluation_dataset("evaluation/datasets/smoke.jsonl", tags=["smoke"])


@pytest.mark.parametrize("case", SMOKE_CASES, ids=lambda case: case.id)
def test_deepeval_smoke_dataset(case: EvaluationCase) -> None:
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY is required for DeepEval evaluation tests.")

    pytest.importorskip("deepeval")

    runner = EvaluationRunner(
        evaluator=DeepEvalEvaluator(settings=settings, include_diagnostics=True),
        thresholds=thresholds_from_settings(settings),
    )
    result = runner.run_cases((case,), metrics=DEEPEVAL_METRICS)
    report = {
        "dataset": "evaluation/datasets/smoke.jsonl",
        "case": case.model_dump(mode="json"),
        "evaluation_model": settings.EVALUATION_MODEL,
        "passed": result.passed,
        "results": result.model_dump(mode="json"),
    }
    report_path = Path("evaluation-results/deepeval-smoke") / f"{case.id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = json.dumps(report, indent=2, ensure_ascii=False)
    report_path.write_text(report_text + "\n", encoding="utf-8")
    print(f"\nDeepEval report: {report_path}\n{report_text}")
    assert result.passed, f"DeepEval failed; report: {report_path}\n{report_text}"
