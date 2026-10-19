"""File guide.

- Use: Contains unit tests for structured agent schemas.
- Usage: Run this file with pytest when checking planner output contracts.
- Duties: Builds ExecutionPlan models and checks validation boundaries.
- Depends on: External packages: pydantic. Project modules:
  rastin_ai.agent.schemas.
"""

import pytest
from pydantic import ValidationError

from rastin_ai.agent.schemas import (
    ExecutionPlan,
    ExecutionTask,
    LiteralArgument,
    TaskOutputReference,
    ToolSelection,
)


def test_valid_execution_task_is_accepted() -> None:
    task = ExecutionTask(
        id="task_1",
        capability="test.capability",
        arguments={"query": LiteralArgument(value="project risks")},
    )

    assert task.id == "task_1"
    assert task.capability == "test.capability"
    assert task.arguments["query"] == LiteralArgument(value="project risks")


@pytest.mark.parametrize(
    "field",
    (
        {"id": " ", "capability": "test.capability"},
        {"id": "task_1", "capability": " "},
    ),
)
def test_execution_task_rejects_empty_identity_fields(field: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        ExecutionTask(**field)


def test_execution_task_rejects_duplicate_dependencies() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        ExecutionTask(
            id="task_2",
            capability="test.capability",
            depends_on=["task_1", "task_1"],
        )


def test_execution_task_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError, match="depend on itself"):
        ExecutionTask(
            id="task_1",
            capability="test.capability",
            depends_on=["task_1"],
        )


def test_valid_single_task_execution_plan_is_accepted() -> None:
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.capability",
                arguments={"query": LiteralArgument(value="project risks")},
            )
        ]
    )

    assert plan.tasks[0].id == "task_1"


def test_multiple_independent_tasks_are_structurally_valid() -> None:
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.search"),
            ExecutionTask(id="task_2", capability="test.analyze"),
        ]
    )

    assert [task.depends_on for task in plan.tasks] == [[], []]


def test_dependent_task_with_output_references_is_valid() -> None:
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(id="task_1", capability="test.search"),
            ExecutionTask(id="task_2", capability="test.analyze"),
            ExecutionTask(
                id="task_3",
                capability="test.report",
                arguments={
                    "documents": TaskOutputReference(
                        task_id="task_1",
                        path="results",
                    ),
                    "analysis": TaskOutputReference(task_id="task_2"),
                },
                depends_on=["task_1", "task_2"],
            ),
        ]
    )

    assert plan.tasks[2].arguments["documents"] == TaskOutputReference(
        task_id="task_1",
        path="results",
    )


def test_execution_plan_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ExecutionPlan(
            tasks=[
                ExecutionTask(id="task_1", capability="test.search"),
                ExecutionTask(id="task_1", capability="test.analyze"),
            ]
        )


def test_execution_plan_rejects_missing_dependency_target() -> None:
    with pytest.raises(ValidationError, match="unknown task IDs"):
        ExecutionPlan(
            tasks=[
                ExecutionTask(
                    id="task_2",
                    capability="test.analyze",
                    depends_on=["task_1"],
                )
            ]
        )


def test_execution_plan_rejects_dependency_cycle() -> None:
    with pytest.raises(ValidationError, match="dependency cycle"):
        ExecutionPlan(
            tasks=[
                ExecutionTask(
                    id="task_1",
                    capability="test.search",
                    depends_on=["task_2"],
                ),
                ExecutionTask(
                    id="task_2",
                    capability="test.analyze",
                    depends_on=["task_1"],
                ),
            ]
        )


def test_execution_plan_rejects_unknown_output_reference() -> None:
    with pytest.raises(ValidationError, match="unknown task output"):
        ExecutionPlan(
            tasks=[
                ExecutionTask(
                    id="task_1",
                    capability="test.analyze",
                    arguments={"source": TaskOutputReference(task_id="missing_task")},
                )
            ]
        )


def test_execution_plan_rejects_non_upstream_output_reference() -> None:
    with pytest.raises(ValidationError, match="non-upstream"):
        ExecutionPlan(
            tasks=[
                ExecutionTask(id="task_1", capability="test.search"),
                ExecutionTask(
                    id="task_2",
                    capability="test.analyze",
                    arguments={"source": TaskOutputReference(task_id="task_1")},
                ),
            ]
        )


def test_execution_plan_serializes_and_validates_round_trip() -> None:
    plan = ExecutionPlan(
        tasks=[
            ExecutionTask(
                id="task_1",
                capability="test.search",
                arguments={"query": LiteralArgument(value="risks")},
            )
        ],
        response_strategy="Summarize deterministic task results.",
    )

    assert ExecutionPlan.model_validate(plan.model_dump()) == plan


def test_valid_tool_selection_is_accepted() -> None:
    selection = ToolSelection(
        tool_name="calculator",
        arguments={"expression": "2 + 2"},
    )

    assert selection.tool_name == "calculator"
    assert selection.arguments == {"expression": "2 + 2"}


def test_no_tool_selection_is_accepted() -> None:
    selection = ToolSelection(tool_name=None, arguments={})

    assert selection.tool_name is None
    assert selection.arguments == {}


def test_tool_selection_rejects_malformed_tool_name_type() -> None:
    with pytest.raises(ValidationError):
        ToolSelection(tool_name=123, arguments={})


def test_tool_selection_rejects_malformed_arguments() -> None:
    with pytest.raises(ValidationError):
        ToolSelection(tool_name="calculator", arguments=["not", "a", "dict"])


def test_tool_selection_rejects_no_tool_with_arguments() -> None:
    with pytest.raises(ValidationError, match="No-tool selections"):
        ToolSelection(tool_name=None, arguments={"expression": "2 + 2"})
