# PDF Reader Tool

The PDF Reader Tool performs deterministic text extraction from local,
text-based PDF files.

- Capability: `document.read.pdf`
- Input: `PDFReaderInput(path: Path)`
- Output: `PDFReaderOutput`

The output includes the source path, page count, 1-based page entries, extracted
page text, and basic normalized PDF metadata.

Supported behavior:

- Validate that the input path exists.
- Validate that the input is a file with a `.pdf` extension.
- Read the PDF with `pypdf`.
- Extract text page by page.
- Normalize missing page text to an empty string.

Limitations:

- No OCR.
- No image extraction.
- No table extraction.
- No document chunking, retrieval, summarization, embeddings, or LLM calls.
- No remote URL fetching.
