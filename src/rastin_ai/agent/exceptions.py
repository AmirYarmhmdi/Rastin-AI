"""File guide.

- Use: Defines errors raised by agent orchestration components.
- Usage: Import PlannerError, ResponseGenerationError, and ToolSelectorError from
  rastin_ai.agent.exceptions.
- Duties: Provides concise, safe exceptions for agent component failures.
- Depends on: No direct project module dependencies.
"""


class AgentError(Exception):
    """Base error for agent orchestration failures."""


class PlannerError(AgentError):
    """Raised when plan generation fails or returns invalid output."""


class ToolSelectorError(AgentError):
    """Raised when tool selection fails or returns invalid output."""


class ResponseGenerationError(AgentError):
    """Raised when final response generation fails or returns invalid output."""
