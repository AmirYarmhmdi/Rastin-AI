"""File guide.

- Use: Runs opt-in live evaluation against the real Rastin-AI runtime.
- Usage: Import LiveEvaluationRunner or run through the evaluation CLI.
- Duties: Executes canonical cases through upload, ingestion, RAG, generation,
  and evaluator adapters without mutating source datasets.
- Depends on: Project runtime services, repositories, evaluation models, and
  optional external PostgreSQL/Qdrant/OpenAI services.
"""

import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from rastin_ai.api.dependencies import (
    get_document_ingestion_service,
    get_question_answering_service,
    get_storage_provider,
)
from rastin_ai.core.config import (
    ConfigurationError,
    ConfigurationIssue,
    Settings,
    get_settings,
    validate_runtime_configuration,
)
from rastin_ai.database.engine import create_database_engine
from rastin_ai.database.session import create_session_factory
from rastin_ai.evaluation.dataset import load_evaluation_dataset
from rastin_ai.evaluation.deepeval_evaluator import (
    DEEPEVAL_METRICS,
    DeepEvalEvaluator,
)
from rastin_ai.evaluation.models import (
    EvaluationCase,
    EvaluationMetricResult,
    EvaluationRunResult,
)
from rastin_ai.evaluation.runner import EvaluationRunner
from rastin_ai.evaluation.thresholds import EvaluationThresholds
from rastin_ai.observability import is_observability_enabled
from rastin_ai.repositories.documents import SQLAlchemyDocumentRepository
from rastin_ai.repositories.users import SQLAlchemyUserRepository
from rastin_ai.repositories.workflow_execution import (
    SQLAlchemyWorkflowExecutionRepository,
)
from rastin_ai.security.auth import AuthenticatedPrincipal, validate_bearer_token
from rastin_ai.services.documents import DocumentUpload, StoredDocumentService
from rastin_ai.services.questions import QuestionInput
from rastin_ai.services.upload import UploadService

RUN_LIVE_EVALUATION_ENV = "RUN_LIVE_EVALUATION"
DEFAULT_LIVE_MAX_CASES = 1
DEFAULT_CONTEXT_PREVIEW_CHARS = 500
MAX_REPORTED_ERROR_CHARS = 600


class LiveEvaluationError(RuntimeError):
    """Raised when live evaluation cannot be completed safely."""


@dataclass(frozen=True)
class LiveDocumentFixture:
    filename: str
    content: bytes
    content_type: str | None = None


@dataclass(frozen=True)
class RuntimeCaseResult:
    case_id: str
    actual_output: str | None
    retrieved_contexts: tuple[str, ...]
    model_name: str | None
    token_usage: dict[str, int] | None
    latency_ms: float
    workflow_id: str | None
    trace_id: str | None
    trace_id_note: str | None = None
    document_ids: tuple[str, ...] = ()
    error: str | None = None


class LiveMetricReport(BaseModel):
    """Serializable result for one metric on one live case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_name: str
    score: float
    threshold: float
    threshold_comparison: str
    passed: bool
    reason: str | None = None


class LiveCaseReport(BaseModel):
    """Serializable, redacted live evaluation report for one case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    latency_ms: float
    model_name: str | None = None
    token_usage: dict[str, int] | None = None
    workflow_id: str | None = None
    trace_id: str | None = None
    trace_id_note: str | None = None
    document_count: int = 0
    retrieved_context_count: int = 0
    retrieved_context_chars: int = 0
    report_text_included: bool = False
    report_text_policy: str = "omitted"
    input: str | None = None
    expected_output: str | None = None
    actual_output: str | None = None
    retrieved_context_preview: tuple[str, ...] = ()
    retrieved_context_preview_chars: int = 0
    metrics: tuple[LiveMetricReport, ...] = ()
    error: str | None = None


