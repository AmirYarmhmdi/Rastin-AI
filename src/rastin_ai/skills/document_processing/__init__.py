"""File guide.

- Use: Exports the Document Processing Skill.
- Usage: Import from rastin_ai.skills.document_processing.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.skills.document_processing.skill.
"""

from rastin_ai.skills.document_processing.skill import DocumentProcessingSkill

__all__ = ["DocumentProcessingSkill"]
