"""File guide.

- Use: Contains unit tests for the OpenAI-backed planner adapter.
- Usage: Run this file with pytest when checking planner SDK integration.
- Duties: Uses fake OpenAI clients to verify ExecutionPlan structured output.
- Depends on: Project modules: rastin_ai.agent.exceptions,
  rastin_ai.agent.planner, rastin_ai.agent.schemas, and
  rastin_ai.core.config. Project modules: rastin_ai.skills.capabilities.
"""

import inspect
from types import SimpleNamespace

import pytest

import rastin_ai.agent.planner as planner_module
from rastin_ai.agent.exceptions import PlannerError
from rastin_ai.agent.planner import OpenAIPlanner
from rastin_ai.agent.schemas import ExecutionPlan, ExecutionTask, LiteralArgument
from rastin_ai.core.config import Settings
from rastin_ai.skills.capabilities import CapabilityPromptView


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


def test_openai_planner_sends_query_capabilities_and_structured_schema() -> None:
    parsed_plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.calculator",
                arguments={"expression": LiteralArgument(value="2 + 2")},
            )
        ]
    )
    responses = FakeResponsesAPI(parsed_plan)
    planner = OpenAIPlanner(model="fake-model", client=FakeOpenAIClient(responses))
    capabilities = (
        CapabilityPromptView(
            name="test.calculator",
            description="Evaluate arithmetic.",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
            },
        ),
    )

    plan = planner.create_plan(
        user_query="Calculate 2 + 2",
        available_capabilities=capabilities,
    )

    assert plan == parsed_plan
    call = responses.calls[0]
    assert call["model"] == "fake-model"
    assert call["text_format"] is ExecutionPlan
    assert "Calculate 2 + 2" in str(call["input"])
    assert "test.calculator" in str(call["input"])
    assert "Evaluate arithmetic." in str(call["input"])
    assert "Do not generate Python or LangGraph code." in str(call["instructions"])


def test_openai_planner_rejects_missing_structured_output() -> None:
    planner = OpenAIPlanner(
        model="fake-model",
        client=FakeOpenAIClient(FakeResponsesAPI(output_parsed=None)),
    )

    with pytest.raises(PlannerError, match="no structured plan"):
        planner.create_plan(user_query="Plan this work.", available_capabilities=())


def test_openai_planner_wraps_request_failures_safely() -> None:
    planner = OpenAIPlanner(
        model="fake-model",
        client=FakeOpenAIClient(FailingResponsesAPI()),
    )

    with pytest.raises(PlannerError, match="OpenAI planner request failed"):
        planner.create_plan(user_query="Plan this work.", available_capabilities=())


def test_openai_planner_requires_api_key_without_injected_client() -> None:
    planner = OpenAIPlanner(
        settings=Settings(
            DEBUG=False,
            OPENAI_API_KEY=None,
            OPENAI_PLANNER_MODEL="fake-model",
        )
    )

    with pytest.raises(PlannerError, match="OPENAI_API_KEY"):
        planner.create_plan(user_query="Plan this work.", available_capabilities=())


def test_openai_planner_does_not_manually_parse_json() -> None:
    source = inspect.getsource(planner_module)

    assert "json.loads" not in source
    assert "literal_eval" not in source
