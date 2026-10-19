# Text Reader Tool

The Text Reader Tool deterministically reads raw text from local `.txt` files.

- Capability: `document.read.text`
- Supported extension: `.txt`
- Input: `TextReaderInput(path: Path, encoding: str, max_chars: int | None)`
- Output: `TextReaderOutput`

Encoding policy:

- The default encoding is `utf-8`.
- Caller-provided encodings are used explicitly.
- Automatic encoding detection is not performed.
- Unknown encodings and decoding failures raise a reader error.

Text preservation policy:

- The decoded text is returned without stripping whitespace.
- Blank lines, indentation, leading whitespace, and trailing whitespace are
  preserved.
- No Markdown parsing or text cleaning is performed.

Line-count policy:

- `line_count` uses Python's `str.splitlines()` semantics.
- An empty file has `line_count = 0`.
- A trailing newline does not create an extra empty logical line.

`max_chars` is an optional positive safety limit on returned text. It limits
only the returned `text`; `char_count` and `line_count` still describe the full
decoded file. `truncated` is `true` only when `max_chars` prevents returning the
entire text.

Limitations:

- No Markdown parsing.
- No text cleaning or normalization.
- No tokenization, chunking, embeddings, NLP, or language detection.
- No remote URL fetching.
- No LLM processing.
