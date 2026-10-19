"""File guide.

- Use: Defines tool selector interfaces and the OpenAI structured-output adapter.
- Usage: Import ToolSelector and OpenAIToolSelector from
  rastin_ai.agent.tool_selector.
- Duties: Proposes zero or one registered tool invocation without execution.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.exceptions, rastin_ai.agent.schemas,
  rastin_ai.core.config, rastin_ai.observability, and
  rastin_ai.skills.capabilities.
"""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from rastin_ai.agent.exceptions import ToolSelectorError
from rastin_ai.agent.schemas import ToolSelection
from rastin_ai.core.config import Settings, get_settings
from rastin_ai.observability import (
    observed_generation,
    sanitize_for_observability,
    usage_details_from_response,
)
from rastin_ai.skills.capabilities import CapabilityPromptView

DEFAULT_OPENAI_TOOL_SELECTOR_MODEL = "gpt-4.1-mini"

TOOL_SELECTOR_INSTRUCTIONS = """You are the tool-selection component of Rastin-AI.

Given the user's request, the high-level plan, and the currently available
registered tools, select the single best tool required for the next executable
operation.

Only select a tool from the provided available tool list.
Return no tool when no executable capability is needed.
Provide arguments required by the selected tool based only on the user's request
and plan.

Do not execute the tool.
Do not fabricate tool results.
Do not answer the user's request.
Do not select tools that are not listed.
"""


class ToolSelector(Protocol):
    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: tuple[CapabilityPromptView, ...],
    ) -> ToolSelection:
        """Return a structured zero-or-one tool selection."""


class OpenAIToolSelectorConfig(BaseModel):
    """Configuration for the OpenAI tool selector adapter."""

    model: str = Field(default=DEFAULT_OPENAI_TOOL_SELECTOR_MODEL, min_length=1)
    api_key: str | None = None


class OpenAIToolSelector:
    """OpenAI-backed selector that returns validated structured output."""

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

        self._config = OpenAIToolSelectorConfig(
            model=model
            or (
                resolved_settings.RASTIN_AI_TOOL_SELECTOR_MODEL
                if resolved_settings is not None
                else DEFAULT_OPENAI_TOOL_SELECTOR_MODEL
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

    def select_tool(
        self,
        *,
        user_query: str,
        plan: list[str],
        available_tools: tuple[CapabilityPromptView, ...],
    ) -> ToolSelection:
        if not user_query.strip():
            msg = "Tool selector user query must not be empty."
            raise ToolSelectorError(msg)

        selector_input = _build_selector_input(
            user_query=user_query,
            plan=plan,
            available_tools=available_tools,
        )

        try:
            with observed_generation(
                name="agent.tool_selector",
                model=self._config.model,
                input={
                    "instructions": TOOL_SELECTOR_INSTRUCTIONS,
                    "input": selector_input,
                    "text_format": "ToolSelection",
                },
                metadata={"component": "tool_selector"},
                settings=self._settings,
            ) as observation:
                response = self._get_client().responses.parse(
                    model=self._config.model,
                    instructions=TOOL_SELECTOR_INSTRUCTIONS,
                    input=selector_input,
                    text_format=ToolSelection,
                )
                observation.update(
                    output=sanitize_for_observability(
                        getattr(response, "output_parsed", None)
                    ),
                    usage_details=usage_details_from_response(response),
                )
        except ToolSelectorError:
            raise
        except Exception as exc:
            msg = (
                "OpenAI tool selector request failed for model: "
                f"{self._config.model}"
            )
            raise ToolSelectorError(msg) from exc

        parsed_selection = getattr(response, "output_parsed", None)
        if not isinstance(parsed_selection, ToolSelection):
            msg = "OpenAI tool selector returned no structured selection."
            raise ToolSelectorError(msg)

        return parsed_selection

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()

        return self._client

    def _build_client(self) -> Any:
        if not self._config.api_key:
            msg = "OPENAI_API_KEY must be set before creating an OpenAI tool selector."
            raise ToolSelectorError(msg)

        try:
            from openai import OpenAI
        except ImportError as exc:
            msg = "The openai package is required for OpenAI tool selection."
            raise ToolSelectorError(msg) from exc

        return OpenAI(api_key=self._config.api_key)


def _build_selector_input(
    *,
    user_query: str,
    plan: list[str],
    available_tools: tuple[CapabilityPromptView, ...],
) -> str:
    tool_payload = [tool.model_dump(mode="json") for tool in available_tools]
    return (
        f"User request:\n{user_query}\n\n"
        f"Plan steps:\n{plan}\n\n"
        f"Available registered tools:\n{tool_payload}"
    )