class LiveEvaluationReport(BaseModel):
    """Serializable aggregate report for one live evaluation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluator: str
    dataset: str
    case_count: int
    evaluated_case_count: int
    passed: bool
    passed_count: int
    failed_count: int
    metrics: tuple[str, ...]
    contains_safe_test_text: bool = False
    average_scores: dict[str, float] = Field(default_factory=dict)
    cases: tuple[LiveCaseReport, ...] = ()


class RuntimeExecutor:
    async def execute(self, case: EvaluationCase) -> RuntimeCaseResult:
        """Execute one canonical case through a runtime."""


class RastinAIRuntimeExecutor:
    """Execute evaluation cases through the configured Rastin-AI services."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def execute(self, case: EvaluationCase) -> RuntimeCaseResult:
        fixtures = _document_fixtures(case)
        start = time.perf_counter()
        document_ids: list[UUID] = []
        workflow_id: UUID | None = None
        trace_id: str | None = None
        try:
            engine = create_database_engine(self._settings.DATABASE_URL)
            try:
                session_factory = create_session_factory(engine)
                async with session_factory() as session:
                    document_repository = SQLAlchemyDocumentRepository(session)
                    workflow_repository = SQLAlchemyWorkflowExecutionRepository(session)
                    principal = await _principal_for_live_run(
                        settings=self._settings,
                        user_repository=SQLAlchemyUserRepository(session),
                    )
                    storage_provider = get_storage_provider(self._settings)
                    upload_service = UploadService(
                        storage_provider=storage_provider,
                        document_repository=document_repository,
                        user_id=principal.user_id,
                        storage_backend=self._settings.STORAGE_BACKEND,
                        max_upload_bytes=self._settings.MAX_UPLOAD_BYTES,
                    )
                    ingestion_service = get_document_ingestion_service(
                        self._settings,
                        storage_provider,
                        document_repository,
                    )
                    document_service = StoredDocumentService(
                        upload_service=upload_service,
                        document_repository=document_repository,
                        ingestion_service=ingestion_service,
                        user_id=principal.user_id,
                    )
                    for fixture in fixtures:
                        document = await document_service.upload_document(
                            DocumentUpload(
                                filename=fixture.filename,
                                content=fixture.content,
                                content_type=fixture.content_type,
                            )
                        )
                        document_ids.append(document.document_id)

                    question_service = get_question_answering_service(
                        self._settings,
                        document_service,
                        workflow_repository,
                        principal,
                    )
                    answer = await question_service.answer(
                        QuestionInput(
                            question=case.input,
                            document_ids=document_ids,
                        )
                    )
                    workflow_id = answer.workflow_id
                    if workflow_id is not None:
                        workflow = await workflow_repository.get_by_id(
                            workflow_id,
                            user_id=principal.user_id,
                        )
                        trace_id = workflow.trace_id if workflow is not None else None

                    return RuntimeCaseResult(
                        case_id=case.id,
                        actual_output=answer.answer,
                        retrieved_contexts=answer.retrieved_contexts,
                        model_name=answer.model_name,
                        token_usage=answer.token_usage,
                        latency_ms=_elapsed_ms(start),
                        workflow_id=(
                            str(workflow_id) if workflow_id is not None else None
                        ),
                        trace_id=trace_id,
                        trace_id_note=_trace_id_note(self._settings, trace_id),
                        document_ids=tuple(str(item) for item in document_ids),
                    )
            finally:
                await engine.dispose()
        except Exception as exc:
            return RuntimeCaseResult(
                case_id=case.id,
                actual_output=None,
                retrieved_contexts=(),
                model_name=None,
                token_usage=None,
                latency_ms=_elapsed_ms(start),
                workflow_id=str(workflow_id) if workflow_id is not None else None,
                trace_id=trace_id,
                trace_id_note=_trace_id_note(self._settings, trace_id),
                document_ids=tuple(str(item) for item in document_ids),
                error=_safe_error(exc),
            )


