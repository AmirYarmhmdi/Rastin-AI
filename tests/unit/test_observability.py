"""File guide.

- Use: Contains unit tests for optional observability integration.
- Usage: Run this file with pytest when checking Langfuse tracing boundaries.
- Duties: Uses fakes to verify config, callbacks, spans, usage, and safe errors.
- Depends on: Standard library test doubles. Project modules:
  rastin_ai.agent, rastin_ai.core.config, and rastin_ai.observability.
"""

import os
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from helpers import clear_settings_env
from pydantic import BaseModel, ConfigDict

import rastin_ai.observability.langfuse as langfuse_observability
from rastin_ai.agent.execution import ExecutionPlanExecutor, TaskStatus
from rastin_ai.agent.graph import ObservableAgentGraph
from rastin_ai.agent.response_generator import OpenAIResponseGenerator
from rastin_ai.agent.schemas import ExecutionPlan, ExecutionTask, LiteralArgument
from rastin_ai.core.config import Settings
from rastin_ai.observability import (
    is_observability_enabled,
    observed_span,
    safe_update_observation,
    sanitize_for_observability,
    startup_observability,
    trace_id_from_observation,
    usage_details_from_response,
    with_langgraph_callbacks,
)
from rastin_ai.skills import CapabilityDefinition
from rastin_ai.tools.registry import register_capability


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class RecordingExecutor:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result


class FailingExecutor:
    def execute(self, **kwargs: Any) -> Any:
        raise RuntimeError("provider failed with secret-token")


class FakeObservation:
    def __init__(self, start_kwargs: dict[str, Any]) -> None:
        self.start_kwargs = start_kwargs
        self.updates: list[dict[str, Any]] = []
        self.trace_id = "trace-test"

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeObservationManager:
    def __init__(self, observation: FakeObservation) -> None:
        self.observation = observation
        self.exits: list[type[BaseException] | None] = []

    def __enter__(self) -> FakeObservation:
        return self.observation

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.exits.append(exc_type)
        return False


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.observations: list[FakeObservation] = []
        self.managers: list[FakeObservationManager] = []
        self.flushed = False
        self.shutdown_called = False

    def start_as_current_observation(self, **kwargs: Any) -> FakeObservationManager:
        observation = FakeObservation(kwargs)
        manager = FakeObservationManager(observation)
        self.observations.append(observation)
        self.managers.append(manager)
        return manager

    def flush(self) -> None:
        self.flushed = True

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeResponsesAPI:
    def __init__(self, response: object) -> None:
        self.response = response

    def create(self, **kwargs: object) -> object:
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.responses = FakeResponsesAPI(response)


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch) -> None:
    clear_settings_env(monkeypatch)


def _settings(**overrides: Any) -> Settings:
    values = {
        "LANGFUSE_ENABLED": True,
        "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
        "LANGFUSE_SECRET_KEY": "sk-lf-test",
        "LANGFUSE_BASE_URL": "http://langfuse.local",
    }
    values.update(overrides)
    return Settings(**values)


def _install_fake_langchain_module(monkeypatch) -> type:
    class FakeCallbackHandler:
        pass

    parent = ModuleType("langfuse")
    parent.__path__ = []
    langchain = ModuleType("langfuse.langchain")
    langchain.CallbackHandler = FakeCallbackHandler
    monkeypatch.setitem(sys.modules, "langfuse", parent)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", langchain)
    return FakeCallbackHandler


def _register(name: str, schema: type[BaseModel], executor: object) -> None:
    register_capability(
        CapabilityDefinition(
            name=name,
            description=f"Execute {name}.",
            input_schema=schema,
        ),
        executor,
    )


def test_observability_enabled_requires_toggle_and_credentials() -> None:
    assert is_observability_enabled(Settings()) is False
    assert (
        is_observability_enabled(
            _settings(LANGFUSE_ENABLED=False),
        )
        is False
    )
    assert is_observability_enabled(_settings(LANGFUSE_SECRET_KEY=None)) is False
    assert is_observability_enabled(_settings()) is True


def test_disabled_startup_does_not_import_langfuse(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "langfuse", None)

    assert startup_observability(Settings(LANGFUSE_ENABLED=False)) is False


def test_enabled_startup_initializes_and_exports_environment(monkeypatch) -> None:
    fake_client = FakeLangfuseClient()
    module = ModuleType("langfuse")
    module.get_client = lambda: fake_client
    monkeypatch.setitem(sys.modules, "langfuse", module)

    assert startup_observability(_settings()) is True

    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk-lf-test"
    assert os.environ["LANGFUSE_SECRET_KEY"] == "sk-lf-test"
    assert os.environ["LANGFUSE_BASE_URL"] == "http://langfuse.local"


def test_langgraph_callbacks_are_added_only_when_enabled(monkeypatch) -> None:
    callback_type = _install_fake_langchain_module(monkeypatch)
    existing_callback = object()

    disabled_config = with_langgraph_callbacks(
        {"callbacks": [existing_callback]},
        settings=Settings(),
    )
    enabled_config = with_langgraph_callbacks(
        {"callbacks": [existing_callback]},
        settings=_settings(),
    )

    assert disabled_config == {"callbacks": [existing_callback]}
    assert enabled_config is not None
    assert enabled_config["callbacks"][0] is existing_callback
    assert isinstance(enabled_config["callbacks"][1], callback_type)


