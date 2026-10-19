# Tool Specification

> This document defines the deterministic tools available to the Rastin-AI agent.
>
> Tools perform deterministic operations.
>
> They do not make decisions.
>
> The LLM is responsible for deciding **when** a tool should be used.
> The tool is responsible for performing **how** the operation is executed.

---

# Traceability

## Inputs

- 03-functional-requirements.md
- 07-workflow-architecture.md
- 08-agent-state-machine.md

## Outputs

- 09-api-specification.md
- 10-database-design.md

---

# Design Principles

Every tool shall:

- have a single responsibility
- be deterministic whenever possible
- be independently testable
- expose typed inputs and outputs
- avoid business logic
- avoid LLM reasoning
- return structured results
- expose meaningful error messages

---

# Tool Lifecycle

Every tool follows the same lifecycle.

Input

↓

Validation

↓

Execution

↓

Structured Result

↓

Error Handling

↓

Observability

---

# Tool Categories

| Category | Purpose |
|------------|---------|
| Document | Read documents |
| Spreadsheet | Analyze Excel |
| CSV | Analyze tabular data |
| Retrieval | Retrieve evidence |
| Python | Execute deterministic computations |
| Reporting | Generate reports |
| Visualization | Produce charts |
| Utility | Session and metadata utilities |

---

# TOOL-001 — Document Reader

## Purpose

Extract structured information from PDF documents.

## Inputs

- file_id

## Outputs

```json
{
  "pages": [],
  "text": "...",
  "metadata": {}
}
```

## Deterministic

✅ Yes

## Used During

- Context Resolution
- Evidence Retrieval

## Possible Errors

- Unsupported file
- Corrupted PDF
- Empty document

---

# TOOL-002 — Spreadsheet Analyzer

## Purpose

Read and inspect Excel workbooks.

## Inputs

- file_id

## Outputs

```json
{
  "worksheets": [],
  "columns": [],
  "rows": [],
  "summary": {}
}
```

## Capabilities

- inspect sheets

- infer schema

- summarize columns

- detect missing values

## Deterministic

✅ Yes

---

# TOOL-003 — CSV Analyzer

## Purpose

Read CSV datasets.

## Inputs

- file_id

## Outputs

Structured dataframe.

## Supported Operations

- filtering

- aggregation

- statistics

- grouping

- sorting

## Deterministic

✅ Yes

---

# TOOL-004 — Retrieval Tool

## Purpose

Retrieve relevant evidence.

## Inputs

- question
- document_ids

## Outputs

Relevant chunks

Similarity scores

Metadata

## Backend

Qdrant

## Deterministic

Yes

---

# TOOL-005 — Python Executor

## Purpose

Execute deterministic analytical operations.

## Inputs

Execution request

Structured data

## Examples

- statistics

- comparison

- calculations

- transformations

## Restrictions

Cannot access LLM.

Cannot call external APIs.

Cannot modify source files.

## Deterministic

Yes

---

# TOOL-006 — Comparison Engine

## Purpose

Compare heterogeneous information.

Examples

PDF

+

Excel

+

CSV

↓

Comparison

## Outputs

Differences

Similarities

Conflicts

Evidence

## Deterministic

Mostly

Depends on retrieved evidence.

---

# TOOL-007 — Report Generator

## Purpose

Generate structured reports.

Supported Sections

- Executive Summary

- Findings

- Evidence

- Recommendations

- References

## Output Formats

Markdown

JSON

Future

PDF

DOCX

---

# TOOL-008 — Visualization Tool

## Purpose

Produce charts.

Examples

- line charts

- bar charts

- histograms

- scatter plots

## Output

Image

Metadata

Chart specification

---

# Tool Invocation Rules

The agent shall invoke tools only when:

- sufficient inputs exist

- required files exist

- workflow planning completed

- previous dependencies completed

The agent shall NOT invoke tools:

- with missing inputs

- when deterministic execution is unnecessary

- if validation fails

---

# Tool Execution Policy

The LLM SHALL

- select tools

- order execution

- interpret outputs

The LLM SHALL NOT

- perform numerical computation

- parse spreadsheets

- calculate statistics

- generate charts

These tasks belong to deterministic tools.

---

# Error Handling

Every tool shall return structured errors.

Example

```json
{
  "status":"failed",
  "error_code":"FILE_NOT_FOUND",
  "message":"Requested document does not exist."
}
```

The agent should decide how to recover.

---

# Observability

Every tool invocation shall record:

- tool name

- inputs

- execution time

- success/failure

- output metadata

- trace id

Future implementation:

Langfuse

OpenTelemetry

---

# Security Constraints

Tools shall never:

- execute arbitrary shell commands

- expose API keys

- modify uploaded files

- bypass validation

---

# Future MCP Compatibility

Every tool should eventually be exposable as an MCP Tool.

Requirements:

- typed interface

- JSON input

- JSON output

- stateless behavior

No redesign should be required.

---

# Future Tool Registry

Every tool will eventually be registered in a Tool Registry.

Example

| Tool | Category | State | Deterministic |
|------|----------|---------------|---------------|
| Document Reader | Document | Ready | Yes |
| Spreadsheet Analyzer | Spreadsheet | Ready | Yes |
| CSV Analyzer | Spreadsheet | Ready | Yes |
| Retrieval Tool | Retrieval | Ready | Yes |
| Python Executor | Computation | Ready | Yes |
| Comparison Engine | Analysis | Planned | Mostly |
| Report Generator | Reporting | Planned | Yes |
| Visualization Tool | Visualization | Planned | Yes |

---

# Tool Selection Matrix

| Workflow Stage | Tool |
|----------------|------|
| Context Resolution | Document Reader |
| Evidence Retrieval | Retrieval Tool |
| Spreadsheet Analysis | Spreadsheet Analyzer |
| CSV Analysis | CSV Analyzer |
| Computation | Python Executor |
| Comparison | Comparison Engine |
| Reporting | Report Generator |
| Visualization | Visualization Tool |

---

# Engineering Philosophy

Tools are not intelligent.

They are reliable software components.

The intelligence of Rastin-AI emerges from the orchestration of deterministic tools rather than from the tools themselves.

This separation enables:

- explainability
- maintainability
- reproducibility
- testing
- production-grade reliability