class LiveEvaluationRunner:
    """Run canonical cases through a runtime and evaluate generated outputs."""

    def __init__(
        self,
        *,
        runtime_executor: RuntimeExecutor,
        evaluator: Any,
        thresholds: EvaluationThresholds,
    ) -> None:
        self._runtime_executor = runtime_executor
        self._evaluator = evaluator
        self._thresholds = thresholds

    async def run_cases(
        self,
        cases: Sequence[EvaluationCase],
        *,
        dataset: str,
        metrics: Sequence[str],
        include_report_text: bool = False,
        context_preview_chars: int = DEFAULT_CONTEXT_PREVIEW_CHARS,
    ) -> LiveEvaluationReport:
        if not cases:
            msg = "Live evaluation requires at least one case."
            raise ValueError(msg)
        if not metrics:
            msg = "Live evaluation requires at least one metric."
            raise ValueError(msg)
        if context_preview_chars < 0:
            msg = "context_preview_chars must be greater than or equal to 0."
            raise ValueError(msg)

        runtime_results: list[RuntimeCaseResult] = []
        generated_cases: list[EvaluationCase] = []
        source_cases_by_id = {case.id: case for case in cases}
        for case in cases:
            runtime_result = await self._runtime_executor.execute(case)
            runtime_results.append(runtime_result)
            if runtime_result.error is not None:
                continue
            generated_cases.append(_case_from_runtime(case, runtime_result))

        evaluation_result, evaluation_errors = _evaluate_generated_cases(
            evaluator=self._evaluator,
            thresholds=self._thresholds,
            generated_cases=generated_cases,
            metrics=metrics,
        )
        metric_results_by_case = _metric_results_by_case(evaluation_result.results)
        case_reports = tuple(
            _case_report(
                runtime_result,
                metric_results_by_case,
                evaluation_errors,
                source_cases_by_id[runtime_result.case_id],
                include_report_text=include_report_text,
                context_preview_chars=context_preview_chars,
            )
            for runtime_result in runtime_results
        )
        failed_count = sum(1 for case_report in case_reports if not case_report.passed)

        return LiveEvaluationReport(
            evaluator=self._evaluator.name,
            dataset=dataset,
            case_count=len(cases),
            evaluated_case_count=len(generated_cases),
            passed=failed_count == 0,
            passed_count=len(case_reports) - failed_count,
            failed_count=failed_count,
            metrics=tuple(metrics),
            contains_safe_test_text=any(
                case_report.report_text_included for case_report in case_reports
            ),
            average_scores=evaluation_result.average_scores,
            cases=case_reports,
        )


async def run_live_deepeval(
    *,
    dataset_path: str | Path,
    tags: Sequence[str],
    metrics: Sequence[str],
    max_cases: int,
    include_report_text: bool = False,
    context_preview_chars: int = DEFAULT_CONTEXT_PREVIEW_CHARS,
    settings: Settings | None = None,
) -> LiveEvaluationReport:
    """Run live runtime execution followed by DeepEval scoring."""

    _require_live_evaluation_enabled()
    resolved_settings = settings or get_settings()
    await _check_live_prerequisites(resolved_settings)
    cases = load_evaluation_dataset(dataset_path, tags=tags)
    selected_cases = cases[:max_cases]
    runner = LiveEvaluationRunner(
        runtime_executor=RastinAIRuntimeExecutor(settings=resolved_settings),
        evaluator=DeepEvalEvaluator(settings=resolved_settings),
        thresholds=EvaluationThresholds(
            answer_relevancy=resolved_settings.EVALUATION_ANSWER_RELEVANCY_THRESHOLD,
            faithfulness=resolved_settings.EVALUATION_FAITHFULNESS_THRESHOLD,
            context_precision=resolved_settings.EVALUATION_CONTEXT_PRECISION_THRESHOLD,
            context_recall=resolved_settings.EVALUATION_CONTEXT_RECALL_THRESHOLD,
            hallucination=resolved_settings.EVALUATION_HALLUCINATION_THRESHOLD,
        ),
    )
    return await runner.run_cases(
        selected_cases,
        dataset=str(dataset_path),
        metrics=metrics,
        include_report_text=include_report_text,
        context_preview_chars=context_preview_chars,
    )


def run_live_deepeval_sync(
    *,
    dataset_path: str | Path,
    tags: Sequence[str],
    metrics: Sequence[str] = DEEPEVAL_METRICS,
    max_cases: int = DEFAULT_LIVE_MAX_CASES,
    report_path: str | Path | None = None,
    include_report_text: bool = False,
    context_preview_chars: int = DEFAULT_CONTEXT_PREVIEW_CHARS,
) -> LiveEvaluationReport:
    report = asyncio.run(
        run_live_deepeval(
            dataset_path=dataset_path,
            tags=tags,
            metrics=metrics,
            max_cases=max_cases,
            include_report_text=include_report_text,
            context_preview_chars=context_preview_chars,
        )
    )
    _emit_console_report(report)
    if report_path is not None:
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(_report_json(report) + "\n")
    else:
        print(_report_json(report))
    return report


def _evaluate_generated_cases(
    *,
    evaluator: Any,
    thresholds: EvaluationThresholds,
    generated_cases: Sequence[EvaluationCase],
    metrics: Sequence[str],
) -> tuple[EvaluationRunResult, dict[str, str]]:
    if not generated_cases:
        return (
            EvaluationRunResult(evaluator=evaluator.name, case_count=0, results=()),
            {},
        )

    runner = EvaluationRunner(evaluator=evaluator, thresholds=thresholds)
    results: list[EvaluationMetricResult] = []
    errors: dict[str, str] = {}
    for case in generated_cases:
        try:
            result = runner.run_cases((case,), metrics=metrics)
        except Exception as exc:
            errors[case.id] = _safe_error(exc)
            continue
        results.extend(result.results)

    return (
        EvaluationRunResult(
            evaluator=evaluator.name,
            case_count=len(generated_cases),
            results=tuple(results),
        ),
        errors,
    )


