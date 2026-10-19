"""File guide.

- Use: Defines the LangGraph tool-selection node wrapper.
- Usage: Import create_tool_selection_node or tool_selection_node from
  rastin_ai.agent.nodes.tool_selection.
- Duties: Calls an injected selector and validates tool names and arguments.
- Depends on: Project modules: rastin_ai.agent.exceptions,
  rastin_ai.agent.state, rastin_ai.agent.tool_selector, and
  rastin_ai.tools.registry.
"""

from collections.abc import Callable
from typing import Any

from rastin_ai.agent.exceptions import ToolSelectorError
from rastin_ai.agent.schemas import (
    ExecutionPlan,
    LiteralArgument,
    TaskOutputReference,
)
from rastin_ai.agent.state import AgentState
from rastin_ai.agent.tool_selector import OpenAIToolSelector, ToolSelector
from rastin_ai.tools.registry import (
    ToolArgumentValidationError,
    UnknownToolError,
    get_tool,
    get_tool_definitions,
    validate_tool_arguments,
)


def create_tool_selection_node(
    tool_selector: ToolSelector,
) -> Callable[[AgentState], dict[str, Any]]:
    def _tool_selection_node(state: AgentState) -> dict[str, Any]:
        return tool_selection_node(state, tool_selector=tool_selector)

    return _tool_selection_node


def tool_selection_node(
    state: AgentState, *, tool_selector: ToolSelector | None = None
) -> dict[str, Any]:
    if state.get("error"):
        return {"selected_tool": None, "tool_arguments": {}}

    execution_plan = state.get("execution_plan")
    if execution_plan is not None:
        return _select_from_execution_plan(execution_plan)

    if state.get("requires_tool") is False:
        return {"selected_tool": None, "tool_arguments": {}, "error": None}

    user_query = state.get("user_query", "")
    available_tools = get_tool_definitions()
    if not available_tools:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "No registered tools are available.",
        }

    active_selector = tool_selector or OpenAIToolSelector()

    try:
        selection = active_selector.select_tool(
            user_query=user_query,
            plan=state.get("plan", []),
            available_tools=available_tools,
        )
    except ToolSelectorError as exc:
        return {"selected_tool": None, "tool_arguments": {}, "error": str(exc)}
    except Exception:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "Tool selector failed unexpectedly.",
        }

    if selection.tool_name is None:
        return {"selected_tool": None, "tool_arguments": {}, "error": None}

    try:
        get_tool(selection.tool_name)
        validated_arguments = validate_tool_arguments(
            selection.tool_name,
            selection.arguments,
        )
    except UnknownToolError:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "Selected tool is not available.",
        }
    except ToolArgumentValidationError:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "Tool arguments failed validation.",
        }

    return {
        "selected_tool": selection.tool_name,
        "tool_arguments": validated_arguments,
        "error": None,
    }


def _select_from_execution_plan(execution_plan: ExecutionPlan) -> dict[str, Any]:
    if not execution_plan.tasks:
        return {"selected_tool": None, "tool_arguments": {}, "error": None}
    if len(execution_plan.tasks) > 1:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "ExecutionPlan DAG execution is not implemented yet.",
        }

    task = execution_plan.tasks[0]
    literal_arguments: dict[str, Any] = {}
    for name, argument in task.arguments.items():
        if isinstance(argument, TaskOutputReference):
            return {
                "selected_tool": None,
                "tool_arguments": {},
                "error": (
                    "ExecutionPlan task-output execution is not implemented yet."
                ),
            }
        if isinstance(argument, LiteralArgument):
            literal_arguments[name] = argument.value

    try:
        get_tool(task.capability)
        validated_arguments = validate_tool_arguments(
            task.capability,
            literal_arguments,
        )
    except UnknownToolError:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "Selected tool is not available.",
        }
    except ToolArgumentValidationError:
        return {
            "selected_tool": None,
            "tool_arguments": {},
            "error": "Tool arguments failed validation.",
        }

    return {
        "selected_tool": task.capability,
        "tool_arguments": validated_arguments,
        "error": None,
    }
