# Excel Sheet Reader Tool

The Excel Sheet Reader Tool deterministically extracts worksheet rows from one
named sheet in a local `.xlsx` workbook.

- Capability: `document.read.excel.sheet`
- Input: `ExcelSheetReaderInput(path: Path, sheet_name: str, max_rows: int | None)`
- Output: `ExcelSheetReaderOutput`
- Supported format: `.xlsx`

The output preserves worksheet rows as rows and cell positions as cells. It does
not assume the first row is a header and does not transform worksheets into
records or dictionaries.

Formula policy: workbooks are opened with `data_only=False`, so formula cells
return their stored formula expressions, such as `=SUM(A1:A2)`. The Tool does
not calculate formulas.

`max_rows` is an optional positive safety limit on returned rows. When it limits
the returned data, `truncated` is `true`. `row_count` and `column_count` still
describe the worksheet dimensions reported by `openpyxl`.

Limitations:

- No filtering, sorting, aggregation, statistics, or data cleaning.
- No formula evaluation.
- No pandas or dataframe output.
- No remote URL fetching.
- No LLM calls or business analysis.
