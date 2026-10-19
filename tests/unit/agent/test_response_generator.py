"""File guide.

- Use: Contains unit tests for the OpenAI-backed response generator adapter.
- Usage: Run this file with pytest when checking final response generation.
- Duties: Uses fake OpenAI clients to verify grounded prompt boundaries.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.exceptions, rastin_ai.agent.response_generator, and
  rastin_ai.core.config.
"""

import inspect
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import rastin_ai.agent.response_generator as response_generator_module
from rastin_ai.agent.exceptions import ResponseGenerationError
from rastin_ai.agent.execution import (
    ExecutionResult,
    TaskRuntimeState,
    TaskStatus,
)
from rastin_ai.agent.response_generator import OpenAIResponseGenerator
from rastin_ai.agent.schemas import ExecutionPlan, ExecutionTask
from rastin_ai.core.config import Settings


class FakeResponsesAPI:
    def __init__(self, output_text: object) -> None:
        self.output_text = output_text
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FailingResponsesAPI:
    def create(self, **kwargs: object) -> object:
        raise RuntimeError("raw provider details")


class FakeOpenAIClient:
    def __init__(self, responses: object) -> None:
        self.responses = responses


class StructuredResult(BaseModel):
    total: int
    unit: str


def test_openai_response_generator_sends_grounded_context_and_returns_text() -> None:
    responses = FakeResponsesAPI("The result is 120.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )

    response = generator.generate_response(
        user_query="Calculate 15 * 8",
        plan=["Use a deterministic calculator."],
        tool_name="calculator",
        tool_result=120,
        error=None,
    )

    assert response == "The result is 120."
    call = responses.calls[0]
    payload = json.loads(str(call["input"]))
    assert call["model"] == "fake-model"
    assert payload["user_request"] == "Calculate 15 * 8"
    assert payload["execution_plan"] == ["Use a deterministic calculator."]
    assert payload["selected_tool"] == "calculator"
    assert payload["tool_result"] == 120
    assert payload["error"] is None
    assert "treat that result as authoritative" in str(call["instructions"])
    assert "Answer the user's exact request directly" in str(call["instructions"])
    assert "ignore unrelated details" in str(call["instructions"])


def test_openai_response_generator_records_model_and_token_usage() -> None:
    class UsageResponsesAPI(FakeResponsesAPI):
        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text=self.output_text,
                usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            )

    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(UsageResponsesAPI("The result is 120.")),
    )

    generator.generate_response(
        user_query="Calculate 15 * 8",
        plan=["Use a deterministic calculator."],
        tool_name="calculator",
        tool_result=120,
    )

    metadata = generator.last_generation_metadata
    assert metadata is not None
    assert metadata.model == "fake-model"
    assert metadata.token_usage == {"input_tokens": 11, "output_tokens": 7}


def test_openai_response_generator_preserves_structured_tool_result() -> None:
    responses = FakeResponsesAPI("The total is 120 EUR.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )

    generator.generate_response(
        user_query="Calculate the total.",
        plan=["Use a deterministic calculator."],
        tool_name="calculator",
        tool_result={"total": 120, "unit": "EUR"},
        error=None,
    )

    payload = json.loads(str(responses.calls[0]["input"]))
    assert payload["tool_result"] == {"total": 120, "unit": "EUR"}


def test_openai_response_generator_sends_structured_execution_result() -> None:
    responses = FakeResponsesAPI("The planned tasks completed.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )
    execution_plan = ExecutionPlan(
        tasks=[ExecutionTask(id="task_1", capability="test.capability")]
    )
    execution_result = ExecutionResult(
        task_states={
            "task_1": TaskRuntimeState(
                task_id="task_1",
                status=TaskStatus.SUCCEEDED,
                result={"value": 4},
            )
        }
    )

    generator.generate_response(
        user_query="Run the plan.",
        plan=["task_1: test.capability"],
        execution_plan=execution_plan,
        execution_result=execution_result,
    )

    payload = json.loads(str(responses.calls[0]["input"]))
    assert payload["execution_plan"] == execution_plan.model_dump(mode="json")
    assert payload["execution_result"] == execution_result.model_dump(mode="json")


def test_openai_response_generator_serializes_pydantic_tool_result() -> None:
    responses = FakeResponsesAPI("The total is 120 EUR.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )

    generator.generate_response(
        user_query="Calculate the total.",
        plan=["Use a deterministic calculator."],
        tool_name="calculator",
        tool_result=StructuredResult(total=120, unit="EUR"),
        error=None,
    )

    payload = json.loads(str(responses.calls[0]["input"]))
    assert payload["tool_result"] == {"total": 120, "unit": "EUR"}


def test_openai_response_generator_sends_no_tool_context() -> None:
    responses = FakeResponsesAPI("Rastin-AI orchestrates AI workflows.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )

    generator.generate_response(
        user_query="Explain Rastin-AI.",
        plan=["Answer directly."],
        tool_name=None,
        tool_result=None,
        error=None,
    )

    payload = json.loads(str(responses.calls[0]["input"]))
    assert payload["selected_tool"] is None
    assert payload["tool_result"] is None


def test_openai_response_generator_sends_sanitized_error_context() -> None:
    responses = FakeResponsesAPI("The tool inputs were invalid.")
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )

    generator.generate_response(
        user_query="Calculate this.",
        plan=["Use a deterministic calculator."],
        tool_name=None,
        tool_result=None,
        error="Tool arguments failed validation.",
    )

    payload = json.loads(str(responses.calls[0]["input"]))
    assert payload["error"] == "Tool arguments failed validation."


def test_openai_response_generator_wraps_request_failures_safely() -> None:
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(FailingResponsesAPI()),
    )

    with pytest.raises(ResponseGenerationError, match="OpenAI response generation"):
        generator.generate_response(
            user_query="Explain this.",
            plan=["Answer directly."],
            tool_name=None,
            tool_result=None,
            error=None,
        )


def test_openai_response_generator_rejects_empty_response_text() -> None:
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(FakeResponsesAPI("   ")),
    )

    with pytest.raises(ResponseGenerationError, match="no response text"):
        generator.generate_response(
            user_query="Explain this.",
            plan=["Answer directly."],
            tool_name=None,
            tool_result=None,
            error=None,
        )


def test_openai_response_generator_requires_api_key_without_injected_client() -> None:
    generator = OpenAIResponseGenerator(
        settings=Settings(
            DEBUG=False,
            OPENAI_API_KEY=None,
            OPENAI_RESPONSE_MODEL="fake-model",
        )
    )

    with pytest.raises(ResponseGenerationError, match="OPENAI_API_KEY"):
        generator.generate_response(
            user_query="Explain this.",
            plan=["Answer directly."],
            tool_name=None,
            tool_result=None,
            error=None,
        )


def test_openai_response_generator_does_not_manually_parse_json_or_execute_tools() -> (
    None
):
    source = inspect.getsource(response_generator_module)

    assert "json.loads" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "get_tool(" not in source
    assert "execute(" not in source
