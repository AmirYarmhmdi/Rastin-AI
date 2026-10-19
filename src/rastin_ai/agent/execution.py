"""File guide.

- Use: Executes validated ExecutionPlan objects with deterministic DAG scheduling.
- Usage: Import ExecutionPlanExecutor, ExecutionResult, and TaskRuntimeState from
  rastin_ai.agent.execution.
- Duties: Tracks runtime task state separately from immutable plans, resolves
  task-output references, validates resolved arguments, and runs executors.
- Depends on: Standard library concurrency. Project modules:
  rastin_ai.agent.schemas, rastin_ai.observability, and
  rastin_ai.tools.registry.
"""

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    TaskOutputReference,
)
from rastin_ai.observability import observed_tool, sanitize_for_observability
from rastin_ai.tools.registry import (
    ToolArgumentValidationError,
    UnknownToolError,
    get_tool,
    validate_tool_arguments,
)

DEFAULT_MAX_CONCURRENCY = 4


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskRuntimeState(BaseModel):
    """Runtime outcome for one task, kept separate from ExecutionTask."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    status: TaskStatus
    result: Any | None = None
    error: str | None = None


class ExecutionResult(BaseModel):
    """Serializable result for an ExecutionPlan run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_states: dict[str, TaskRuntimeState] = Field(default_factory=dict)
    error: str | None = None

    @property
    def is_successful(self) -> bool:
        if self.error is not None:
            return False

        return all(
            task_state.status is TaskStatus.SUCCEEDED
            for task_state in self.task_states.values()
        )

    @property
    def successful_results(self) -> dict[str, Any]:
        return {
            task_id: task_state.result
            for task_id, task_state in self.task_states.items()
            if task_state.status is TaskStatus.SUCCEEDED
        }

    @property
    def failed_tasks(self) -> tuple[TaskRuntimeState, ...]:
        return tuple(
            task_state
            for task_state in self.task_states.values()
            if task_state.status is TaskStatus.FAILED
        )


class TaskArgumentResolutionError(ValueError):
    pass


class ExecutionPlanExecutor:
    """Run an ExecutionPlan without asking an LLM for runtime decisions."""

    def __init__(
        self,
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        on_task_state_change: Callable[[TaskRuntimeState], None] | None = None,
    ) -> None:
        if max_concurrency < 1:
            msg = "max_concurrency must be at least 1."
            raise ValueError(msg)

        self._max_concurrency = max_concurrency
        self._on_task_state_change = on_task_state_change

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        task_by_id = {task.id: task for task in plan.tasks}
        task_states = initialize_task_states(plan)
        for task_state in task_states.values():
            self._emit(task_state)

        pending_task_ids = set(task_by_id)
        while pending_task_ids:
            skipped_task_ids = _mark_blocked_tasks_skipped(
                pending_task_ids,
                task_by_id,
                task_states,
                self._emit,
            )
            pending_task_ids.difference_update(skipped_task_ids)
            if not pending_task_ids:
                break

            runnable_tasks = [
                task
                for task in sorted(
                    task_by_id.values(), key=lambda candidate: candidate.id
                )
                if task.id in pending_task_ids
                and _dependencies_succeeded(task, task_states)
            ]
            if not runnable_tasks:
                error = "ExecutionPlan execution stalled before completion."
                for task_id in sorted(pending_task_ids):
                    task_states[task_id] = TaskRuntimeState(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        error=error,
                    )
                    self._emit(task_states[task_id])
                return ExecutionResult(task_states=task_states, error=error)

            self._run_ready_tasks(runnable_tasks, task_states)
            pending_task_ids.difference_update(task.id for task in runnable_tasks)

        return ExecutionResult(task_states=task_states)

    def _run_ready_tasks(
        self,
        tasks: list[ExecutionTask],
        task_states: dict[str, TaskRuntimeState],
    ) -> None:
        states_snapshot = dict(task_states)
        max_workers = min(self._max_concurrency, len(tasks))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_task: dict[Future[Any], ExecutionTask] = {}
            for task in tasks:
                task_states[task.id] = TaskRuntimeState(
                    task_id=task.id,
                    status=TaskStatus.RUNNING,
                )
                self._emit(task_states[task.id])
                future_to_task[pool.submit(_execute_task, task, states_snapshot)] = task

            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                except TaskArgumentResolutionError:
                    task_states[task.id] = TaskRuntimeState(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error="Task arguments could not be resolved.",
                    )
                except ToolArgumentValidationError:
                    task_states[task.id] = TaskRuntimeState(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error="Task arguments failed validation.",
                    )
                except UnknownToolError:
                    task_states[task.id] = TaskRuntimeState(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error="Task capability is not executable.",
                    )
                except Exception:
                    task_states[task.id] = TaskRuntimeState(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error="Task execution failed.",
                    )
                else:
                    task_states[task.id] = TaskRuntimeState(
                        task_id=task.id,
                        status=TaskStatus.SUCCEEDED,
                        result=_copy_runtime_value(result),
                    )

                self._emit(task_states[task.id])

    def _emit(self, task_state: TaskRuntimeState) -> None:
        if self._on_task_state_change is not None:
            self._on_task_state_change(task_state)


