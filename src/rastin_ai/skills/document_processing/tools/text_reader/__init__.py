"""File guide.

- Use: Exports the reader tool and schemas for plain text files.
- Usage: Import from
  rastin_ai.skills.document_processing.tools.text_reader.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.text_reader.schemas, and
  rastin_ai.skills.document_processing.tools.text_reader.tool.
"""

from .schemas import TextReaderInput, TextReaderOutput
from .tool import TextReaderError, TextReaderTool

__all__ = [
    "TextReaderError",
    "TextReaderInput",
    "TextReaderOutput",
    "TextReaderTool",
]
