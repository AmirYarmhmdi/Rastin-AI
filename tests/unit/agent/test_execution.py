"""File guide.

- Use: Contains unit tests for deterministic ExecutionPlan DAG execution.
- Usage: Run this file with pytest when checking agent runtime behavior.
- Duties: Registers fake capabilities, executes plans, and verifies task states.
- Depends on: Standard library threading. Project modules:
  rastin_ai.agent.execution, rastin_ai.agent.schemas, and
  rastin_ai.tools.registry.
"""

import inspect
from threading import Barrier
from typing import Any

from pydantic import BaseModel, ConfigDict

import rastin_ai.agent.execution as execution_module
from rastin_ai.agent.execution import (
    ExecutionPlanExecutor,
    TaskStatus,
    initialize_task_states,
)
from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    TaskOutputReference,
)
from rastin_ai.skills import CapabilityDefinition
from rastin_ai.tools.registry import register_capability


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class TextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class JoinArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: str
    right: str


class ModelOutput(BaseModel):
    document_id: str


class RecordingExecutor:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result


class FailingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, **kwargs: Any) -> Any:
        self.calls += 1
        raise RuntimeError("raw provider payload with secret-token")


def _register(name: str, schema: type[BaseModel], executor: object) -> None:
    register_capability(
        CapabilityDefinition(
            name=name,
            description=f"Execute {name}.",
            input_schema=schema,
        ),
        executor,
    )


def test_initial_task_states_are_pending_and_plan_level_success_completes() -> None:
    plan = ExecutionPlan(tasks=[ExecutionTask(id="task_1", capability="test.empty")])

    assert initialize_task_states(plan)["task_1"].status is TaskStatus.PENDING

    executor = RecordingExecutor({"ok": True})
    _register("test.empty", EmptyArguments, executor)

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_1"].status is TaskStatus.SUCCEEDED
    assert result.is_successful is True
    assert result.successful_results == {"task_1": {"ok": True}}


def test_running_transition_is_emitted_before_success() -> None:
    seen_statuses: list[TaskStatus] = []
    _register("test.empty", EmptyArguments, RecordingExecutor({"ok": True}))
    plan = ExecutionPlan(tasks=[ExecutionTask(id="task_1", capability="test.empty")])

    ExecutionPlanExecutor(
        on_task_state_change=lambda state: seen_statuses.append(state.status)
    ).execute(plan)

    assert seen_statuses == [
        TaskStatus.PENDING,
        TaskStatus.RUNNING,
        TaskStatus.SUCCEEDED,
    ]


def test_sequential_dependency_resolves_upstream_output_before_downstream() -> None:
    calls: list[str] = []

    class Producer:
        def execute(self, **kwargs: Any) -> Any:
            calls.append("task_1")
            return {"document_id": "abc"}

    class Consumer:
        def execute(self, **kwargs: Any) -> Any:
            calls.append("task_2")
            return {"received": kwargs["text"]}

    _register("test.produce", EmptyArguments, Producer())
    _register("test.consume", TextArguments, Consumer())
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_2",
                capability="test.consume",
                depends_on=["task_1"],
                arguments={
                    "text": TaskOutputReference(
                        task_id="task_1",
                        path="document_id",
                    )
                },
            ),
            ExecutionTask(id="task_1", capability="test.produce"),
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert calls == ["task_1", "task_2"]
    assert result.task_states["task_2"].result == {"received": "abc"}


def test_parallel_branches_are_eligible_before_join_task() -> None:
    barrier = Barrier(2)
    calls: list[str] = []

    class Branch:
        def execute(self, **kwargs: Any) -> Any:
            calls.append(f"start:{kwargs['text']}")
            barrier.wait(timeout=2)
            calls.append(f"finish:{kwargs['text']}")
            return {"value": kwargs["text"]}

    class Join:
        def execute(self, **kwargs: Any) -> Any:
            calls.append("join")
            return f"{kwargs['left']}+{kwargs['right']}"

    _register("test.branch", TextArguments, Branch())
    _register("test.join", JoinArguments, Join())
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.branch",
                arguments={"text": LiteralArgument(value="left")},
            ),
            ExecutionTask(
                id="task_2",
                capability="test.branch",
                arguments={"text": LiteralArgument(value="right")},
            ),
            ExecutionTask(
                id="task_3",
                capability="test.join",
                depends_on=["task_1", "task_2"],
                arguments={
                    "left": TaskOutputReference(task_id="task_1", path="value"),
                    "right": TaskOutputReference(task_id="task_2", path="value"),
                },
            ),
        ]
    )

    result = ExecutionPlanExecutor(max_concurrency=2).execute(plan)

    assert set(calls[:2]) == {"start:left", "start:right"}
    assert calls[-1] == "join"
    assert result.task_states["task_3"].result == "left+right"


