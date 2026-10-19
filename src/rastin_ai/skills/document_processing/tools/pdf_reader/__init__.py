"""File guide.

- Use: Exports the reader tool and schemas for PDF files.
- Usage: Import from
  rastin_ai.skills.document_processing.tools.pdf_reader.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.pdf_reader.schemas, and
  rastin_ai.skills.document_processing.tools.pdf_reader.tool.
"""

from rastin_ai.skills.document_processing.tools.pdf_reader.schemas import (
    PDFPage,
    PDFReaderInput,
    PDFReaderOutput,
)
from rastin_ai.skills.document_processing.tools.pdf_reader.tool import (
    PDFReaderError,
    PDFReaderTool,
)

__all__ = [
    "PDFPage",
    "PDFReaderError",
    "PDFReaderInput",
    "PDFReaderOutput",
    "PDFReaderTool",
]
