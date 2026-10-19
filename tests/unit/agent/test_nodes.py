"""File guide.

- Use: Contains unit tests for initial agent node behavior.
- Usage: Run this file with pytest when checking agent orchestration nodes.
- Duties: Builds small states, calls deterministic nodes, and checks results.
- Depends on: Project modules: rastin_ai.agent.nodes and
  rastin_ai.tools.registry.
"""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from rastin_ai.agent.exceptions import ResponseGenerationError
from rastin_ai.agent.execution import (
    ExecutionPlanExecutor,
    ExecutionResult,
    TaskStatus,
)
from rastin_ai.agent.nodes import (
    execute_plan_node,
    planner_node,
    response_generation_node,
    tool_execution_node,
    tool_selection_node,
)
from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    TaskOutputReference,
    ToolSelection,
)
from rastin_ai.tools.registry import register_tool


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValueArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class RecordingTool:
    name = "recording_test_tool"
    description = "Records its arguments."
    args_schema = ValueArguments

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return {"ok": True, "arguments": kwargs}


class FakePlanner:
    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan
        self.calls: list[dict[str, object]] = []

    def create_plan(
        self,
        *,
        user_query: str,
        available_capabilities: object,
    ) -> ExecutionPlan:
        self.calls.append(
            {
                "user_query": user_query,
                "available_capabilities": available_capabilities,
            }
        )
        return self.plan


class FailingPlanner:
    def create_plan(
        self,
        *,
        user_query: str,
        available_capabilities: object,
    ) -> ExecutionPlan:
        raise RuntimeError("provider exploded with sensitive internals")


class FakeToolSelector:
    def __init__(self, selection: ToolSelection) -> None:
        self.selection = selection
        self.calls: list[dict[str, object]] = []

    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: object,
    ) -> ToolSelection:
        self.calls.append(
            {
                "user_query": user_query,
                "plan": plan,
                "available_tools": available_tools,
            }
        )
        return self.selection


class FailingToolSelector:
    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: object,
    ) -> ToolSelection:
        raise RuntimeError("provider exploded with sensitive internals")


class RecordingPlanExecutor(ExecutionPlanExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.plans: list[ExecutionPlan] = []

    def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        self.plans.append(plan)
        return super().execute(plan)


class FakeResponseGenerator:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_response(
        self,
        *,
        user_query: str,
        plan: list[str],
        execution_plan: ExecutionPlan | None = None,
        execution_result: object | None = None,
        tool_name: str | None = None,
        tool_result: Any = None,
        error: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "user_query": user_query,
                "plan": plan,
                "execution_plan": execution_plan,
                "execution_result": execution_result,
                "tool_name": tool_name,
                "tool_result": tool_result,
                "error": error,
            }
        )
        return self.response


class FailingResponseGenerator:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc or RuntimeError("provider exploded with sensitive internals")

    def generate_response(
        self,
        *,
        user_query: str,
        plan: list[str],
        execution_plan: ExecutionPlan | None = None,
        execution_result: object | None = None,
        tool_name: str | None = None,
        tool_result: Any = None,
        error: str | None = None,
    ) -> str:
        raise self.exc


def test_planner_returns_structured_plan_update() -> None:
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="recording_test_tool",
                arguments={"value": LiteralArgument(value=42)},
            )
        ]
    )
    planner = FakePlanner(execution_plan)

    result = planner_node({"user_query": "Summarize this request."}, planner=planner)

    assert result == {
        "execution_plan": execution_plan,
        "plan": ["task_1: recording_test_tool"],
        "requires_tool": True,
        "error": None,
    }


def test_planner_receives_user_query_once() -> None:
    planner = FakePlanner(ExecutionPlan())

    planner_node({"user_query": "Calculate 2 + 2"}, planner=planner)

    assert planner.calls[0]["user_query"] == "Calculate 2 + 2"
    assert "available_capabilities" in planner.calls[0]


def test_planner_handles_unexpected_errors_predictably() -> None:
    result = planner_node({"user_query": "Calculate 2 + 2"}, planner=FailingPlanner())

    assert result == {
        "execution_plan": ExecutionPlan(),
        "plan": [],
        "requires_tool": False,
        "error": "Planner failed unexpectedly.",
    }


def test_planner_rejects_empty_user_query_without_calling_planner() -> None:
    planner = FakePlanner(ExecutionPlan())

    result = planner_node({"user_query": " "}, planner=planner)

    assert result == {
        "execution_plan": ExecutionPlan(),
        "plan": [],
        "requires_tool": False,
        "error": "Planner requires a non-empty user_query.",
    }
    assert planner.calls == []


def test_tool_selector_skips_when_planner_says_no_tool_required() -> None:
    selector = FakeToolSelector(ToolSelection(tool_name="unused", arguments={}))

    result = tool_selection_node(
        {
            "user_query": "Tell me what this project does.",
            "requires_tool": False,
        },
        tool_selector=selector,
    )

    assert result == {"selected_tool": None, "tool_arguments": {}, "error": None}
    assert selector.calls == []