def test_observable_graph_injects_callbacks_and_root_workflow(monkeypatch) -> None:
    callback_type = _install_fake_langchain_module(monkeypatch)
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    class FakeGraph:
        def __init__(self) -> None:
            self.config: dict[str, Any] | None = None

        def invoke(self, input: Any, config: dict[str, Any] | None = None) -> Any:
            self.config = config
            return {"answer": "done"}

    graph = FakeGraph()
    result = ObservableAgentGraph(graph, settings=_settings()).invoke({"q": "hi"})

    assert result == {"answer": "done"}
    assert graph.config is not None
    assert isinstance(graph.config["callbacks"][0], callback_type)
    assert fake_client.observations[0].start_kwargs["as_type"] == "agent"
    assert fake_client.observations[0].updates == [
        {
            "output": {
                "keys": ["answer"],
                "has_error": False,
                "plan_step_count": 0,
                "has_response": False,
            }
        }
    ]


def test_tool_execution_records_successful_tool_observation(monkeypatch) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )
    executor = RecordingExecutor({"large": "x" * 3_000})
    _register("test.observe", TextArguments, executor)
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.observe",
                arguments={"text": LiteralArgument(value="safe")},
            )
        ]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_1"].status is TaskStatus.SUCCEEDED
    observation = fake_client.observations[0]
    assert observation.start_kwargs["as_type"] == "tool"
    assert observation.start_kwargs["name"] == "test.observe"
    assert observation.start_kwargs["input"] == {"text": "safe"}
    assert observation.start_kwargs["metadata"] == {"task_id": "task_1"}
    assert observation.updates[0]["output"] == {
        "type": "mapping",
        "keys": ["large"],
        "key_count": 1,
    }


def test_tool_execution_records_failure_without_changing_result(monkeypatch) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )
    _register("test.fail_observed", EmptyArguments, FailingExecutor())
    plan = ExecutionPlan(
        tasks=[ExecutionTask(id="task_1", capability="test.fail_observed")]
    )

    result = ExecutionPlanExecutor().execute(plan)

    assert result.task_states["task_1"].status is TaskStatus.FAILED
    assert result.task_states["task_1"].error == "Task execution failed."
    failure_update = fake_client.observations[0].updates[0]
    assert failure_update["level"] == "ERROR"
    assert "RuntimeError" in failure_update["status_message"]
    assert "secret-token" not in failure_update["status_message"]


def test_generation_observation_captures_provider_usage(monkeypatch) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )
    response = SimpleNamespace(
        output_text="Answer.",
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
            input_tokens_details=SimpleNamespace(cached_tokens=4),
        ),
    )
    generator = OpenAIResponseGenerator(
        model="fake-model",
        client=FakeOpenAIClient(response),
    )

    assert generator.generate_response(user_query="Question?", plan=["answer"]) == (
        "Answer."
    )

    observation = fake_client.observations[0]
    assert observation.start_kwargs["as_type"] == "generation"
    assert observation.start_kwargs["model"] == "fake-model"
    assert observation.start_kwargs["input"] == {
        "user_query_chars": 9,
        "plan_step_count": 1,
        "has_execution_plan": False,
        "has_execution_result": False,
        "has_tool_result": False,
        "has_error": False,
    }
    assert observation.updates[0]["output"] == {"response_chars": 7}
    assert observation.updates[0]["usage_details"] == {
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
        "input_tokens_cached_tokens": 4,
    }


def test_usage_extraction_and_sanitization_are_conservative() -> None:
    response = SimpleNamespace(
        usage={
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "total_tokens": 12,
            "ignored": "not-a-token-count",
        }
    )

    assert usage_details_from_response(response) == {
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "total_tokens": 12,
    }
    assert sanitize_for_observability(
        {"OPENAI_API_KEY": "sk-secret", "file": b"abc"}
    ) == {"OPENAI_API_KEY": "[REDACTED]", "file": "<binary length=3>"}
    assert sanitize_for_observability(
        {
            "storage_key": "files/private/content.pdf",
            "local_path": "/tmp/private/content.pdf",
            "nested": {"path": "/tmp/secret.txt"},
        }
    ) == {
        "storage_key": "[REDACTED]",
        "local_path": "[REDACTED]",
        "nested": {"path": "[REDACTED]"},
    }


def test_observed_span_is_noop_when_langfuse_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: None,
    )

    with observed_span(name="test.noop", input={"path": "/tmp/private.txt"}) as span:
        safe_update_observation(span, output={"storage_key": "files/private.txt"})


def test_span_updates_are_sanitized_and_trace_id_is_extractable(monkeypatch) -> None:
    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    with observed_span(
        name="test.span",
        input={"storage_key": "files/private/content.pdf"},
        metadata={"document_id": "doc-1"},
    ) as observation:
        assert trace_id_from_observation(observation) == "trace-test"
        safe_update_observation(
            observation,
            output={"local_path": "/tmp/private/content.pdf", "count": 1},
        )

    recorded = fake_client.observations[0]
    assert recorded.start_kwargs["as_type"] == "span"
    assert recorded.start_kwargs["input"] == {"storage_key": "[REDACTED]"}
    assert recorded.updates == [{"output": {"local_path": "[REDACTED]", "count": 1}}]


def test_observability_update_failures_do_not_escape() -> None:
    class ExplodingObservation:
        def update(self, **kwargs: Any) -> None:
            _ = kwargs
            raise RuntimeError("telemetry unavailable")

    safe_update_observation(
        ExplodingObservation(),
        output={"path": "/tmp/private/content.txt"},
    )
