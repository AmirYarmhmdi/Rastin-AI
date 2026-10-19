"""File guide.

- Use: Builds the LangGraph workflow for deterministic plan execution.
- Usage: Import create_agent_graph from rastin_ai.agent.graph.
- Duties: Wires planner, deterministic plan execution, and response generation.
- Depends on: External packages: langgraph. Project modules:
  rastin_ai.agent.nodes, rastin_ai.agent.state, and
  rastin_ai.observability.
"""

from typing import Any

from langgraph.graph import END, START, StateGraph

import rastin_ai.observability as observability
from rastin_ai.agent.execution import ExecutionPlanExecutor
from rastin_ai.agent.nodes import (
    create_execute_plan_node,
    create_planner_node,
    create_response_generation_node,
)
from rastin_ai.agent.planner import OpenAIPlanner, Planner
from rastin_ai.agent.response_generator import (
    OpenAIResponseGenerator,
    ResponseGenerator,
)
from rastin_ai.agent.state import AgentState
from rastin_ai.agent.tool_selector import ToolSelector
from rastin_ai.core.config import Settings


def create_agent_graph(
    *,
    planner: Planner | None = None,
    tool_selector: ToolSelector | None = None,
    execution_plan_executor: ExecutionPlanExecutor | None = None,
    response_generator: ResponseGenerator | None = None,
    settings: Settings | None = None,
):
    builder = StateGraph(AgentState)
    resolved_planner = planner or OpenAIPlanner()
    # Keep the legacy selector parameter for compatibility, but do not place it on
    # the ExecutionPlan path.
    _ = tool_selector
    resolved_executor = execution_plan_executor or ExecutionPlanExecutor()
    resolved_response_generator = response_generator or OpenAIResponseGenerator()

    builder.add_node("planner", create_planner_node(resolved_planner))
    builder.add_node("execute_plan", create_execute_plan_node(resolved_executor))
    builder.add_node(
        "response_generation",
        create_response_generation_node(resolved_response_generator),
    )

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "execute_plan")
    builder.add_edge("execute_plan", "response_generation")
    builder.add_edge("response_generation", END)

    return ObservableAgentGraph(builder.compile(), settings=settings)


class ObservableAgentGraph:
    """Thin wrapper that adds trace config at the graph invocation boundary."""

    def __init__(self, graph: Any, *, settings: Settings | None = None) -> None:
        self._graph = graph
        self._settings = settings

    def invoke(
        self,
        input: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        workflow_metadata = {
            **_workflow_metadata(self._settings),
            **_config_metadata(config),
        }
        with observability.observed_workflow(
            name="agent.workflow",
            input=_observed_graph_input(input),
            metadata=workflow_metadata,
            session_id=_metadata_string(workflow_metadata.get("session_id")),
            settings=self._settings,
        ) as observation:
            result = self._graph.invoke(
                input,
                config=observability.with_langgraph_callbacks(
                    config,
                    settings=self._settings,
                ),
                **kwargs,
            )
            observability.safe_update_observation(
                observation,
                output=_observed_graph_output(result),
            )
            return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


def _workflow_metadata(settings: Settings | None) -> dict[str, str]:
    if settings is None:
        return {"component": "agent"}
    return {
        "component": "agent",
        "environment": settings.ENVIRONMENT,
        "app_version": settings.APP_VERSION,
    }


def _config_metadata(config: dict[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {}
    metadata = config.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _metadata_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _observed_graph_input(input: Any) -> dict[str, Any]:
    if isinstance(input, dict):
        user_query = input.get("user_query")
        return {
            "keys": sorted(str(key) for key in input),
            "user_query_chars": (
                len(user_query) if isinstance(user_query, str) else None
            ),
        }
    return {"input_type": type(input).__name__}


def _observed_graph_output(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return {
            "keys": sorted(str(key) for key in result),
            "has_error": bool(result.get("error")),
            "plan_step_count": len(result.get("plan") or ()),
            "has_response": bool(result.get("response")),
        }
    return {"output_type": type(result).__name__}