def test_failure_skips_dependents_but_independent_branches_continue() -> None:
    failing = FailingExecutor()
    independent = RecordingExecutor({"ok": True})
    _register("test.fail", EmptyArguments, failing)
    _register("test.independent", EmptyArguments, independent)
    _register("test.join", JoinArguments, RecordingExecutor("unused"))
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.fail"),
            ExecutionTask(id="task_2", capability="test.independent"),
            ExecutionTask(
                id="task_3",
                capability="test.join",
                depends_on=["task_1", "task_2"],
            ),
            ExecutionTask(id="task_4", capability="test.independent"),
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_1"].status is TaskStatus.FAILED
    assert result.task_states["task_1"].error == "Task execution failed."
    assert result.task_states["task_2"].status is TaskStatus.SUCCEEDED
    assert result.task_states["task_3"].status is TaskStatus.SKIPPED
    assert result.task_states["task_4"].status is TaskStatus.SUCCEEDED
    assert failing.calls == 1
    assert len(independent.calls) == 2


def test_output_reference_supports_direct_dict_model_and_list_paths() -> None:
    _register("test.dict", EmptyArguments, RecordingExecutor({"items": ["abc"]}))
    _register(
        "test.model",
        EmptyArguments,
        RecordingExecutor(ModelOutput(document_id="model-id")),
    )
    first_consumer = RecordingExecutor({"ok": "first"})
    second_consumer = RecordingExecutor({"ok": "second"})
    _register("test.consume.first", TextArguments, first_consumer)
    _register("test.consume.second", TextArguments, second_consumer)
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.dict"),
            ExecutionTask(id="task_2", capability="test.model"),
            ExecutionTask(
                id="task_3",
                capability="test.consume.first",
                depends_on=["task_1"],
                arguments={
                    "text": TaskOutputReference(task_id="task_1", path="items.0")
                },
            ),
            ExecutionTask(
                id="task_4",
                capability="test.consume.second",
                depends_on=["task_2"],
                arguments={
                    "text": TaskOutputReference(task_id="task_2", path="document_id")
                },
            ),
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_3"].status is TaskStatus.SUCCEEDED
    assert result.task_states["task_4"].status is TaskStatus.SUCCEEDED
    assert first_consumer.calls == [{"text": "abc"}]
    assert second_consumer.calls == [{"text": "model-id"}]


def test_invalid_output_path_fails_downstream_task_deterministically() -> None:
    consumer = RecordingExecutor({"unused": True})
    _register("test.produce", EmptyArguments, RecordingExecutor({"known": "value"}))
    _register("test.consume", TextArguments, consumer)
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.produce"),
            ExecutionTask(
                id="task_2",
                capability="test.consume",
                depends_on=["task_1"],
                arguments={
                    "text": TaskOutputReference(task_id="task_1", path="missing")
                },
            ),
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_2"].status is TaskStatus.FAILED
    assert result.task_states["task_2"].error == "Task arguments could not be resolved."
    assert consumer.calls == []


def test_resolved_arguments_are_validated_after_reference_substitution() -> None:
    consumer = RecordingExecutor({"unused": True})
    _register("test.produce", EmptyArguments, RecordingExecutor({"value": "not-int"}))
    _register("test.consume", ValueArguments, consumer)
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.produce"),
            ExecutionTask(
                id="task_2",
                capability="test.consume",
                depends_on=["task_1"],
                arguments={
                    "value": TaskOutputReference(task_id="task_1", path="value")
                },
            ),
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_2"].status is TaskStatus.FAILED
    assert result.task_states["task_2"].error == "Task arguments failed validation."
    assert consumer.calls == []


def test_each_task_executes_once_and_references_do_not_rerun_upstream() -> None:
    producer = RecordingExecutor({"value": 3})
    left = RecordingExecutor({"ok": "left"})
    right = RecordingExecutor({"ok": "right"})
    _register("test.produce", EmptyArguments, producer)
    _register("test.left", ValueArguments, left)
    _register("test.right", ValueArguments, right)
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.produce"),
            ExecutionTask(
                id="task_2",
                capability="test.left",
                depends_on=["task_1"],
                arguments={
                    "value": TaskOutputReference(task_id="task_1", path="value")
                },
            ),
            ExecutionTask(
                id="task_3",
                capability="test.right",
                depends_on=["task_1"],
                arguments={
                    "value": TaskOutputReference(task_id="task_1", path="value")
                },
            ),
        ]
    )

    ExecutionPlanExecutor().execute(plan)

    assert producer.calls == [{}]
    assert left.calls == [{"value": 3}]
    assert right.calls == [{"value": 3}]


def test_runtime_module_does_not_call_llm_or_response_components() -> None:
    source = inspect.getsource(execution_module)

    assert "Planner" not in source
    assert "ToolSelector" not in source
    assert "OpenAI" not in source
    assert "ResponseGenerator" not in source
