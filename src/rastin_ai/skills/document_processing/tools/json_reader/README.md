# JSON Reader Tool

The JSON Reader Tool deterministically reads and parses local `.json` files
using Python's standard-library JSON parser.

- Capability: `document.read.json`
- Supported extension: `.json`
- Input: `JSONReaderInput(path: Path, encoding: str)`
- Output: `JSONReaderOutput`

Encoding policy:

- The default encoding is `utf-8`.
- Caller-provided encodings are used explicitly.
- Automatic encoding detection is not performed.
- Unknown encodings and decoding failures raise a reader error.

Root types:

- `object`
- `array`
- `string`
- `number`
- `boolean`
- `null`

The parsed `data` preserves standard JSON value types: objects become
dictionaries, arrays become lists, strings remain strings, numbers remain Python
JSON parser numbers, booleans remain booleans, and `null` becomes `None`.

`item_count` reports the number of top-level object keys or array items. It is
`None` for scalar and null roots.

Duplicate object keys follow Python standard-library JSON parsing semantics.

Limitations:

- No JSONPath.
- No filtering, flattening, transformation, or aggregation.
- No JSON Schema validation.
- No type inference beyond standard JSON parsing.
- No JSONL or NDJSON support.
- No streaming parser for very large files.
- No LLM processing.
