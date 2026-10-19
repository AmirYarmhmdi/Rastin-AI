"""File guide.

- Use: Contains unit tests for the OpenAI-backed tool selector adapter.
- Usage: Run this file with pytest when checking selector SDK integration.
- Duties: Uses fake OpenAI clients to verify structured-output boundaries.
- Depends on: Project modules: rastin_ai.agent.exceptions,
  rastin_ai.agent.schemas, rastin_ai.agent.tool_selector,
  rastin_ai.core.config, and rastin_ai.tools.base.
"""

import inspect
from types import SimpleNamespace

import pytest

import rastin_ai.agent.tool_selector as tool_selector_module
from rastin_ai.agent.exceptions import ToolSelectorError
from rastin_ai.agent.schemas import ToolSelection
from rastin_ai.agent.tool_selector import OpenAIToolSelector
from rastin_ai.core.config import Settings
from rastin_ai.tools.base import ToolDefinition


class FakeResponsesAPI:
    def __init__(self, output_parsed: object) -> None:
        self.output_parsed = output_parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.output_parsed)


class FailingResponsesAPI:
    def parse(self, **kwargs: object) -> object:
        raise RuntimeError("raw provider details")


class FakeOpenAIClient:
    def __init__(self, responses: object) -> None:
        self.responses = responses


def test_openai_selector_sends_query_plan_tools_and_structured_schema() -> None:
    parsed_selection = ToolSelection(
        tool_name="calculator",
        arguments={"expression": "2 + 2"},
    )
    responses = FakeResponsesAPI(parsed_selection)
    selector = OpenAIToolSelector(
        model="fake-model",
        client=FakeOpenAIClient(responses),
    )
    tool_definition = ToolDefinition(
        name="calculator",
        description="Evaluate a mathematical expression.",
        argument_schema={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
        },
    )

    selection = selector.select_tool(
        user_query="Calculate 2 + 2",
        plan=["Use a deterministic calculator."],
        available_tools=(tool_definition,),
    )

    assert selection == parsed_selection
    call = responses.calls[0]
    assert call["model"] == "fake-model"
    assert call["text_format"] is ToolSelection
    assert "Calculate 2 + 2" in str(call["input"])
    assert "Use a deterministic calculator." in str(call["input"])
    assert "calculator" in str(call["input"])
    assert "Do not execute the tool." in str(call["instructions"])


def test_openai_selector_rejects_missing_structured_output() -> None:
    selector = OpenAIToolSelector(
        model="fake-model",
        client=FakeOpenAIClient(FakeResponsesAPI(output_parsed=None)),
    )

    with pytest.raises(ToolSelectorError, match="no structured selection"):
        selector.select_tool(
            user_query="Select a tool.",
            plan=["Use a tool."],
            available_tools=(),
        )


def test_openai_selector_wraps_request_failures_safely() -> None:
    selector = OpenAIToolSelector(
        model="fake-model",
        client=FakeOpenAIClient(FailingResponsesAPI()),
    )

    with pytest.raises(ToolSelectorError, match="OpenAI tool selector request failed"):
        selector.select_tool(
            user_query="Select a tool.",
            plan=["Use a tool."],
            available_tools=(),
        )


def test_openai_selector_requires_api_key_without_injected_client() -> None:
    selector = OpenAIToolSelector(
        settings=Settings(
            DEBUG=False,
            OPENAI_API_KEY=None,
            RASTIN_AI_TOOL_SELECTOR_MODEL="fake-model",
        )
    )

    with pytest.raises(ToolSelectorError, match="OPENAI_API_KEY"):
        selector.select_tool(
            user_query="Select a tool.",
            plan=["Use a tool."],
            available_tools=(),
        )


def test_openai_selector_does_not_manually_parse_json() -> None:
    source = inspect.getsource(tool_selector_module)

    assert "json.loads" not in source
    assert "literal_eval" not in source