def _case_from_runtime(
    source_case: EvaluationCase,
    runtime_result: RuntimeCaseResult,
) -> EvaluationCase:
    return source_case.model_copy(
        update={
            "actual_output": runtime_result.actual_output,
            "retrieved_contexts": runtime_result.retrieved_contexts,
            "metadata": {
                **source_case.metadata,
                "runtime": {
                    "model_name": runtime_result.model_name,
                    "token_usage": runtime_result.token_usage,
                    "latency_ms": runtime_result.latency_ms,
                    "workflow_id": runtime_result.workflow_id,
                    "trace_id": runtime_result.trace_id,
                },
            },
        }
    )


def _case_report(
    runtime_result: RuntimeCaseResult,
    metric_results_by_case: dict[str, tuple[EvaluationMetricResult, ...]],
    evaluation_errors: dict[str, str],
    source_case: EvaluationCase,
    *,
    include_report_text: bool,
    context_preview_chars: int,
) -> LiveCaseReport:
    metric_results = metric_results_by_case.get(runtime_result.case_id, ())
    metric_reports = tuple(_metric_report(result) for result in metric_results)
    metric_failed = any(not result.passed for result in metric_reports)
    error = runtime_result.error or evaluation_errors.get(runtime_result.case_id)
    passed = error is None and bool(metric_reports) and not metric_failed
    text_fields = _safe_report_text_fields(
        source_case=source_case,
        runtime_result=runtime_result,
        include_report_text=include_report_text,
        context_preview_chars=context_preview_chars,
    )
    return LiveCaseReport(
        case_id=runtime_result.case_id,
        passed=passed,
        latency_ms=round(runtime_result.latency_ms, 2),
        model_name=runtime_result.model_name,
        token_usage=runtime_result.token_usage,
        workflow_id=runtime_result.workflow_id,
        trace_id=runtime_result.trace_id,
        trace_id_note=runtime_result.trace_id_note,
        document_count=len(runtime_result.document_ids),
        retrieved_context_count=len(runtime_result.retrieved_contexts),
        retrieved_context_chars=sum(
            len(context) for context in runtime_result.retrieved_contexts
        ),
        **text_fields,
        metrics=metric_reports,
        error=error,
    )


def _safe_report_text_fields(
    *,
    source_case: EvaluationCase,
    runtime_result: RuntimeCaseResult,
    include_report_text: bool,
    context_preview_chars: int,
) -> dict[str, Any]:
    if not include_report_text:
        return {
            "report_text_included": False,
            "report_text_policy": "omitted_by_default",
        }
    if not _case_allows_report_text(source_case):
        return {
            "report_text_included": False,
            "report_text_policy": "omitted_case_not_marked_safe",
        }

    previews = tuple(
        _bounded_preview(context, context_preview_chars)
        for context in runtime_result.retrieved_contexts
    )
    return {
        "report_text_included": True,
        "report_text_policy": "safe_test_only",
        "input": source_case.input,
        "expected_output": source_case.expected_output,
        "actual_output": runtime_result.actual_output,
        "retrieved_context_preview": previews,
        "retrieved_context_preview_chars": context_preview_chars,
    }


def _case_allows_report_text(case: EvaluationCase) -> bool:
    live_metadata = case.metadata.get("live")
    if not isinstance(live_metadata, dict):
        return False
    return live_metadata.get("safe_report_text") is True


