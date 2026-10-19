# Document Processing Skill

The Document Processing Skill is the Rastin-AI boundary for deterministic
processing of supported document and file formats.

A Skill is a higher-level capability grouping and orchestration boundary. A Tool
is a deterministic executable operation owned by a Skill.

This Skill owns file readers and related deterministic parsing operations. Its
current and planned initial tools are:

- PDF Reader: implemented for local, text-based PDF text extraction.
- Excel Workbook Reader: implemented for `.xlsx` structure inspection.
- Excel Sheet Reader: implemented for deterministic `.xlsx` worksheet row
  extraction.
- CSV Reader: implemented for deterministic delimited text row extraction.
- Text Reader: implemented for deterministic `.txt` raw text extraction.
- JSON Reader: implemented for deterministic `.json` parsing with native JSON
  value preservation.
- DOCX Reader: implemented for deterministic `.docx` paragraph, table, and
  metadata extraction.

Reader tools should parse files and return structured results. The LLM or
orchestrator should select and coordinate these tools instead of performing file
parsing itself.

Future document-processing steps may add more readers or richer extraction, but
analysis behavior remains outside this Skill's reader tools.
