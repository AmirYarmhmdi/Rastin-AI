"""File guide.

- Use: Contains security-boundary tests for tool selection and execution.
- Usage: Run this file with pytest when checking tool execution authorization.
- Duties: Proves selectors cannot bypass registry and schema validation.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.graph, rastin_ai.agent.schemas, and
  rastin_ai.tools.registry.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from rastin_ai.agent.graph import create_agent_graph
from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    ToolSelection,
)
from rastin_ai.tools.registry import list_tools, register_tool


class ExpressionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str


class RecordingExpressionTool:
    name = "security_expression_tool"
    description = "Records an expression without evaluating it."
    args_schema = ExpressionArguments

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return kwargs["expression"]


class FakePlanner:
    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan

    def create_plan(
        self,
        *,
        user_query: str,
        available_capabilities: object,
    ) -> ExecutionPlan:
        return self.plan


class FakeToolSelector:
    def __init__(self, selection: ToolSelection) -> None:
        self.selection = selection

    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: object,
    ) -> ToolSelection:
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


def test_unknown_tool_names_cannot_execute() -> None:
    tool = RecordingExpressionTool()
    register_tool(tool.name, tool)
    graph = create_agent_graph(
        planner=FakePlanner(
            ExecutionPlan(
                tasks=[
                    ExecutionTask(
                        id="task_1",
                        capability="unknown_security_tool",
                    )
                ]
            )
        ),
        tool_selector=FakeToolSelector(
            ToolSelection(tool_name="unknown_security_tool", arguments={})
        ),
        response_generator=FakeResponseGenerator("unused"),
    )

    result = graph.invoke({"user_query": "Run the unknown tool."})

    assert tool.calls == []
    assert (
        result["response"]
        == "Unable to complete request: ExecutionPlan failed capability validation."
    )


def test_invalid_arguments_cannot_reach_tool_execution() -> None:
    tool = RecordingExpressionTool()
    register_tool(tool.name, tool)
    graph = create_agent_graph(
        planner=FakePlanner(
            ExecutionPlan(
                tasks=[
                    ExecutionTask(
                        id="task_1",
                        capability=tool.name,
                        arguments={"expression": LiteralArgument(value=123)},
                    )
                ]
            )
        ),
        tool_selector=FakeToolSelector(
            ToolSelection(tool_name=tool.name, arguments={"expression": 123})
        ),
        response_generator=FakeResponseGenerator("The planned task failed."),
    )

    result = graph.invoke({"user_query": "Record the expression."})

    assert tool.calls == []
    assert result["response"] == "The planned task failed."
    assert result["execution_result"].task_states["task_1"].error == (
        "Task arguments failed validation."
    )


def test_selector_cannot_register_tools() -> None:
    tool = RecordingExpressionTool()
    register_tool(tool.name, tool)
    before = list_tools()
    graph = create_agent_graph(
        planner=FakePlanner(
            ExecutionPlan(
                tasks=[
                    ExecutionTask(
                        id="task_1",
                        capability=tool.name,
                        arguments={"expression": LiteralArgument(value="2 + 2")},
                    )
                ]
            )
        ),
        tool_selector=FakeToolSelector(
            ToolSelection(tool_name=tool.name, arguments={"expression": "2 + 2"})
        ),
        response_generator=FakeResponseGenerator("Recorded."),
    )

    graph.invoke({"user_query": "Record the expression."})

    assert list_tools() == before


def test_argument_strings_are_not_evaluated_during_selection() -> None:
    tool = RecordingExpressionTool()
    register_tool(tool.name, tool)
    expression = "__import__('os').system('echo unsafe')"
    generator = FakeResponseGenerator("Recorded without evaluating.")
    graph = create_agent_graph(
        planner=FakePlanner(
            ExecutionPlan(
                tasks=[
                    ExecutionTask(
                        id="task_1",
                        capability=tool.name,
                        arguments={"expression": LiteralArgument(value=expression)},
                    )
                ]
            )
        ),
        tool_selector=FakeToolSelector(
            ToolSelection(tool_name=tool.name, arguments={"expression": expression})
        ),
        response_generator=generator,
    )

    result = graph.invoke({"user_query": "Record the expression."})

    assert tool.calls == [{"expression": expression}]
    assert result["tool_result"] == expression
    assert generator.calls[0]["tool_result"] == expression
