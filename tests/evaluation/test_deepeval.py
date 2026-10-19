"""LLM-backed DeepEval regression smoke tests."""

import os

import pytest

from rastin_ai.evaluation.dataset import load_evaluation_dataset
from rastin_ai.evaluation.thresholds import EvaluationThresholds

pytestmark = pytest.mark.evaluation


def test_deepeval_smoke_dataset() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for DeepEval evaluation tests.")

    pytest.importorskip("deepeval")

    from deepeval import assert_test
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        FaithfulnessMetric,
        HallucinationMetric,
    )

    from rastin_ai.evaluation.deepeval_evaluator import build_deepeval_test_case

    cases = load_evaluation_dataset(
        "evaluation/datasets/smoke.jsonl",
        tags=["smoke"],
    )
    thresholds = EvaluationThresholds()

    for case in cases:
        test_case = build_deepeval_test_case(case)
        metrics = [
            AnswerRelevancyMetric(threshold=thresholds.answer_relevancy),
            FaithfulnessMetric(threshold=thresholds.faithfulness),
            HallucinationMetric(threshold=thresholds.hallucination),
        ]
        assert_test(test_case, metrics)
