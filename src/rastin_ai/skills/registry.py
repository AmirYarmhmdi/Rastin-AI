"""File guide.

- Use: Registers Skills and canonical capability definitions.
- Usage: Import DuplicateSkillError, DuplicateCapabilityError, and SkillRegistry
  from rastin_ai.skills.registry.
- Duties: Defines SkillRegistry and capability lookup/projection helpers.
- Depends on: Project modules: rastin_ai.skills.base and
  rastin_ai.skills.capabilities.
"""

from rastin_ai.skills.base import BaseSkill
from rastin_ai.skills.capabilities import CapabilityDefinition, CapabilityPromptView


class DuplicateSkillError(ValueError):
    pass


class DuplicateCapabilityError(ValueError):
    pass


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._capabilities: dict[str, CapabilityDefinition] = {}

    def register(self, skill: BaseSkill) -> None:
        if skill.name in self._skills:
            msg = f"Skill already registered: {skill.name}"
            raise DuplicateSkillError(msg)

        for capability in skill.capability_definitions:
            self._ensure_unique_capability(capability)

        self._skills[skill.name] = skill
        for capability in skill.capability_definitions:
            self._capabilities[capability.name] = capability

    def register_capability(self, capability: CapabilityDefinition) -> None:
        self._ensure_unique_capability(capability)
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_skills(self) -> tuple[BaseSkill, ...]:
        return tuple(self._skills.values())

    def find_by_capability(self, capability: str) -> tuple[BaseSkill, ...]:
        """Find skills that declare a capability, regardless of executable tools."""
        return tuple(
            skill for skill in self._skills.values() if capability in skill.capabilities
        )

    def get_capability(self, name: str) -> CapabilityDefinition | None:
        return self._capabilities.get(name)

    def list_capabilities(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._capabilities.values())

    def get_capability_prompt_views(self) -> tuple[CapabilityPromptView, ...]:
        return tuple(
            capability.to_prompt_view() for capability in self.list_capabilities()
        )

    def _ensure_unique_capability(self, capability: CapabilityDefinition) -> None:
        existing = self._capabilities.get(capability.name)
        if existing is not None:
            msg = f"Capability already registered: {capability.name}"
            raise DuplicateCapabilityError(msg)
