# Excel Workbook Reader Tool

The Excel Workbook Reader Tool performs deterministic structure inspection for
local `.xlsx` workbooks.

- Capability: `document.read.excel.workbook`
- Input: `ExcelWorkbookReaderInput(path: Path)`
- Output: `ExcelWorkbookReaderOutput`
- Supported format: `.xlsx`

The output includes the source path, sheet count, workbook-order sheet entries,
1-based sheet indices, worksheet dimensions from `openpyxl`, and basic
serialized workbook metadata.

This Tool inspects workbook structure only. It does not return full worksheet
cell data, evaluate formulas, filter rows, calculate statistics, inspect charts,
or call an LLM.

Worksheet `max_row` and `max_column` values come from the spreadsheet library's
standard dimension information. Those dimensions can reflect previously used or
formatted cells and should not be treated as a perfect semantic data range.
