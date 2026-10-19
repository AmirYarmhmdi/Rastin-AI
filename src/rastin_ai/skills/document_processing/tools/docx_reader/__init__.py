"""File guide.

- Use: Exports the reader tool and schemas for DOCX files.
- Usage: Import from
  rastin_ai.skills.document_processing.tools.docx_reader.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.docx_reader.schemas, and
  rastin_ai.skills.document_processing.tools.docx_reader.tool.
"""

from .schemas import DOCXParagraph, DOCXReaderInput, DOCXReaderOutput, DOCXTable
from .tool import DOCXReaderError, DOCXReaderTool

__all__ = [
    "DOCXParagraph",
    "DOCXReaderError",
    "DOCXReaderInput",
    "DOCXReaderOutput",
    "DOCXReaderTool",
    "DOCXTable",
]
