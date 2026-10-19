"""File guide.

- Use: Contains unit tests for generic tool registry behavior.
- Usage: Run this file with pytest when checking tool registration.
- Duties: Registers typed fake tools and validates metadata and arguments.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.tools.registry.
"""

import pytest
from pydantic import BaseModel, ConfigDict

from rastin_ai.skills import BaseSkill, BaseTool, CapabilityDefinition, SkillMetadata
from rastin_ai.tools.registry import (
    ToolArgumentValidationError,
    ToolRegistrationError,
    UnknownToolError,
    get_capability_definition,
    get_tool_definitions,
    list_tools,
    register_capability,
    register_tool,
    validate_tool_arguments,
)


class CalculatorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str
    precision: int = 2


class CalculatorTool:
    name = "metadata_calculator"
    description = "Evaluate a mathematical expression."
    args_schema = CalculatorArguments

    def execute(self, **kwargs: object) -> object:
        return kwargs


class MetadataFreeExecutor:
    def execute(self, **kwargs: object) -> object:
        return kwargs


class SkillOwnedArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int


class SkillOwnedTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="skill_owned_tool",
            description="Skill-owned canonical description.",
            capability="skill.owned.execute",
            args_schema=SkillOwnedArguments,
        )
        self.calls: list[SkillOwnedArguments] = []

    def execute(self, tool_input: object) -> object:
        assert isinstance(tool_input, SkillOwnedArguments)
        self.calls.append(tool_input)
        return {"value": tool_input.value}


class SkillOwnedCapability(BaseSkill):
    def __init__(self, tool: SkillOwnedTool) -> None:
        super().__init__(
            metadata=SkillMetadata(
                name="skill_owned",
                description="A test skill.",
                version="0.1.0",
            ),
            instructions="Test deterministic execution.",
            capabilities=("skill.owned.execute",),
            tools=(tool,),
        )


class MissingSchemaTool:
    name = "missing_schema"
    description = "Missing an argument schema."

    def execute(self, **kwargs: object) -> object:
        return kwargs


def test_registered_tool_exposes_metadata() -> None:
    tool = CalculatorTool()
    register_tool(tool.name, tool)

    registered_tools = list_tools()

    assert tool in registered_tools
    assert tool.name == "metadata_calculator"
    assert tool.description == "Evaluate a mathematical expression."
    assert tool.args_schema is CalculatorArguments


def test_registry_lists_capabilities_from_canonical_definition() -> None:
    capability = CapabilityDefinition(
        name="canonical_calculator",
        description="Canonical calculator description from Skills.",
        input_schema=CalculatorArguments,
    )
    register_capability(capability, MetadataFreeExecutor())

    definitions = get_tool_definitions()
    definition = next(item for item in definitions if item.name == capability.name)

    assert definition.description == "Canonical calculator description from Skills."
    assert definition.input_schema["properties"]["expression"]["type"] == "string"
    assert definition.argument_schema == definition.input_schema


def test_runtime_registry_does_not_require_duplicate_metadata() -> None:
    capability = CapabilityDefinition(
        name="metadata_free_capability",
        description="Description owned by the canonical skill catalog.",
        input_schema=CalculatorArguments,
    )
    executor = MetadataFreeExecutor()

    register_capability(capability, executor)

    assert list_tools() == (executor,)
    assert get_capability_definition(capability.name) == capability


def test_registry_rejects_tools_without_argument_schema() -> None:
    with pytest.raises(ToolRegistrationError, match="args_schema"):
        register_tool("missing_schema", MissingSchemaTool())


def test_registry_validates_and_normalizes_arguments() -> None:
    capability = CapabilityDefinition(
        name="validation_calculator",
        description="Validate calculator input.",
        input_schema=CalculatorArguments,
    )
    register_capability(capability, MetadataFreeExecutor())

    arguments = validate_tool_arguments(
        capability.name,
        {"expression": "2 + 2", "precision": "4"},
    )

    assert arguments == {"expression": "2 + 2", "precision": 4}


def test_registry_rejects_invalid_arguments() -> None:
    capability = CapabilityDefinition(
        name="strict_validation_calculator",
        description="Validate calculator input strictly.",
        input_schema=CalculatorArguments,
    )
    register_capability(capability, MetadataFreeExecutor())

    with pytest.raises(ToolArgumentValidationError, match="failed validation"):
        validate_tool_arguments(
            capability.name,
            {"expression": "2 + 2", "unexpected": True},
        )


def test_missing_canonical_capability_fails_cleanly() -> None:
    with pytest.raises(UnknownToolError, match="missing_capability"):
        validate_tool_arguments("missing_capability", {})


def test_skill_registration_drives_metadata_validation_and_runtime_execution() -> None:
    from rastin_ai.tools.registry import get_tool, register_skill

    skill_tool = SkillOwnedTool()
    register_skill(SkillOwnedCapability(skill_tool))

    definition = get_tool_definitions()[0]
    arguments = validate_tool_arguments("skill.owned.execute", {"value": "7"})
    executor = get_tool("skill.owned.execute")
    result = executor.execute(**arguments)

    assert definition.name == "skill.owned.execute"
    assert definition.description == "Skill-owned canonical description."
    assert definition.input_schema["properties"]["value"]["type"] == "integer"
    assert arguments == {"value": 7}
    assert result == {"value": 7}
    assert skill_tool.calls == [SkillOwnedArguments(value=7)]
