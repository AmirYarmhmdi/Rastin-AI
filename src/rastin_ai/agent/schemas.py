"""File guide.

- Use: Defines structured models exchanged between agent components.
- Usage: Import ExecutionPlan, ExecutionTask, and ToolSelection from
  rastin_ai.agent.schemas.
- Duties: Provides validated, serializable agent output contracts.
- Depends on: External packages only: pydantic and typing.
"""

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)


class LiteralArgument(BaseModel):
    """Literal argument value supplied directly to a planned task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["literal"] = "literal"
    value: Any


class TaskOutputReference(BaseModel):
    """Reference to the output of a previous task in the same plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["task_output"] = "task_output"
    task_id: StrictStr = Field(min_length=1)
    path: StrictStr | None = None

    @field_validator("task_id", "path")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped_value = value.strip()
        if not stripped_value:
            msg = "Task output reference fields must be non-empty when provided."
            raise ValueError(msg)

        return stripped_value


ArgumentValue = Annotated[
    LiteralArgument | TaskOutputReference,
    Field(discriminator="type"),
]


class ExecutionTask(BaseModel):
    """Executable task in a structured orchestration plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StrictStr = Field(min_length=1)
    capability: StrictStr = Field(min_length=1)
    arguments: dict[str, ArgumentValue] = Field(default_factory=dict)
    depends_on: list[StrictStr] = Field(default_factory=list)

    @field_validator("id", "capability")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            msg = "Task identifiers and capabilities must be non-empty."
            raise ValueError(msg)

        return stripped_value

    @field_validator("arguments")
    @classmethod
    def reject_empty_argument_names(
        cls, arguments: dict[str, ArgumentValue]
    ) -> dict[str, ArgumentValue]:
        if any(not name.strip() for name in arguments):
            msg = "Task argument names must be non-empty strings."
            raise ValueError(msg)

        return {name.strip(): value for name, value in arguments.items()}

    @field_validator("depends_on")
    @classmethod
    def normalize_dependencies(cls, depends_on: list[str]) -> list[str]:
        normalized_dependencies = [dependency.strip() for dependency in depends_on]
        if any(not dependency for dependency in normalized_dependencies):
            msg = "Task dependencies must be non-empty task IDs."
            raise ValueError(msg)
        if len(set(normalized_dependencies)) != len(normalized_dependencies):
            msg = "Task dependencies must not contain duplicates."
            raise ValueError(msg)

        return normalized_dependencies

    @model_validator(mode="after")
    def reject_self_dependency(self) -> "ExecutionTask":
        if self.id in self.depends_on:
            msg = f"Task cannot depend on itself: {self.id}"
            raise ValueError(msg)

        return self


class ExecutionPlan(BaseModel):
    """Provider-independent structured plan for future DAG execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks: list[ExecutionTask] = Field(default_factory=list)
    response_strategy: StrictStr | None = None

    @field_validator("response_strategy")
    @classmethod
    def normalize_response_strategy(cls, value: str | None) -> str | None:
        if value is None:
            return None

        stripped_value = value.strip()
        if not stripped_value:
            msg = "Response strategy must be non-empty when provided."
            raise ValueError(msg)

        return stripped_value

    @model_validator(mode="after")
    def validate_task_graph(self) -> "ExecutionPlan":
        task_ids = [task.id for task in self.tasks]
        if len(set(task_ids)) != len(task_ids):
            msg = "ExecutionPlan task IDs must be unique."
            raise ValueError(msg)

        task_id_set = set(task_ids)
        task_by_id = {task.id: task for task in self.tasks}
        for task in self.tasks:
            missing_dependencies = [
                dependency
                for dependency in task.depends_on
                if dependency not in task_id_set
            ]
            if missing_dependencies:
                msg = (
                    f"Task {task.id} depends on unknown task IDs: "
                    f"{missing_dependencies}"
                )
                raise ValueError(msg)

            for argument in task.arguments.values():
                if not isinstance(argument, TaskOutputReference):
                    continue
                if argument.task_id not in task_id_set:
                    msg = (
                        f"Task {task.id} references unknown task output: "
                        f"{argument.task_id}"
                    )
                    raise ValueError(msg)
                if argument.task_id not in task.depends_on:
                    msg = (
                        f"Task {task.id} references non-upstream task output: "
                        f"{argument.task_id}"
                    )
                    raise ValueError(msg)

        _reject_dependency_cycles(task_by_id)
        return self


# Compatibility alias for earlier milestones. New planner code should use
# ExecutionPlan directly.
Plan = ExecutionPlan


def _reject_dependency_cycles(task_by_id: dict[str, ExecutionTask]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            msg = f"ExecutionPlan contains a dependency cycle at task: {task_id}"
            raise ValueError(msg)

        visiting.add(task_id)
        for dependency in task_by_id[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_by_id:
        visit(task_id)


class ToolSelection(BaseModel):
    """Validated selector output for zero or one tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: StrictStr | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool_name")
    @classmethod
    def reject_empty_tool_name(cls, tool_name: str | None) -> str | None:
        if tool_name is not None and not tool_name.strip():
            msg = "Tool name must be non-empty when provided."
            raise ValueError(msg)

        return tool_name.strip() if tool_name is not None else None

    @field_validator("arguments")
    @classmethod
    def reject_non_string_argument_names(
        cls, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if any(not isinstance(name, str) for name in arguments):
            msg = "Tool argument names must be strings."
            raise ValueError(msg)

        return arguments

    @model_validator(mode="after")
    def reject_no_tool_arguments(self) -> "ToolSelection":
        if self.tool_name is None and self.arguments:
            msg = "No-tool selections must not include arguments."
            raise ValueError(msg)

        return self
