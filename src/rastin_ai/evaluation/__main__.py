"""Developer entry point for Rastin-AI evaluation."""

import argparse
import json
from pathlib import Path

from rastin_ai.evaluation.dataset import load_evaluation_dataset
from rastin_ai.evaluation.deepeval_evaluator import DEEPEVAL_METRICS
from rastin_ai.evaluation.live import (
    DEFAULT_LIVE_MAX_CASES,
    LiveEvaluationError,
    run_live_deepeval_sync,
)
from rastin_ai.evaluation.ragas_evaluator import RAGAS_METRICS, RagasEvaluator
from rastin_ai.evaluation.runner import EvaluationRunner
from rastin_ai.evaluation.thresholds import thresholds_from_settings

DEFAULT_DATASET = "evaluation/datasets/smoke.jsonl"
DEFAULT_LIVE_DATASET = "evaluation/datasets/live_smoke.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m rastin_ai.evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--dataset", default=DEFAULT_DATASET)
    validate_parser.add_argument("--tags", nargs="*", default=())

    ragas_parser = subparsers.add_parser("ragas")
    ragas_parser.add_argument("--dataset", default=DEFAULT_DATASET)
    ragas_parser.add_argument("--tags", nargs="*", default=())
    ragas_parser.add_argument("--metrics", nargs="*", default=list(RAGAS_METRICS))

    live_parser = subparsers.add_parser("live-deepeval")
    live_parser.add_argument("--dataset", default=DEFAULT_LIVE_DATASET)
    live_parser.add_argument("--tags", nargs="*", default=("live", "smoke"))
    live_parser.add_argument("--metrics", nargs="*", default=list(DEEPEVAL_METRICS))
    live_parser.add_argument("--max-cases", type=int, default=DEFAULT_LIVE_MAX_CASES)
    live_parser.add_argument("--report-path")
    live_parser.add_argument(
        "--include-report-text",
        action="store_true",
        help=(
            "Include bounded input/output/context text only for cases marked "
            "metadata.live.safe_report_text=true."
        ),
    )
    live_parser.add_argument("--context-preview-chars", type=int, default=500)

    args = parser.parse_args()

    if args.command == "validate":
        cases = load_evaluation_dataset(Path(args.dataset), tags=args.tags)
        print(json.dumps({"dataset": args.dataset, "case_count": len(cases)}))
        return

    if args.command == "live-deepeval":
        if args.max_cases < 1:
            raise SystemExit("--max-cases must be at least 1.")
        if args.context_preview_chars < 0:
            raise SystemExit("--context-preview-chars must be at least 0.")
        try:
            result = run_live_deepeval_sync(
                dataset_path=args.dataset,
                tags=args.tags,
                metrics=args.metrics,
                max_cases=args.max_cases,
                report_path=args.report_path,
                include_report_text=args.include_report_text,
                context_preview_chars=args.context_preview_chars,
            )
        except LiveEvaluationError as exc:
            print(json.dumps({"status": "skipped", "reason": str(exc)}))
            raise SystemExit(1) from exc
        if not result.passed:
            raise SystemExit(1)
        return

    thresholds = thresholds_from_settings()
    runner = EvaluationRunner(evaluator=RagasEvaluator(), thresholds=thresholds)
    result = runner.run_dataset(args.dataset, metrics=args.metrics, tags=args.tags)
    print(
        json.dumps(
            {
                "evaluator": result.evaluator,
                "case_count": result.case_count,
                "passed": result.passed,
                "passed_count": result.passed_count,
                "failed_count": result.failed_count,
                "average_scores": result.average_scores,
            },
            sort_keys=True,
        )
    )
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
