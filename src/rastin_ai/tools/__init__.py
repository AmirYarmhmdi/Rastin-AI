"""File guide.

- Use: Exposes generic deterministic tool abstractions and registry helpers.
- Usage: Import Tool, get_tool, and register_tool from rastin_ai.tools.
- Duties: Keeps generic tool imports short and independent from LangGraph.
- Depends on: Project modules: rastin_ai.tools.base and
  rastin_ai.tools.registry.
"""

from rastin_ai.tools.base import Tool, ToolDefinition
from rastin_ai.tools.registry import (
    ToolArgumentValidationError,
    ToolRegistrationError,
    UnknownToolError,
    get_capability_definition,
    get_runtime_skill_registry,
    get_tool,
    get_tool_definitions,
    list_tools,
    register_capability,
    register_skill,
    register_skill_tools,
    register_tool,
    validate_tool_arguments,
)

__all__ = (
    "Tool",
    "ToolArgumentValidationError",
    "ToolDefinition",
    "ToolRegistrationError",
    "UnknownToolError",
    "get_capability_definition",
    "get_runtime_skill_registry",
    "get_tool",
    "get_tool_definitions",
    "list_tools",
    "register_capability",
    "register_skill",
    "register_skill_tools",
    "register_tool",
    "validate_tool_arguments",
)
