# API Specification

> This document defines the public REST API of Rastin-AI.
>
> The API follows a **Design First** approach. Endpoints are specified before implementation to ensure consistency, testability, and maintainability.
>
> All endpoints exchange JSON unless otherwise specified.

---

# Traceability

## Inputs

- 03-functional-requirements.md
- 06-high-level-architecture.md
- 08-tool-specification.md
- 09-tool-contracts.md

## Outputs

- FastAPI Implementation
- OpenAPI Specification
- Integration Tests
- SDK Generation

---

# API Design Principles

The API shall:

- be RESTful
- use JSON
- expose deterministic endpoints
- provide consistent error responses
- support versioning
- remain stateless
- be fully documented

---

# Base URL

```
/api/v1
```

---

# Authentication

## MVP

Authentication is outside the MVP scope.

Future versions may support:

- OAuth2
- JWT
- Azure Entra ID
- API Keys

---

# Common Response Format

## Success

```json
{
  "status": "success",
  "data": {}
}
```

---

## Error

```json
{
  "status": "error",
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "Requested file does not exist."
  }
}
```

---

# Resource Model

Rastin-AI exposes the following resources:

- Sessions
- Documents
- Questions
- Workflows
- Reports
- Traces

---

# Conversation Session API

Conversation sessions are created by `POST /messages` when a caller omits
`session_id`. The public session API is read-only in this phase.

## List Sessions

GET

```
/sessions
```

Response

```json
{
  "sessions": [
    {
      "id": "conversation-session-uuid",
      "title": "First user message",
      "status": "active",
      "created_at": "timestamp",
      "updated_at": "timestamp"
    }
  ]
}
```

---

## Get Session

GET

```
/sessions/{session_id}
```

Response

```json
{
  "id": "conversation-session-uuid",
  "title": "First user message",
  "status": "active",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "messages": [
    {
      "id": "message-uuid",
      "role": "assistant",
      "sequence": 2,
      "content": "...",
      "workflow_id": "workflow-uuid",
      "status": "answered",
      "error_message": null,
      "citations": [],
      "sources": [],
      "document_references": [],
      "created_at": "timestamp"
    }
  ]
}
```

---

# Document API

## Upload Document

POST

```
/documents
```

Content-Type

```
multipart/form-data
```

Supported formats

- PDF
- CSV
- XLSX
- DOCX
- JSON
- TXT
- Markdown

Response

