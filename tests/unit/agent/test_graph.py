"""File guide.

- Use: Contains unit tests for initial LangGraph workflow behavior.
- Usage: Run this file with pytest when checking complete agent graph paths.
- Duties: Registers test tools, invokes the graph, and checks path outputs.
- Depends on: Project modules: rastin_ai.agent.graph and
  rastin_ai.tools.registry.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from rastin_ai.agent.execution import TaskStatus
from rastin_ai.agent.graph import create_agent_graph
from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    ToolSelection,
)
from rastin_ai.skills import CapabilityDefinition
from rastin_ai.tools.registry import register_capability


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


class FakeToolSelector:
    def __init__(self, selection: ToolSelection) -> None:
        self.selection = selection
        self.calls = 0

    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: object,
    ) -> ToolSelection:
        self.calls += 1
        return self.selection


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


class CalculatorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str


class CalculatorTool:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return {"expression": kwargs["expression"], "value": 4}


def test_graph_runs_no_tool_path() -> None:
    planner = FakePlanner(ExecutionPlan(response_strategy="Answer directly."))
    selector = FakeToolSelector(
        ToolSelection(tool_name="unused_selector_should_not_run", arguments={})
    )
    generator = FakeResponseGenerator("The repository coordinates AI workflows.")
    graph = create_agent_graph(
        planner=planner,
        tool_selector=selector,
        response_generator=generator,
    )

    result = graph.invoke({"user_query": "Explain the repository purpose."})

    assert result["selected_tool"] is None
    assert result["requires_tool"] is False
    assert result["tool_arguments"] == {}
    assert result["execution_result"].task_states == {}
    assert "tool_result" not in result
    assert result["response"] == "The repository coordinates AI workflows."
    assert planner.calls[0]["user_query"] == "Explain the repository purpose."
    assert selector.calls == 0
    assert generator.calls == [
        {
            "user_query": "Explain the repository purpose.",
            "plan": [],
            "execution_plan": planner.plan,
            "execution_result": result["execution_result"],
            "tool_name": None,
            "tool_result": None,
            "error": None,
        }
    ]


def test_graph_runs_tool_execution_path() -> None:
    planner = FakePlanner(
        ExecutionPlan(
            tasks=[
                ExecutionTask(
                    id="task_1",
                    capability="agent.calculator",
                    arguments={"expression": LiteralArgument(value="Calculate 2 + 2")},
                )
            ]
        )
    )
    selector = FakeToolSelector(
        ToolSelection(
            tool_name="agent.calculator",
            arguments={"expression": "Calculate 2 + 2"},
        )
    )
    calculator = CalculatorTool()
    generator = FakeResponseGenerator("The result is 4.")
    register_capability(
        CapabilityDefinition(
            name="agent.calculator",
            description="Evaluate a mathematical expression.",
            input_schema=CalculatorArguments,
        ),
        calculator,
    )
    graph = create_agent_graph(
        planner=planner,
        tool_selector=selector,
        response_generator=generator,
    )

    result = graph.invoke({"user_query": "Calculate 2 + 2"})

    assert result["selected_tool"] == "agent.calculator"
    assert result["requires_tool"] is True
    assert result["tool_arguments"] == {}
    assert result["tool_result"] == {"expression": "Calculate 2 + 2", "value": 4}
    assert result["execution_result"].task_states["task_1"].status is (
        TaskStatus.SUCCEEDED
    )
    assert result["error"] is None
    assert result["response"] == "The result is 4."
    assert planner.calls[0]["user_query"] == "Calculate 2 + 2"
    assert selector.calls == 0
    assert calculator.calls == [{"expression": "Calculate 2 + 2"}]
    assert len(generator.calls) == 1
    assert generator.calls == [
        {
            "user_query": "Calculate 2 + 2",
            "plan": ["task_1: agent.calculator"],
            "execution_plan": planner.plan,
            "execution_result": result["execution_result"],
            "tool_name": "agent.calculator",
            "tool_result": {"expression": "Calculate 2 + 2", "value": 4},
            "error": None,
        }
    ]


def test_graph_blocks_invalid_arguments_before_tool_execution() -> None:
    calculator = CalculatorTool()
    generator = FakeResponseGenerator("The calculator arguments were invalid.")
    register_capability(
        CapabilityDefinition(
            name="agent.calculator.invalid",
            description="Evaluate a mathematical expression.",
            input_schema=CalculatorArguments,
        ),
        calculator,
    )
    graph = create_agent_graph(
        planner=FakePlanner(
            ExecutionPlan(
                tasks=[
                    ExecutionTask(
                        id="task_1",
                        capability="agent.calculator.invalid",
                        arguments={"expression": LiteralArgument(value=123)},
                    )
                ]
            )
        ),
        tool_selector=FakeToolSelector(
            ToolSelection(
                tool_name="agent.calculator.invalid",
                arguments={"expression": 123},
            )
        ),
        response_generator=generator,
    )

    result = graph.invoke({"user_query": "Calculate 2 + 2"})

    assert result["selected_tool"] == "agent.calculator.invalid"
    assert result["tool_arguments"] == {}
    assert "tool_result" not in result
    assert result["execution_result"].task_states["task_1"].status is TaskStatus.FAILED
    assert result["execution_result"].task_states["task_1"].error == (
        "Task arguments failed validation."
    )
    assert result["response"] == "The calculator arguments were invalid."
    assert calculator.calls == []
    assert generator.calls[0]["error"] == (
        "One or more planned tasks did not complete successfully."
    )
