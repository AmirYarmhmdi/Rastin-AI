"""File guide.

- Use: Contains unit tests for capability-aware ExecutionPlan validation.
- Usage: Run this file with pytest when checking plan validation behavior.
- Duties: Builds test Skill registries and validates structured plans.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.plan_validation, rastin_ai.agent.schemas, and
  rastin_ai.skills.
"""

import pytest
from pydantic import BaseModel, ConfigDict

from rastin_ai.agent.plan_validation import (
    ExecutionPlanValidationError,
    ExecutionPlanValidator,
)
from rastin_ai.agent.schemas import ExecutionPlan, ExecutionTask, LiteralArgument
from rastin_ai.skills import BaseSkill, BaseTool, SkillMetadata
from rastin_ai.skills.registry import SkillRegistry


class CapabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class ExecutableTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="executable_tool",
            description="Canonical executable description.",
            capability="test.executable",
            args_schema=CapabilityInput,
        )

    def execute(self, tool_input: object) -> object:
        return tool_input


class ExecutableSkill(BaseSkill):
    def __init__(self) -> None:
        super().__init__(
            metadata=SkillMetadata(
                name="executable_skill",
                description="Contains an executable capability.",
                version="0.1.0",
            ),
            instructions="Execute deterministic tests.",
            capabilities=("test.executable", "test.declared_only"),
            tools=(ExecutableTool(),),
        )


def _registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(ExecutableSkill())
    return registry


def test_execution_plan_validator_accepts_canonical_executable_capability() -> None:
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.executable",
                arguments={"value": LiteralArgument(value=1)},
            )
        ]
    )

    assert ExecutionPlanValidator().validate(plan, skill_registry=_registry()) is plan


def test_execution_plan_validator_rejects_unknown_capability() -> None:
    plan = ExecutionPlan(tasks=[ExecutionTask(id="task_1", capability="test.unknown")])

    with pytest.raises(ExecutionPlanValidationError, match="test.unknown"):
        ExecutionPlanValidator().validate(plan, skill_registry=_registry())


def test_execution_plan_validator_rejects_non_executable_declared_capability() -> None:
    plan = ExecutionPlan(
        tasks=[ExecutionTask(id="task_1", capability="test.declared_only")]
    )

    with pytest.raises(ExecutionPlanValidationError, match="test.declared_only"):
        ExecutionPlanValidator().validate(plan, skill_registry=_registry())


def test_execution_plan_contains_capability_identity_without_metadata_duplication() -> (
    None
):
    task = ExecutionTask(id="task_1", capability="test.executable")

    assert task.model_dump() == {
        "id": "task_1",
        "capability": "test.executable",
        "arguments": {},
        "depends_on": [],
    }
