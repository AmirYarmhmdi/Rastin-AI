"""File guide.

- Use: Exports the reader tool and schemas for JSON files.
- Usage: Import from
  rastin_ai.skills.document_processing.tools.json_reader.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.json_reader.schemas, and
  rastin_ai.skills.document_processing.tools.json_reader.tool.
"""

from .schemas import JSONReaderInput, JSONReaderOutput, JSONScalar, JSONValue
from .tool import JSONReaderError, JSONReaderTool

__all__ = [
    "JSONReaderError",
    "JSONReaderInput",
    "JSONReaderOutput",
    "JSONReaderTool",
    "JSONScalar",
    "JSONValue",
]
