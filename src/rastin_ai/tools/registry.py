"""File guide.

- Use: Resolves runtime executors for canonical Skills capabilities.
- Usage: Import register_capability, register_tool, get_tool, list_tools, and
  validate_tool_arguments from rastin_ai.tools.registry.
- Duties: Binds canonical capability names to deterministic executors. Metadata
  and schemas remain owned by rastin_ai.skills.
- Depends on: External packages: pydantic and typing. Project modules:
  rastin_ai.skills and rastin_ai.tools.base.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from rastin_ai.skills import BaseSkill, BaseTool, CapabilityDefinition, SkillRegistry
from rastin_ai.tools.base import Tool, ToolDefinition


class UnknownToolError(LookupError):
    pass


class ToolRegistrationError(ValueError):
    pass


class ToolArgumentValidationError(ValueError):
    pass


class _SkillToolExecutor:
    def __init__(self, tool: BaseTool) -> None:
        self._tool = tool

    def execute(self, **kwargs: Any) -> Any:
        tool_input = self._tool.args_schema.model_validate(kwargs)
        return self._tool.execute(tool_input)


_SKILL_REGISTRY = SkillRegistry()
_TOOLS: dict[str, Tool] = {}


def register_capability(capability: CapabilityDefinition, executor: Tool) -> None:
    _SKILL_REGISTRY.register_capability(capability)
    _TOOLS[capability.name] = executor


def register_skill(skill: BaseSkill) -> None:
    _SKILL_REGISTRY.register(skill)
    for skill_tool in skill.tools:
        _TOOLS[skill_tool.capability] = _SkillToolExecutor(skill_tool)


def register_skill_tools(skill_tools: tuple[BaseTool, ...]) -> None:
    for skill_tool in skill_tools:
        register_capability(
            skill_tool.capability_definition,
            _SkillToolExecutor(skill_tool),
        )


def register_tool(name: str, tool: Tool) -> None:
    """Compatibility adapter for registering a runtime executor.

    New code should prefer register_capability(capability, executor). This helper
    creates the canonical capability definition in the Skills registry, then
    stores only the runtime executor binding here.
    """
    capability = _capability_from_legacy_tool(name, tool)
    register_capability(capability, tool)


def get_tool(name: str) -> Tool:
    if _SKILL_REGISTRY.get_capability(name) is None:
        msg = f"Unknown tool: {name}"
        raise UnknownToolError(msg)

    try:
        return _TOOLS[name]
    except KeyError as exc:
        msg = f"Unknown tool: {name}"
        raise UnknownToolError(msg) from exc


def list_tools() -> tuple[Tool, ...]:
    return tuple(_TOOLS.values())


def get_tool_definitions() -> tuple[ToolDefinition, ...]:
    return _SKILL_REGISTRY.get_capability_prompt_views()


def get_runtime_skill_registry() -> SkillRegistry:
    return _SKILL_REGISTRY


def get_capability_definition(name: str) -> CapabilityDefinition:
    capability = _SKILL_REGISTRY.get_capability(name)
    if capability is None:
        msg = f"Unknown tool: {name}"
        raise UnknownToolError(msg)

    return capability


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    capability = get_capability_definition(name)

    try:
        validated_arguments = capability.input_schema.model_validate(arguments)
    except ValidationError as exc:
        msg = f"Tool arguments failed validation for {name}."
        raise ToolArgumentValidationError(msg) from exc

    return validated_arguments.model_dump()


def _capability_from_legacy_tool(name: str, tool: Tool) -> CapabilityDefinition:
    if not name:
        msg = "Tool name must not be empty."
        raise ValueError(msg)
    description = getattr(tool, "description", None)
    if not description:
        msg = f"Tool must expose a non-empty description: {name}"
        raise ToolRegistrationError(msg)
    args_schema = getattr(tool, "args_schema", None)
    if not isinstance(args_schema, type) or not issubclass(args_schema, BaseModel):
        msg = f"Tool must expose a Pydantic args_schema: {name}"
        raise ToolRegistrationError(msg)

    return CapabilityDefinition(
        name=name,
        description=description,
        input_schema=args_schema,
    )


def _reset_runtime_registry_for_tests() -> None:
    _TOOLS.clear()
    _SKILL_REGISTRY._skills.clear()
    _SKILL_REGISTRY._capabilities.clear()