def test_tool_selector_uses_execution_plan_without_reselecting_capability() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    selector = FakeToolSelector(ToolSelection(tool_name="should_not_run", arguments={}))
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability=tool.name,
                arguments={"value": LiteralArgument(value="42")},
            )
        ]
    )

    result = tool_selection_node(
        {"user_query": "Record this value.", "execution_plan": execution_plan},
        tool_selector=selector,
    )

    assert result == {
        "selected_tool": tool.name,
        "tool_arguments": {"value": 42},
        "error": None,
    }
    assert selector.calls == []


def test_tool_selector_rejects_multi_task_plan_until_dag_executor_exists() -> None:
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.one"),
            ExecutionTask(id="task_2", capability="test.two"),
        ]
    )

    result = tool_selection_node({"execution_plan": execution_plan})

    assert result == {
        "selected_tool": None,
        "tool_arguments": {},
        "error": "ExecutionPlan DAG execution is not implemented yet.",
    }


def test_tool_selector_rejects_task_output_reference_until_dag_executor_exists() -> (
    None
):
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.one"),
            ExecutionTask(
                id="task_2",
                capability="test.two",
                arguments={"source": TaskOutputReference(task_id="task_1")},
                depends_on=["task_1"],
            ),
        ]
    )

    result = tool_selection_node({"execution_plan": execution_plan})

    assert result == {
        "selected_tool": None,
        "tool_arguments": {},
        "error": "ExecutionPlan DAG execution is not implemented yet.",
    }


def test_tool_selector_preserves_planner_error_boundary() -> None:
    result = tool_selection_node(
        {"user_query": "Calculate 2 + 2", "error": "Planner failed unexpectedly."}
    )

    assert result == {"selected_tool": None, "tool_arguments": {}}


def test_tool_selector_valid_selection_writes_validated_arguments() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    selector = FakeToolSelector(
        ToolSelection(tool_name=tool.name, arguments={"value": "42"})
    )

    result = tool_selection_node(
        {
            "user_query": "Record this value.",
            "plan": ["Use a deterministic recorder."],
            "requires_tool": True,
        },
        tool_selector=selector,
    )

    assert result == {
        "selected_tool": tool.name,
        "tool_arguments": {"value": 42},
        "error": None,
    }
    assert len(selector.calls) == 1


def test_tool_selector_no_tool_selection_writes_no_tool() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    selector = FakeToolSelector(ToolSelection(tool_name=None, arguments={}))

    result = tool_selection_node(
        {
            "user_query": "Explain this.",
            "plan": ["Respond directly."],
            "requires_tool": True,
        },
        tool_selector=selector,
    )

    assert result == {"selected_tool": None, "tool_arguments": {}, "error": None}


def test_tool_selector_rejects_unregistered_tool() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    selector = FakeToolSelector(
        ToolSelection(tool_name="hallucinated_tool", arguments={})
    )

    result = tool_selection_node(
        {
            "user_query": "Do the thing.",
            "plan": ["Use a deterministic tool."],
            "requires_tool": True,
        },
        tool_selector=selector,
    )

    assert result == {
        "selected_tool": None,
        "tool_arguments": {},
        "error": "Selected tool is not available.",
    }


@pytest.mark.parametrize(
    "arguments", ({}, {"value": "not-an-int"}, {"value": 1, "x": 2})
)
def test_tool_selector_rejects_invalid_arguments(arguments: dict[str, object]) -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    selector = FakeToolSelector(ToolSelection(tool_name=tool.name, arguments=arguments))

    result = tool_selection_node(
        {
            "user_query": "Record this value.",
            "plan": ["Use a deterministic recorder."],
            "requires_tool": True,
        },
        tool_selector=selector,
    )

    assert result == {
        "selected_tool": None,
        "tool_arguments": {},
        "error": "Tool arguments failed validation.",
    }


def test_tool_selector_exception_is_sanitized() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)

    result = tool_selection_node(
        {
            "user_query": "Record this value.",
            "plan": ["Use a deterministic recorder."],
            "requires_tool": True,
        },
        tool_selector=FailingToolSelector(),
    )

    assert result == {
        "selected_tool": None,
        "tool_arguments": {},
        "error": "Tool selector failed unexpectedly.",
    }


def test_execute_plan_node_runs_single_task_through_plan_executor() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    executor = RecordingPlanExecutor()
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability=tool.name,
                arguments={"value": LiteralArgument(value="42")},
            )
        ]
    )

    result = execute_plan_node({"execution_plan": execution_plan}, executor=executor)

    assert executor.plans == [execution_plan]
    assert result["error"] is None
    assert result["execution_result"].task_states["task_1"].status is (
        TaskStatus.SUCCEEDED
    )
    assert result["execution_result"].task_states["task_1"].result == {
        "ok": True,
        "arguments": {"value": 42},
    }
    assert tool.calls == [{"value": 42}]


