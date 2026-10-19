"""File guide.

- Use: Defines the LangGraph node for deterministic ExecutionPlan execution.
- Usage: Import create_execute_plan_node or execute_plan_node from
  rastin_ai.agent.nodes.
- Duties: Validates the structured plan and delegates DAG execution to
  ExecutionPlanExecutor.
- Depends on: Project modules: rastin_ai.agent.execution,
  rastin_ai.agent.plan_validation, rastin_ai.agent.state, and
  rastin_ai.tools.registry.
"""

from collections.abc import Callable
from typing import Any

from rastin_ai.agent.execution import (
    ExecutionPlanExecutor,
    ExecutionResult,
    TaskStatus,
)
from rastin_ai.agent.plan_validation import (
    ExecutionPlanValidationError,
    ExecutionPlanValidator,
)
from rastin_ai.agent.schemas import ExecutionPlan
from rastin_ai.agent.state import AgentState
from rastin_ai.tools.registry import get_runtime_skill_registry


def create_execute_plan_node(
    executor: ExecutionPlanExecutor,
) -> Callable[[AgentState], dict[str, Any]]:
    def _execute_plan_node(state: AgentState) -> dict[str, Any]:
        return execute_plan_node(state, executor=executor)

    return _execute_plan_node


def execute_plan_node(
    state: AgentState,
    *,
    executor: ExecutionPlanExecutor | None = None,
) -> dict[str, Any]:
    if state.get("error"):
        return {}

    execution_plan = state.get("execution_plan")
    if execution_plan is None:
        return {"error": "ExecutionPlan is required before execution."}

    try:
        ExecutionPlanValidator().validate(
            execution_plan,
            skill_registry=get_runtime_skill_registry(),
        )
    except ExecutionPlanValidationError:
        return {"error": "ExecutionPlan failed capability validation."}

    active_executor = executor or ExecutionPlanExecutor()
    execution_result = active_executor.execute(execution_plan)

    state_update: dict[str, Any] = {
        "execution_result": execution_result,
        "error": execution_result.error,
    }
    state_update.update(
        _legacy_single_task_projection(execution_plan, execution_result)
    )
    return state_update


def _legacy_single_task_projection(
    execution_plan: ExecutionPlan,
    execution_result: ExecutionResult,
) -> dict[str, Any]:
    if len(execution_plan.tasks) != 1:
        return {
            "selected_tool": None,
            "tool_arguments": {},
        }

    task = execution_plan.tasks[0]
    task_state = execution_result.task_states.get(task.id)
    if task_state is None or task_state.status is not TaskStatus.SUCCEEDED:
        return {
            "selected_tool": task.capability,
            "tool_arguments": {},
        }

    return {
        "selected_tool": task.capability,
        "tool_arguments": {},
        "tool_result": task_state.result,
    }