```json
{
  "document_id": "uuid",
  "filename": "example.pdf",
  "content_type": "application/pdf",
  "status": "indexed",
  "workflow_id": null,
  "file_metadata_id": "uuid",
  "normalized_extension": ".pdf",
  "size_bytes": 12345,
  "checksum_sha256": "sha256-hex",
  "file_storage_status": "stored",
  "indexing_error_code": null,
  "indexing_error_message": null,
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

Runtime behavior: the original bytes are saved through the configured storage
provider under an owner-aware key. PostgreSQL creates one authenticated-user
owned logical `documents` row and one linked `file_metadata` row in the same
database transaction. The endpoint then
synchronously sets the document to `processing`, reads the file back through the
storage provider, extracts text for supported formats, chunks, embeds, deletes
prior Qdrant chunks for the same logical `document_id` and local `user_id`,
upserts the replacement chunks with both identifiers in payload metadata, and
sets the document to `indexed`.

Supported indexing formats are PDF, TXT, Markdown, CSV, JSON, DOCX, and XLSX.
All seven public upload formats use the shared deterministic extraction
boundary. Readable files return `201` with `status = indexed` after Qdrant
upsert. Scanned or encrypted PDFs, malformed CSV/JSON, corrupt DOCX/XLSX, empty
documents, embedding failures, or Qdrant failures return `201` with
`status = failed` and safe failure details. Indexing failures do not delete the
original file or linked metadata. Storage or upload metadata persistence
failures remain non-2xx; if storage succeeds but database persistence fails, the
API attempts a best-effort delete of the stored object and returns the original
persistence error.

---

## List Documents

GET

```
/documents
```

Response

```json
{
  "documents": [
    {
      "id": "uuid",
      "filename": "example.pdf",
      "content_type": "application/pdf",
      "status": "indexed",
      "created_at": "timestamp",
      "file_metadata_id": "uuid",
      "normalized_extension": ".pdf",
      "size_bytes": 12345,
      "checksum_sha256": "sha256-hex",
      "file_storage_status": "stored",
      "indexing_error_code": null,
      "indexing_error_message": null,
      "updated_at": "timestamp"
    }
  ]
}
```

Only documents owned by the authenticated user are returned. Internal storage
keys and backend references are not included in normal public responses.

---

# Question API

## Ask Question

POST

```
/questions
```

Request

```json
{
  "question": "Compare these two reports.",
  "document_ids": ["logical-document-uuid"]
}
```

Response

```json
{
  "answer": "...",
  "workflow_id": "...",
  "status": "answered",
  "message": null,
  "sources": [
    {
      "document_id": "logical-document-uuid",
      "filename": "report.pdf",
      "chunk_id": "chunk_abc123",
      "chunk_index": 0,
      "score": 0.91,
      "location_type": "page",
      "source_location": "page:3",
      "page_number": 3
    }
  ],
  "citations": [
    {
      "document_id": "logical-document-uuid",
      "filename": "report.pdf",
      "chunk_id": "chunk_abc123",
      "chunk_index": 0,
      "score": 0.91,
      "location_type": "page",
      "source_location": "page:3",
      "page_number": 3
    }
  ]
}
```

Persisted-document question answering accepts logical PostgreSQL document UUIDs
only. Before querying Qdrant, the service validates every requested document ID
against PostgreSQL for the authenticated user and checks lifecycle state:

- `indexed`: eligible for retrieval.
- `uploaded` or `processing`: returns `200` with `status = not_ready` and no
  Qdrant or model call.
- `failed`: returns `200` with `status = indexing_failed` and safe indexing
  failure code information only.
- nonexistent ID: returns `404 DOCUMENT_NOT_FOUND`.

If no explicit document IDs are provided, the service does not run an unscoped
vector search. Qdrant retrieval uses both local `user_id` and logical
`document_id` payload filters; guessed document UUIDs are not sufficient for
access. If indexed documents return no retrieved chunks inside the configured
evidence budget, the response is `status = no_evidence` and response generation
is skipped. If retrieved chunks exist but do not provide enough question support,
the response is `status = insufficient_evidence`. Structured citations are
derived from actual retrieved source records, not model prose, and exclude
storage keys, internal paths, and raw document text.

---

# Message API

## Submit Message

POST

```
/messages
```

Content-Type

```
multipart/form-data
```

Fields

- `message`: required user text.
- `session_id`: optional reusable conversation session UUID.
- `document_ids`: optional repeated logical document UUIDs for persisted-document
  RAG scope.
- `files`: optional repeated file attachments.

Response

```json
{
  "workflow_id": "workflow-uuid",
  "session_id": "conversation-session-uuid",
  "user_message_id": "user-message-uuid",
  "assistant_message_id": "assistant-message-uuid",
  "status": "answered",
  "final_answer": "...",
  "attachments": [
    {
      "document_id": "logical-document-uuid",
      "filename": "example.pdf",
      "content_type": "application/pdf",
      "size_bytes": 12345,
      "status": "stored"
    }
  ],
  "sources": [],
  "citations": [],
  "artifacts": [],
  "workflow_details": []
}
```

Runtime behavior: if `session_id` is omitted, the backend creates one reusable
`sessions` row and uses the first message as a compact title. If `session_id` is
provided, PostgreSQL must already contain that session or the endpoint returns
`404 CONVERSATION_SESSION_NOT_FOUND`. The service loads bounded recent history
from PostgreSQL using `CONVERSATION_HISTORY_MAX_TURNS` and
`CONVERSATION_HISTORY_MAX_CHARS`, then invokes the orchestration router. The
router chooses either the existing direct RAG/attachment QA path or the LangGraph
orchestration path. It persists the user turn, logical document/file references,
assistant turn, structured citations/sources, and workflow reference. Binary
file bytes remain only in the configured storage provider, not in conversation
tables.

Routing criteria are deterministic and intentionally conservative:

| Route | Criteria |
| --- | --- |
| `direct_rag` | Default. Simple factual, explanatory, or summarization QA over selected logical documents or attachments. |
| `langgraph` | Explicit comparison/contrast/gap analysis; contradictions or duplicates; cross-document synthesis; table/report/requirements extraction; CSV/XLSX or structured-data analysis; explicit clarifying-question/scope handling. |

Direct RAG keeps the Phase 4 strict scope rules and never performs unscoped
retrieval. LangGraph receives only the selected logical document IDs, attachment
document IDs, bounded history, and safe context metadata. It validates selected
document lifecycle state before invocation and does not bypass Qdrant/document
scope rules. Core document-processing capabilities are registered for graph
planning/execution during dependency construction.

If message processing fails after the user turn has been persisted, the service
persists an assistant turn with `status = failed` and a safe error message, then
returns the existing API error response. The session relationship is preserved.

---

# Workflow API

## Get Workflow

GET

```
/workflows/{workflow_id}
```

Response

```json
{
  "workflow_id": "00000000-0000-4000-8000-000000000000",
  "session_id": "00000000-0000-4000-8000-000000000001",
  "status": "completed",
  "result": {},
  "error": null,
  "trace_id": "optional-langfuse-trace-reference",
  "created_at": "2026-08-11T12:00:00Z",
  "updated_at": "2026-08-11T12:00:00Z",
  "started_at": "2026-08-11T12:00:00Z",
  "finished_at": "2026-08-11T12:00:05Z"
}
```

---

## List Recent Workflows

GET

```
/workflows
```

Response

```json
{
  "workflows": [
    {
      "workflow_id": "00000000-0000-4000-8000-000000000000",
      "session_id": "00000000-0000-4000-8000-000000000001",
      "status": "completed",
      "display_label": "Summarize quarterly results",
      "trace_id": "optional-langfuse-trace-reference",
      "created_at": "2026-08-11T12:00:00Z",
      "updated_at": "2026-08-11T12:00:00Z",
      "started_at": "2026-08-11T12:00:00Z",
      "finished_at": "2026-08-11T12:00:05Z"
    }
  ]
}
```

---

# Tool API

## List Available Tools

GET

```
/tools
```

Response

```json
[
  {
    "name": "document_reader",
    "category": "document"
  }
]
```

---

## Get Tool Metadata

GET

```
/tools/{tool_name}
```

---

# Report API

## Generate Report

POST

```
/reports
```

Request

```json
{
  "workflow_id": "...",
  "format": "markdown"
}
```

Supported formats

- markdown

Future

- pdf
- docx

---

## Download Report

GET

```
/reports/{report_id}
```

---

# Trace Access

Rastin-AI does not currently expose a first-party `/traces/{trace_id}` API.
When Langfuse is enabled, the application persists the Langfuse trace reference
on `workflow_executions.trace_id` and returns it through the workflow status
APIs. Trace details are viewed in Langfuse.

---

# Evaluation API

## Run Evaluation

POST

```
/evaluation/run
```

Response

```json
{
  "evaluation_id": "...",
  "status": "started"
}
```

---

## Get Evaluation Results

GET

```
/evaluation/{evaluation_id}
```

---

# Health API

## Health Check

GET

```
/health
```

Response

```json
{
  "status": "ok",
  "service": "Rastin-AI",
  "version": "0.1.0",
  "environment": "development"
}
```

`GET /` is also public, but returns only minimal non-sensitive service metadata:

```json
{
  "service": "Rastin-AI",
  "version": "0.1.0"
}
```

---

# Error Codes

| Code | Meaning |
|--------|----------|
| FILE_NOT_FOUND | Uploaded file not found |
| INVALID_FILE | Unsupported format |
| EMPTY_DOCUMENT | No readable content |
| INVALID_REQUEST | Invalid request payload |
| TOOL_FAILURE | Tool execution failed |
| VECTOR_DB_ERROR | Retrieval failed |
| LLM_ERROR | Model request failed |
| INTERNAL_ERROR | Unexpected server error |

---

# HTTP Status Codes

| Status | Usage |
|----------|-------|
| 200 | Success |
| 201 | Resource created |
| 400 | Invalid request |
| 404 | Resource not found |
| 409 | Conflict |
| 422 | Validation failed |
| 500 | Internal error |

---

# API Versioning

The API follows URI versioning.

Example

```
/api/v1/questions
```

Future breaking changes shall introduce a new version.

```
/api/v2/...
```

---

# Pagination

Endpoints returning collections should support:

```
?page=1

&page_size=20
```

Response

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 145
}
```

---

# Idempotency

The following operations are idempotent:

- GET
- DELETE

POST endpoints creating resources are not idempotent unless an Idempotency-Key is provided in future versions.

---

# Rate Limiting

Not implemented in MVP.

Future implementation may include:

- per-user quotas
- API keys
- request throttling

---

# OpenAPI Compatibility

The API is designed to generate a complete OpenAPI 3.1 specification.

Future implementation should automatically expose:

```
/docs
```

Swagger UI

and

```
/openapi.json
```

OpenAPI Schema

---

# API Design Philosophy

The REST API is intentionally thin.

Business logic does not reside in the API layer.

The API is responsible for:

- validation
- serialization
- routing
- authentication dependency enforcement

`GET /`, `/api/v1/health`, and `/api/v1/ready` are unauthenticated. Data-bearing
endpoints require the configured auth boundary. Local/test deployments may use
`AUTH_MODE=disabled` or `AUTH_MODE=dev_jwt`; production-like environments must
use `AUTH_MODE=oidc` with standard JWT issuer, audience, and JWKS validation.

Application logic resides inside the Agent and Tool layers.

This separation keeps the API stable while allowing the internal AI workflow to evolve independently.