def initialize_task_states(plan: ExecutionPlan) -> dict[str, TaskRuntimeState]:
    return {
        task.id: TaskRuntimeState(task_id=task.id, status=TaskStatus.PENDING)
        for task in plan.tasks
    }


def resolve_task_arguments(
    task: ExecutionTask,
    task_states: Mapping[str, TaskRuntimeState],
) -> dict[str, Any]:
    return {
        name: _resolve_argument_value(argument, task_states)
        for name, argument in task.arguments.items()
    }


def _execute_task(
    task: ExecutionTask,
    task_states: Mapping[str, TaskRuntimeState],
) -> Any:
    resolved_arguments = resolve_task_arguments(task, task_states)
    validated_arguments = validate_tool_arguments(task.capability, resolved_arguments)
    executor = get_tool(task.capability)
    with observed_tool(
        name=task.capability,
        input=validated_arguments,
        metadata={"task_id": task.id},
    ) as observation:
        result = executor.execute(**validated_arguments)
        observation.update(
            output=sanitize_for_observability(_observed_tool_result(result))
        )
        return result


def _resolve_argument_value(
    argument: LiteralArgument | TaskOutputReference,
    task_states: Mapping[str, TaskRuntimeState],
) -> Any:
    if isinstance(argument, LiteralArgument):
        return _copy_runtime_value(argument.value)

    upstream_state = task_states.get(argument.task_id)
    if upstream_state is None or upstream_state.status is not TaskStatus.SUCCEEDED:
        msg = "Referenced task output is unavailable."
        raise TaskArgumentResolutionError(msg)

    value = upstream_state.result
    if argument.path is not None:
        value = resolve_output_path(value, argument.path)

    return _copy_runtime_value(value)


def resolve_output_path(value: Any, path: str) -> Any:
    current_value = value
    for segment in path.split("."):
        if not segment:
            msg = "Task output reference path contains an empty segment."
            raise TaskArgumentResolutionError(msg)

        current_value = _resolve_path_segment(current_value, segment)

    return current_value


def _resolve_path_segment(value: Any, segment: str) -> Any:
    if isinstance(value, BaseModel):
        if segment not in value.__class__.model_fields:
            msg = "Task output reference path does not exist."
            raise TaskArgumentResolutionError(msg)
        return getattr(value, segment)

    if isinstance(value, Mapping):
        if segment not in value:
            msg = "Task output reference path does not exist."
            raise TaskArgumentResolutionError(msg)
        return value[segment]

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not segment.isdigit():
            msg = "Task output reference path segment is not a list index."
            raise TaskArgumentResolutionError(msg)
        index = int(segment)
        try:
            return value[index]
        except IndexError as exc:
            msg = "Task output reference list index is out of range."
            raise TaskArgumentResolutionError(msg) from exc

    msg = "Task output reference path cannot be resolved."
    raise TaskArgumentResolutionError(msg)


def _dependencies_succeeded(
    task: ExecutionTask,
    task_states: Mapping[str, TaskRuntimeState],
) -> bool:
    return all(
        task_states[dependency].status is TaskStatus.SUCCEEDED
        for dependency in task.depends_on
    )


def _mark_blocked_tasks_skipped(
    pending_task_ids: set[str],
    task_by_id: Mapping[str, ExecutionTask],
    task_states: dict[str, TaskRuntimeState],
    emit: Callable[[TaskRuntimeState], None],
) -> set[str]:
    skipped_task_ids: set[str] = set()
    for task_id in sorted(pending_task_ids):
        task = task_by_id[task_id]
        if any(
            task_states[dependency].status in {TaskStatus.FAILED, TaskStatus.SKIPPED}
            for dependency in task.depends_on
        ):
            task_states[task_id] = TaskRuntimeState(
                task_id=task_id,
                status=TaskStatus.SKIPPED,
                error="Task skipped because a dependency did not succeed.",
            )
            emit(task_states[task_id])
            skipped_task_ids.add(task_id)

    return skipped_task_ids


def _copy_runtime_value(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def _observed_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        result = result.model_dump(mode="python")
    if isinstance(result, Mapping):
        keys = sorted(str(key) for key in result)
        observed: dict[str, Any] = {
            "type": "mapping",
            "keys": keys[:20],
            "key_count": len(keys),
        }
        for count_key in ("document_count", "chunk_count", "source_count"):
            value = result.get(count_key)
            if isinstance(value, int):
                observed[count_key] = value
        return observed
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return {"type": "sequence", "item_count": len(result)}
    if isinstance(result, str):
        return {"type": "text", "chars": len(result)}
    if isinstance(result, bytes | bytearray | memoryview):
        return {"type": "binary", "bytes": len(result)}
    return {"type": type(result).__name__}
