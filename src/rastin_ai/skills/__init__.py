"""File guide.

- Use: Exports the public Skill framework objects.
- Usage: Import from rastin_ai.skills.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.skills.base,
  rastin_ai.skills.registry, and rastin_ai.skills.tool.
"""

from rastin_ai.skills.base import BaseSkill, SkillMetadata
from rastin_ai.skills.capabilities import CapabilityDefinition, CapabilityPromptView
from rastin_ai.skills.registry import SkillRegistry
from rastin_ai.skills.tool import BaseTool

__all__ = [
    "BaseSkill",
    "BaseTool",
    "CapabilityDefinition",
    "CapabilityPromptView",
    "SkillMetadata",
    "SkillRegistry",
]
