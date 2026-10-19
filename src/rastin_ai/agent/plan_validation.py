"""File guide.

- Use: Validates ExecutionPlan objects against canonical capabilities.
- Usage: Import ExecutionPlanValidator from rastin_ai.agent.plan_validation.
- Duties: Checks executable capability references without executing tasks.
- Depends on: Project modules: rastin_ai.agent.schemas and
  rastin_ai.skills.registry.
"""

from rastin_ai.agent.schemas import ExecutionPlan
from rastin_ai.skills.registry import SkillRegistry


class ExecutionPlanValidationError(ValueError):
    pass


class ExecutionPlanValidator:
    """Validate structured plans against the canonical Skills registry."""

    def validate(
        self,
        plan: ExecutionPlan,
        *,
        skill_registry: SkillRegistry,
    ) -> ExecutionPlan:
        for task in plan.tasks:
            if skill_registry.get_capability(task.capability) is None:
                msg = f"Task references unavailable capability: {task.capability}"
                raise ExecutionPlanValidationError(msg)

        return plan
