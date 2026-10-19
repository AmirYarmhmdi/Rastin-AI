# DOCX Reader Tool

The DOCX Reader Tool deterministically extracts useful textual structure from
local Microsoft Word `.docx` files.

- Capability: `document.read.docx`
- Supported extension: `.docx`
- Input: `DOCXReaderInput(path: Path)`
- Output: `DOCXReaderOutput`

Paragraph behavior:

- Main document body paragraphs are returned in paragraph order.
- Paragraph indices are 1-based.
- Empty paragraphs are preserved.
- Paragraph text is not stripped or semantically classified.

Table behavior:

- Tables are returned in table order.
- Table indices are 1-based.
- Row and cell order are preserved.
- Cell values are returned as strings.
- The first row is not interpreted as a header.

Metadata behavior:

- Basic core document properties are normalized to `str | None`.
- Date/time values are serialized as ISO 8601 strings.

Limitations:

- Paragraphs and tables are exposed as separate ordered collections; exact
  interleaved body order is not represented.
- No OCR or image extraction.
- No exact visual layout or advanced style reconstruction.
- No advanced hyperlink extraction.
- No comments, revisions, or tracked-change analysis.
- No advanced header/footer extraction.
- No NLP, summarization, chunking, embeddings, or LLM processing.
