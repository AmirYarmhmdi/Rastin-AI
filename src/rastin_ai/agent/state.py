"""File guide.

- Use: Defines the semantic state shared across agent workflow nodes.
- Usage: Import AgentState from rastin_ai.agent.state.
- Duties: Keeps LangGraph state focused on orchestration data.
- Depends on: External packages: typing. Project modules:
  rastin_ai.agent.execution and rastin_ai.agent.schemas.
"""

from typing import Any, TypedDict

from rastin_ai.agent.execution import ExecutionResult
from rastin_ai.agent.schemas import ExecutionPlan


class AgentState(TypedDict, total=False):
    user_query: str
    execution_plan: ExecutionPlan
    execution_result: ExecutionResult
    # Compatibility fields derived from execution_plan/execution_result.
    plan: list[str]
    requires_tool: bool
    selected_tool: str | None
    tool_arguments: dict[str, Any]
    tool_result: Any
    response: str
    error: str | None
