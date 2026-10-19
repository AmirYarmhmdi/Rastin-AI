"""File guide.

- Use: Defines the LangGraph response-generation node wrapper.
- Usage: Import create_response_generation_node or response_generation_node from
  rastin_ai.agent.nodes.response.
- Duties: Calls an injected response generator for final user-facing output.
- Depends on: Project modules: rastin_ai.agent.exceptions,
  rastin_ai.agent.response_generator, and rastin_ai.agent.state.
"""

from collections.abc import Callable

from rastin_ai.agent.exceptions import ResponseGenerationError
from rastin_ai.agent.execution import ExecutionResult, TaskStatus
from rastin_ai.agent.response_generator import (
    OpenAIResponseGenerator,
    ResponseGenerator,
)
from rastin_ai.agent.state import AgentState


def create_response_generation_node(
    response_generator: ResponseGenerator,
) -> Callable[[AgentState], dict[str, str]]:
    def _response_generation_node(state: AgentState) -> dict[str, str]:
        return response_generation_node(
            state,
            response_generator=response_generator,
        )

    return _response_generation_node


def response_generation_node(
    state: AgentState,
    *,
    response_generator: ResponseGenerator | None = None,
) -> dict[str, str]:
    error = state.get("error")
    if error:
        return {"response": f"Unable to complete request: {error}"}

    user_query = state.get("user_query", "")
    active_generator = response_generator or OpenAIResponseGenerator()

    try:
        response = active_generator.generate_response(
            user_query=user_query,
            plan=state.get("plan", []),
            execution_plan=state.get("execution_plan"),
            execution_result=state.get("execution_result"),
            tool_name=state.get("selected_tool"),
            tool_result=state.get("tool_result"),
            error=_execution_error_summary(state.get("execution_result")),
        )
    except ResponseGenerationError as exc:
        return {"response": f"Unable to complete request: {exc}"}
    except Exception:
        return {"response": "Response generation failed unexpectedly."}

    return {"response": response}


def _execution_error_summary(execution_result: ExecutionResult | None) -> str | None:
    if execution_result is None:
        return None
    if execution_result.error is not None:
        return execution_result.error

    failed_or_skipped = [
        task_state
        for task_state in execution_result.task_states.values()
        if task_state.status in {TaskStatus.FAILED, TaskStatus.SKIPPED}
    ]
    if not failed_or_skipped:
        return None

    return "One or more planned tasks did not complete successfully."
