# CSV Reader Tool

The CSV Reader Tool deterministically reads rows and string cells from local
`.csv` files.

- Capability: `document.read.csv`
- Input: `CSVReaderInput(path: Path, delimiter: str | None, encoding: str, max_rows: int | None)`
- Output: `CSVReaderOutput`
- Supported format: `.csv`

Delimiter policy:

- If `delimiter` is provided, that exact one-character delimiter is used.
- If `delimiter` is omitted, Python's `csv.Sniffer` is used with only these
  common delimiters: comma, semicolon, tab, and pipe.
- If detection fails, the Tool raises a reader error instead of guessing.

Encoding policy:

- The default encoding is `utf-8`.
- Caller-provided encodings are passed directly to file opening.
- Automatic encoding detection is not performed.

`max_rows` is an optional positive safety limit on returned rows. `row_count`
still reports the total number of rows in the file, and `truncated` is `true`
when the returned rows are limited.

Rows are preserved as rows. The first row is not treated as a header, and rows
are not converted to dictionaries.

CSV cells are returned as strings. Empty fields remain empty strings. No type
inference is performed.

Limitations:

- No filtering, sorting, grouping, aggregation, statistics, or data cleaning.
- No schema inference beyond basic row and column counts.
- No automatic encoding detection.
- No pandas or dataframe output.
- No LLM calls or business analysis.
