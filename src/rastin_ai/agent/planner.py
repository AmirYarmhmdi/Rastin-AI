"""File guide.

- Use: Defines planner interfaces and the OpenAI structured-output adapter.
- Usage: Import Planner and OpenAIPlanner from rastin_ai.agent.planner.
- Duties: Converts user requests into validated structured execution plans.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.exceptions, rastin_ai.agent.schemas,
  rastin_ai.core.config, rastin_ai.observability, and
  rastin_ai.skills.capabilities.
"""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from rastin_ai.agent.exceptions import PlannerError
from rastin_ai.agent.schemas import ExecutionPlan
from rastin_ai.core.config import Settings, get_settings
from rastin_ai.observability import (
    observed_generation,
    sanitize_for_observability,
    usage_details_from_response,
)
from rastin_ai.skills.capabilities import CapabilityPromptView

PLANNER_INSTRUCTIONS = (
    "You are the orchestration planner for Rastin-AI.\n\n"
    "Convert the user's request into a minimal executable plan.\n\n"
    "Use only the executable capabilities provided to you.\n"
    "Represent each executable operation as one task.\n"
    "Use dependencies only when a task requires another task's result.\n"
    "Independent tasks should not depend on each other so the runtime may execute "
    "them concurrently.\n"
    "When one task consumes another task's result, use a structured task-output "
    "reference.\n\n"
    "Do not execute tasks.\n"
    "Do not generate Python or LangGraph code.\n"
    "Do not fabricate capabilities.\n"
    "Do not duplicate equivalent work.\n"
    "Do not answer the user's request.\n\n"
    "Return only the structured ExecutionPlan."
)


class Planner(Protocol):
    def create_plan(
        self,
        *,
        user_query: str,
        available_capabilities: tuple[CapabilityPromptView, ...],
    ) -> ExecutionPlan:
        """Return a structured execution plan for a user request."""


class OpenAIPlannerConfig(BaseModel):
    """Configuration for the OpenAI planner adapter."""

    model: str = Field(min_length=1)
    api_key: str | None = None


class OpenAIPlanner:
    """OpenAI-backed planner that returns validated structured output."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings
        if resolved_settings is None and (
            model is None or (client is None and api_key is None)
        ):
            resolved_settings = get_settings()

        self._config = OpenAIPlannerConfig(
            model=model
            or (
                resolved_settings.OPENAI_PLANNER_MODEL
                if resolved_settings is not None
                else get_settings().OPENAI_PLANNER_MODEL
            ),
            api_key=api_key
            or (
                resolved_settings.OPENAI_API_KEY
                if resolved_settings is not None
                else None
            ),
        )
        self._client = client
        self._settings = resolved_settings

    def create_plan(
        self,
        *,
        user_query: str,
        available_capabilities: tuple[CapabilityPromptView, ...],
    ) -> ExecutionPlan:
        if not user_query.strip():
            msg = "Planner user query must not be empty."
            raise PlannerError(msg)

        planner_input = _build_planner_input(
            user_query=user_query,
            available_capabilities=available_capabilities,
        )

        try:
            with observed_generation(
                name="agent.planner",
                model=self._config.model,
                input={
                    "user_query_chars": len(user_query),
                    "available_capability_count": len(available_capabilities),
                    "text_format": "ExecutionPlan",
                },
                metadata={"component": "planner"},
                settings=self._settings,
            ) as observation:
                response = self._get_client().responses.parse(
                    model=self._config.model,
                    instructions=PLANNER_INSTRUCTIONS,
                    input=planner_input,
                    text_format=ExecutionPlan,
                )
                observation.update(
                    output=sanitize_for_observability(
                        _observed_plan_output(getattr(response, "output_parsed", None))
                    ),
                    usage_details=usage_details_from_response(response),
                )
        except PlannerError:
            raise
        except Exception as exc:
            msg = f"OpenAI planner request failed for model: {self._config.model}"
            raise PlannerError(msg) from exc

        parsed_plan = getattr(response, "output_parsed", None)
        if not isinstance(parsed_plan, ExecutionPlan):
            msg = "OpenAI planner returned no structured plan."
            raise PlannerError(msg)

        return parsed_plan

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()

        return self._client

    def _build_client(self) -> Any:
        if not self._config.api_key:
            msg = "OPENAI_API_KEY must be set before creating an OpenAI planner."
            raise PlannerError(msg)

        try:
            from openai import OpenAI
        except ImportError as exc:
            msg = "The openai package is required for OpenAI planning."
            raise PlannerError(msg) from exc

        return OpenAI(api_key=self._config.api_key)


def _build_planner_input(
    *,
    user_query: str,
    available_capabilities: tuple[CapabilityPromptView, ...],
) -> str:
    capability_payload = [
        capability.model_dump(mode="json") for capability in available_capabilities
    ]
    return (
        f"User request:\n{user_query}\n\n"
        f"Available executable capabilities:\n{capability_payload}"
    )


def _observed_plan_output(value: object) -> dict[str, object]:
    if isinstance(value, ExecutionPlan):
        return {
            "task_count": len(value.tasks),
            "capabilities": [task.capability for task in value.tasks],
        }
    return {"parsed": value is not None}