def _bounded_preview(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...<truncated>"


def _metric_report(result: EvaluationMetricResult) -> LiveMetricReport:
    return LiveMetricReport(
        metric_name=result.metric_name,
        score=result.score,
        threshold=result.threshold,
        threshold_comparison=result.threshold_comparison,
        passed=result.passed,
        reason=result.reason,
    )


def _metric_results_by_case(
    results: Sequence[EvaluationMetricResult],
) -> dict[str, tuple[EvaluationMetricResult, ...]]:
    grouped: dict[str, list[EvaluationMetricResult]] = {}
    for result in results:
        grouped.setdefault(result.case_id, []).append(result)

    return {case_id: tuple(case_results) for case_id, case_results in grouped.items()}


def _document_fixtures(case: EvaluationCase) -> tuple[LiveDocumentFixture, ...]:
    live_metadata = case.metadata.get("live")
    if not isinstance(live_metadata, dict):
        return ()

    raw_documents = live_metadata.get("documents", ())
    if not isinstance(raw_documents, list | tuple):
        msg = f"Live case {case.id} metadata.live.documents must be an array."
        raise LiveEvaluationError(msg)

    fixtures: list[LiveDocumentFixture] = []
    for index, raw_document in enumerate(raw_documents, start=1):
        if not isinstance(raw_document, dict):
            msg = f"Live case {case.id} document fixture {index} must be an object."
            raise LiveEvaluationError(msg)
        filename = _required_text(raw_document.get("filename"), "filename", case.id)
        content = _required_text(raw_document.get("content"), "content", case.id)
        content_type = raw_document.get("content_type")
        if content_type is not None and not isinstance(content_type, str):
            msg = f"Live case {case.id} document content_type must be a string."
            raise LiveEvaluationError(msg)
        fixtures.append(
            LiveDocumentFixture(
                filename=filename,
                content=content.encode("utf-8"),
                content_type=content_type,
            )
        )

    return tuple(fixtures)


def _required_text(value: Any, field_name: str, case_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"Live case {case_id} document {field_name} must be a non-empty string."
        raise LiveEvaluationError(msg)
    return value.strip()


async def _principal_for_live_run(
    *,
    settings: Settings,
    user_repository: SQLAlchemyUserRepository,
) -> AuthenticatedPrincipal:
    identity = validate_bearer_token(token=None, settings=settings)
    user = await user_repository.resolve_external_identity(identity)
    return AuthenticatedPrincipal(
        user_id=user.id,
        issuer=identity.issuer,
        subject=identity.subject,
        email=user.email,
        display_name=user.display_name,
    )


def _require_live_evaluation_enabled() -> None:
    if os.environ.get(RUN_LIVE_EVALUATION_ENV) == "1":
        return

    msg = (
        "Live evaluation is disabled. Set RUN_LIVE_EVALUATION=1 to run paid, "
        "non-deterministic runtime evaluation."
    )
    raise LiveEvaluationError(msg)


async def _check_live_prerequisites(settings: Settings) -> None:
    try:
        validate_runtime_configuration(settings)
    except ConfigurationError as exc:
        safe_issues = [
            ConfigurationIssue(issue.setting, issue.message) for issue in exc.issues
        ]
        raise LiveEvaluationError(str(ConfigurationError(safe_issues))) from exc

    await _check_database(settings)
    _check_qdrant(settings)


async def _check_database(settings: Settings) -> None:
    engine = create_database_engine(settings.DATABASE_URL)
    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await session.execute(text("select 1"))
    except Exception as exc:
        msg = "PostgreSQL is unavailable for live evaluation."
        raise LiveEvaluationError(msg) from exc
    finally:
        await engine.dispose()


def _check_qdrant(settings: Settings) -> None:
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        client.get_collections()
    except Exception as exc:
        msg = "Qdrant is unavailable for live evaluation."
        raise LiveEvaluationError(msg) from exc


def _trace_id_note(settings: Settings, trace_id: str | None) -> str | None:
    if trace_id is not None:
        return None
    if is_observability_enabled(settings):
        return "Langfuse is enabled, but no trace ID was available."
    return "Langfuse tracing is disabled or unavailable; null trace_id is expected."


def _emit_console_report(report: LiveEvaluationReport) -> None:
    print(
        (
            f"Live evaluation: {report.passed_count}/{report.case_count} cases passed "
            f"using {report.evaluator}"
        ),
        file=sys.stderr,
    )
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        metric_summary = ", ".join(
            f"{metric.metric_name}={metric.score:.2f}" for metric in case.metrics
        )
        if not metric_summary:
            metric_summary = "no metrics"
        print(
            (
                f"{status} {case.case_id}: {metric_summary}; "
                f"latency={case.latency_ms:.2f}ms; "
                f"contexts={case.retrieved_context_count}"
            ),
            file=sys.stderr,
        )
        if case.error:
            print(f"  error={case.error}", file=sys.stderr)


def _report_json(report: LiveEvaluationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), sort_keys=True)


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:MAX_REPORTED_ERROR_CHARS]
