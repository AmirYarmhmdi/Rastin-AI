"""File guide.

- Use: Defines response generator interfaces and the OpenAI response adapter.
- Usage: Import ResponseGenerator and OpenAIResponseGenerator from
  rastin_ai.agent.response_generator.
- Duties: Presents validated workflow outcomes without executing work.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.exceptions, rastin_ai.agent.execution,
  rastin_ai.agent.schemas, rastin_ai.core.config, and
  rastin_ai.observability.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field

from rastin_ai.agent.exceptions import ResponseGenerationError
from rastin_ai.agent.execution import ExecutionResult
from rastin_ai.agent.schemas import ExecutionPlan
from rastin_ai.core.config import Settings, get_settings
from rastin_ai.observability import (
    observed_generation,
    sanitize_for_observability,
    usage_details_from_response,
)

RESPONSE_GENERATOR_INSTRUCTIONS = (
    "You are the response-generation component of Rastin-AI.\n\n"
    "Produce a clear final answer to the user's request using only the supplied "
    "workflow context and execution results.\n\n"
    "When a deterministic tool result is provided, treat that result as "
    "authoritative.\n\n"
    "Answer the user's exact request directly and concisely. Use only evidence "
    "that is relevant to that request, and ignore unrelated details that may be "
    "present in retrieved context or tool output.\n\n"
    "Do not recompute, override, reinterpret as a different result, or fabricate "
    "replacement values.\n"
    "Do not claim that an operation was performed unless the supplied context says "
    "it was performed.\n"
    "Do not invoke or select tools.\n"
    "Do not expose internal orchestration details unless they are relevant to "
    "explaining an error.\n"
    "When information is missing, say that it is unavailable rather than inventing "
    "it.\n\n"
    "Return only the user-facing final answer."
)


class ResponseGenerator(Protocol):
    def generate_response(
        self,
        *,
        user_query: str,
        plan: list[str],
        execution_plan: ExecutionPlan | None = None,
        execution_result: ExecutionResult | None = None,
        tool_name: str | None = None,
        tool_result: Any = None,
        error: str | None = None,
    ) -> str:
        """Return the final user-facing response for a workflow outcome."""


@dataclass(frozen=True)
class ResponseGenerationMetadata:
    """Provider metadata from the most recent response generation call."""

    model: str
    token_usage: dict[str, int] | None = None


class OpenAIResponseGeneratorConfig(BaseModel):
    """Configuration for the OpenAI response generator adapter."""

    model: str = Field(min_length=1)
    api_key: str | None = None


class OpenAIResponseGenerator:
    """OpenAI-backed response generator for grounded final answers."""

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

        self._config = OpenAIResponseGeneratorConfig(
            model=model
            or (
                resolved_settings.OPENAI_RESPONSE_MODEL
                if resolved_settings is not None
                else get_settings().OPENAI_RESPONSE_MODEL
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
        self._last_generation_metadata: ResponseGenerationMetadata | None = None

    @property
    def last_generation_metadata(self) -> ResponseGenerationMetadata | None:
        return self._last_generation_metadata

    def generate_response(
        self,
        *,
        user_query: str,
        plan: list[str],
        execution_plan: ExecutionPlan | None = None,
        execution_result: ExecutionResult | None = None,
        tool_name: str | None = None,
        tool_result: Any = None,
        error: str | None = None,
    ) -> str:
        if not user_query.strip():
            msg = "Response generator user query must not be empty."
            raise ResponseGenerationError(msg)

        self._last_generation_metadata = None
        response_input = _build_response_input(
            user_query=user_query,
            plan=plan,
            execution_plan=execution_plan,
            execution_result=execution_result,
            tool_name=tool_name,
            tool_result=tool_result,
            error=error,
        )

        try:
            with observed_generation(
                name="agent.response_generator",
                model=self._config.model,
                input={
                    "user_query_chars": len(user_query),
                    "plan_step_count": len(plan),
                    "has_execution_plan": execution_plan is not None,
                    "has_execution_result": execution_result is not None,
                    "has_tool_result": tool_result is not None,
                    "has_error": error is not None,
                },
                metadata={"component": "response_generator"},
                settings=self._settings,
            ) as observation:
                response = self._get_client().responses.create(
                    model=self._config.model,
                    instructions=RESPONSE_GENERATOR_INSTRUCTIONS,
                    input=response_input,
                )
                usage_details = usage_details_from_response(response)
                observation.update(
                    output=sanitize_for_observability(
                        {
                            "response_chars": len(
                                getattr(response, "output_text", "") or ""
                            )
                        }
                    ),
                    usage_details=usage_details,
                )
                self._last_generation_metadata = ResponseGenerationMetadata(
                    model=self._config.model,
                    token_usage=usage_details,
                )
        except ResponseGenerationError:
            raise
        except Exception as exc:
            msg = (
                "OpenAI response generation request failed for model: "
                f"{self._config.model}"
            )
            raise ResponseGenerationError(msg) from exc

        response_text = getattr(response, "output_text", None)
        if not isinstance(response_text, str) or not response_text.strip():
            msg = "OpenAI response generator returned no response text."
            raise ResponseGenerationError(msg)

        return response_text.strip()

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()

        return self._client

    def _build_client(self) -> Any:
        if not self._config.api_key:
            msg = (
                "OPENAI_API_KEY must be set before creating an OpenAI response "
                "generator."
            )
            raise ResponseGenerationError(msg)

        try:
            from openai import OpenAI
        except ImportError as exc:
            msg = "The openai package is required for OpenAI response generation."
            raise ResponseGenerationError(msg) from exc

        return OpenAI(api_key=self._config.api_key)


def _build_response_input(
    *,
    user_query: str,
    plan: list[str],
    execution_plan: ExecutionPlan | None = None,
    execution_result: ExecutionResult | None = None,
    tool_name: str | None = None,
    tool_result: Any = None,
    error: str | None = None,
) -> str:
    payload = {
        "user_request": user_query,
        "execution_plan": _to_json_compatible(execution_plan) or plan,
        "execution_result": _to_json_compatible(execution_result),
        "selected_tool": tool_name,
        "tool_result": _to_json_compatible(tool_result),
        "error": error,
    }
    return json.dumps(payload, sort_keys=True)


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _to_json_compatible(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)
