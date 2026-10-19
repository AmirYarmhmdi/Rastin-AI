"""File guide.

- Use: Exports the reader tool and schemas for CSV files.
- Usage: Import from
  rastin_ai.skills.document_processing.tools.csv_reader.__init__ to use the
  package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules:
  rastin_ai.skills.document_processing.tools.csv_reader.schemas, and
  rastin_ai.skills.document_processing.tools.csv_reader.tool.
"""

from .schemas import CSVReaderInput, CSVReaderOutput
from .tool import CSVReaderError, CSVReaderTool

__all__ = [
    "CSVReaderError",
    "CSVReaderInput",
    "CSVReaderOutput",
    "CSVReaderTool",
]
