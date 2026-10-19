# Tool Contracts

> This document defines the formal contracts for every deterministic tool available in Rastin-AI.
>
> A Tool Contract specifies the expected interface, execution behavior, validation rules, error handling, and runtime guarantees.
>
> Tool Contracts act as the boundary between the Agent and the implementation.

---

# Traceability

## Inputs

- 08-tool-specification.md
- 07-workflow-architecture.md
- 08-agent-state-machine.md

## Outputs

- FastAPI Implementation
- LangGraph Nodes
- Unit Tests
- Integration Tests

---

# Contract Design Principles

Every Tool Contract shall define:

- purpose
- interface
- inputs
- outputs
- validation
- execution guarantees
- error model
- observability
- security constraints

The implementation must conform to the contract.

---

# Common Contract Schema

Every tool follows the same structure.

```yaml
name:
version:
category:

description:

deterministic:

timeout:

retryable:

idempotent:

required_state:

next_state:

inputs:

outputs:

errors:

observability:

security:
```

---

# TOOL-001 — Document Reader

```yaml
name: document_reader

version: 1.0

category: document

description:
Extract text and metadata from PDF documents.

deterministic: true

timeout: 30s

retryable: false

idempotent: true

required_state:
  - ContextResolved

next_state:
  - EvidenceRetrieved

inputs:

  file_id:
    type: UUID
    required: true

outputs:

  text:
    type: string

  pages:
    type: array

  metadata:
    type: object

errors:

  FILE_NOT_FOUND

  INVALID_DOCUMENT

  EMPTY_DOCUMENT

observability:

  trace: true

  execution_time: true

security:

  readonly: true
```

---

# TOOL-002 — Spreadsheet Analyzer

```yaml
name: spreadsheet_analyzer

version: 1.0

category: spreadsheet

description:
Analyze Excel workbooks.

deterministic: true

timeout: 60s

retryable: false

idempotent: true

required_state:

  - ContextResolved

next_state:

  - ToolExecuted

inputs:

  file_id:

    type: UUID

outputs:

  worksheets:

    type: array

  schema:

    type: object

  statistics:

    type: object

errors:

  INVALID_WORKBOOK

  EMPTY_WORKBOOK

  FILE_NOT_FOUND

observability:

  trace: true

security:

  readonly: true
```

---

# TOOL-003 — CSV Analyzer

```yaml
name: csv_analyzer

version: 1.0

category: structured_data

description:
Analyze CSV datasets.

deterministic: true

timeout: 30s

retryable: false

idempotent: true

required_state:

  - ContextResolved

next_state:

  - ToolExecuted

inputs:

  file_id:
    type: UUID

outputs:

  dataframe:
    type: DataFrame

  statistics:
    type: object

errors:

  INVALID_CSV

  EMPTY_DATASET

  FILE_NOT_FOUND
```

---

# TOOL-004 — Retrieval Tool

```yaml
name: retrieval_tool

version: 1.0

category: retrieval

description:
Retrieve relevant evidence from the vector database.

deterministic: true

timeout: 10s

retryable: true

idempotent: true

required_state:

  - IntentUnderstood

next_state:

  - EvidenceRetrieved

inputs:

  query:
    type: string

  document_ids:
    type: array

outputs:

  chunks:
    type: array

  similarity_scores:
    type: array

errors:

  NO_MATCHES

  VECTOR_STORE_UNAVAILABLE
```

---

# TOOL-005 — Python Executor

```yaml
name: python_executor

version: 1.0

category: computation

description:
Execute deterministic analytical computations.

deterministic: true

timeout: 120s

retryable: false

idempotent: true

required_state:

  - WorkflowPlanned

next_state:

  - ToolExecuted

inputs:

  operation:
    type: string

  payload:
    type: object

outputs:

  result:
    type: object

errors:

  INVALID_OPERATION

  INVALID_INPUT

  EXECUTION_ERROR

security:

  readonly: true

  internet_access: false

  shell_access: false
```

---

# TOOL-006 — Comparison Engine

```yaml
name: comparison_engine

version: 1.0

category: reasoning

description:
Compare structured and unstructured information.

deterministic: mostly

timeout: 60s

retryable: false

idempotent: true

required_state:

  - EvidenceRetrieved

next_state:

  - ToolExecuted

inputs:

  sources:
    type: array

outputs:

  similarities:
    type: array

  differences:
    type: array

  conflicts:
    type: array

errors:

  INSUFFICIENT_EVIDENCE
```

---

# TOOL-007 — Report Generator

```yaml
name: report_generator

version: 1.0

category: reporting

description:
Generate structured reports.

deterministic: true

timeout: 30s

retryable: false

idempotent: true

required_state:

  - ResponseReady

next_state:

  - Completed

inputs:

  findings:
    type: object

outputs:

  markdown:
    type: string

  json:
    type: object

future_outputs:

  pdf

  docx
```

---

# TOOL-008 — Visualization Tool

```yaml
name: visualization_tool

version: 1.0

category: visualization

description:
Generate charts from structured datasets.

deterministic: true

timeout: 30s

retryable: false

idempotent: true

required_state:

  - ToolExecuted

next_state:

  - ResponseReady

inputs:

  dataframe:
    type: object

  chart_type:
    type: string

outputs:

  image:
    type: binary

  specification:
    type: json

errors:

  INVALID_DATASET

  UNSUPPORTED_CHART
```

---

# Contract Compatibility

Every Tool Contract shall be compatible with:

- LangGraph Nodes
- FastAPI Endpoints
- MCP Tools
- OpenAI Tool Calling
- Anthropic Tool Use
- Future Agent Frameworks

No redesign should be required.

---

# Runtime Guarantees

Every Tool Contract guarantees:

- deterministic behavior whenever applicable
- typed inputs
- typed outputs
- explicit validation
- structured errors
- execution trace
- timeout protection
- independent testing

---

# Versioning Policy

Tool Contracts follow semantic versioning.

Examples:

```
1.0.0
```

Initial stable interface.

```
1.1.0
```

Backward-compatible additions.

```
2.0.0
```

Breaking changes.

Older versions should remain supported whenever practical.

---

# Testing Requirements

Every Tool Contract shall have:

- unit tests
- integration tests
- contract validation tests
- error handling tests
- timeout tests

Contract compliance must be verified automatically during CI.

---

# Future Extensions

Future versions may introduce:

- MCP Tool Registry
- Tool Discovery
- Tool Permissions
- Tool Capability Negotiation
- Parallel Tool Execution
- Remote Tool Invocation

The current contract model is intentionally designed to support these capabilities without requiring interface redesign.