def test_execute_plan_node_runs_multi_task_plan_through_same_executor() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    executor = RecordingPlanExecutor()
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability=tool.name,
                arguments={"value": LiteralArgument(value=1)},
            ),
            ExecutionTask(
                id="task_2",
                capability=tool.name,
                arguments={"value": LiteralArgument(value=2)},
            ),
        ]
    )

    result = execute_plan_node({"execution_plan": execution_plan}, executor=executor)

    assert executor.plans == [execution_plan]
    assert result["error"] is None
    assert {
        task_id: task_state.status
        for task_id, task_state in result["execution_result"].task_states.items()
    } == {
        "task_1": TaskStatus.SUCCEEDED,
        "task_2": TaskStatus.SUCCEEDED,
    }
    assert sorted(tool.calls, key=lambda call: call["value"]) == [
        {"value": 1},
        {"value": 2},
    ]


def test_execute_plan_node_rejects_unavailable_capability_before_runtime() -> None:
    execution_plan = ExecutionPlan(
        tasks=[ExecutionTask(id="task_1", capability="missing.capability")]
    )

    result = execute_plan_node({"execution_plan": execution_plan})

    assert result == {"error": "ExecutionPlan failed capability validation."}


def test_tool_execution_does_nothing_safely_when_no_tool_is_selected() -> None:
    result = tool_execution_node({"selected_tool": None, "tool_arguments": {}})

    assert result == {}


def test_registered_tool_is_executed_with_supplied_arguments() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)

    result = tool_execution_node(
        {
            "selected_tool": tool.name,
            "tool_arguments": {"value": 42},
        }
    )

    assert result == {
        "tool_result": {"ok": True, "arguments": {"value": 42}},
        "error": None,
    }
    assert tool.calls == [{"value": 42}]


def test_unknown_tool_produces_controlled_error_behavior() -> None:
    result = tool_execution_node(
        {"selected_tool": "missing_test_tool", "tool_arguments": {}}
    )

    assert result == {"error": "Unknown tool: missing_test_tool"}


def test_response_node_uses_generator_for_successful_tool_result() -> None:
    generator = FakeResponseGenerator("The result is 4.")

    result = response_generation_node(
        {
            "user_query": "Calculate 2 + 2",
            "plan": ["Use a deterministic calculator."],
            "selected_tool": "calculator",
            "tool_result": 4,
            "error": None,
        },
        response_generator=generator,
    )

    assert result == {"response": "The result is 4."}
    assert generator.calls == [
        {
            "user_query": "Calculate 2 + 2",
            "plan": ["Use a deterministic calculator."],
            "execution_plan": None,
            "execution_result": None,
            "tool_name": "calculator",
            "tool_result": 4,
            "error": None,
        }
    ]


def test_response_node_uses_generator_for_no_tool_case() -> None:
    generator = FakeResponseGenerator("Agents orchestrate work.")

    result = response_generation_node(
        {
            "user_query": "Explain agents.",
            "plan": ["Answer directly."],
            "selected_tool": None,
            "error": None,
        },
        response_generator=generator,
    )

    assert result == {"response": "Agents orchestrate work."}
    assert generator.calls == [
        {
            "user_query": "Explain agents.",
            "plan": ["Answer directly."],
            "execution_plan": None,
            "execution_result": None,
            "tool_name": None,
            "tool_result": None,
            "error": None,
        }
    ]


def test_response_node_passes_execution_result_failures_to_generator() -> None:
    tool = RecordingTool()
    register_tool(tool.name, tool)
    execution_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability=tool.name,
                arguments={"value": LiteralArgument(value="not-an-int")},
            )
        ]
    )
    execution_update = execute_plan_node({"execution_plan": execution_plan})
    generator = FakeResponseGenerator("The planned task did not complete.")

    result = response_generation_node(
        {
            "user_query": "Record this value.",
            "execution_plan": execution_plan,
            "execution_result": execution_update["execution_result"],
            "plan": ["task_1: recording_test_tool"],
            "error": None,
        },
        response_generator=generator,
    )

    assert result == {"response": "The planned task did not complete."}
    assert (
        generator.calls[0]["execution_result"] == execution_update["execution_result"]
    )
    assert generator.calls[0]["error"] == (
        "One or more planned tasks did not complete successfully."
    )
    assert tool.calls == []


def test_response_node_fast_paths_workflow_error_without_generator() -> None:
    generator = FakeResponseGenerator("unused")

    result = response_generation_node(
        {"error": "Unknown tool: missing"},
        response_generator=generator,
    )

    assert result == {"response": "Unable to complete request: Unknown tool: missing"}
    assert generator.calls == []


def test_response_node_handles_response_generation_error() -> None:
    result = response_generation_node(
        {"user_query": "Explain agents."},
        response_generator=FailingResponseGenerator(
            ResponseGenerationError("OpenAI response generation request failed.")
        ),
    )

    assert result == {
        "response": (
            "Unable to complete request: OpenAI response generation request failed."
        )
    }


def test_response_node_sanitizes_unexpected_generator_exception() -> None:
    result = response_generation_node(
        {"user_query": "Explain agents."},
        response_generator=FailingResponseGenerator(),
    )

    assert result == {"response": "Response generation failed unexpectedly."}
