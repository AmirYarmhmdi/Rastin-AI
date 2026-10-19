# Database Design

> This document defines the persistence architecture of Rastin-AI.
>
> Rather than relying on a single database, Rastin-AI uses multiple specialized storage systems.
>
> Each storage technology is responsible for a specific type of data.

---

# Traceability

## Inputs

- 03-functional-requirements.md
- 06-high-level-architecture.md
- 10-api-specification.md

## Outputs

- PostgreSQL Schema
- Qdrant Collections
- ORM Models
- Database Migrations

---

# Persistence Philosophy

Rastin-AI separates data according to its characteristics.

| Storage | Responsibility |
|----------|----------------|
| PostgreSQL | Structured relational data |
| Qdrant | Vector embeddings |
| Local Storage | Uploaded files |
| Langfuse | Traces and observability |

This separation improves scalability, maintainability, and performance.

---

# Persistence Overview

```text
                    Rastin-AI

                          │

        ┌─────────────────┼──────────────────┐

        │                 │                  │

 PostgreSQL          Qdrant            Local Storage

        │                 │                  │

 Metadata          Embeddings          Uploaded Files

        │

   Langfuse

Execution Traces
```

---

# PostgreSQL Schema

The relational database stores application metadata.

Main entities:

- User
- Session
- ConversationMessage
- ConversationMessageDocument
- Document
- FileMetadata
- WorkflowExecution

`ToolExecution` and `Report` are design targets, not tables in the current
schema.

---

# Entity: User

Purpose

Represents the local application user mapped from a trusted external identity.
Phase A stores user ownership, not organizations, roles, sharing, or tenant
membership.

Fields

| Field | Type |
|---------|------|
| id | UUID |
| issuer | String, nullable |
| external_subject | String, nullable |
| email | String, nullable |
| display_name | String, nullable |
| is_active | Boolean |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

One User

↓

Many Sessions, Documents, FileMetadata rows, and WorkflowExecutions

`issuer` plus `external_subject` is unique for authenticated users. Local
development with `AUTH_MODE=disabled` maps requests to one configured local
development identity.

---

# Entity: Session

Purpose

Represents a reusable conversation session. In the current implementation,
`POST /api/v1/messages` creates a session when `session_id` is omitted and
reuses an existing session when `session_id` is supplied.

Fields

| Field | Type |
|---------|------|
| id | UUID |
| user_id | UUID, nullable FK users.id |
| title | String, nullable |
| created_at | Timestamp |
| updated_at | Timestamp |
| status | active, archived |

Relationships

One Session

↓

Many ConversationMessages

One Session

↓

Many Documents

↓

Many WorkflowExecutions

Messages are ordered by the deterministic `(session_id, sequence)` pair. The
session `updated_at` timestamp is touched whenever a message is appended so the
read-only session list can show recent activity.

---

# Entity: ConversationMessage

Purpose

Stores one durable user or assistant turn. Conversation text is distinct from
workflow internals; workflow state stays in `workflow_executions`.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| session_id | UUID |
| workflow_id | UUID, nullable |
| role | user, assistant |
| sequence | Integer |
| content | Text |
| status | submitted, answered, failed |
| error_message | String, nullable |
| citations | JSONB |
| sources | JSONB |
| message_metadata | JSONB |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

Many ConversationMessages

↓

One Session

Zero or More ConversationMessages

↓

One WorkflowExecution

One ConversationMessage

↓

Many ConversationMessageDocuments

Assistant citations and sources are stored as safe structured JSON references,
not as raw retrieved chunk text.

---

# Entity: ConversationMessageDocument

Purpose

Relates a user message to logical documents and optional file metadata. This is
used for both newly attached files and already persisted documents referenced by
`document_ids`.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| message_id | UUID |
| document_id | UUID |
| file_metadata_id | UUID, nullable |
| reference_type | attachment, referenced |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

Many ConversationMessageDocuments

↓

One ConversationMessage

Many ConversationMessageDocuments

↓

One Document

Many ConversationMessageDocuments

↓

Zero or One FileMetadata

Conversation tables never store binary file content, local paths, or Azure Blob
payloads.

---

# Entity: Document

Purpose

Represents the logical document resource used by Rastin-AI workflows.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| session_id | UUID |
| user_id | UUID, nullable FK users.id |
| name | String |
| status | uploaded, processing, indexed, failed |
| indexing_error_code | String, nullable |
| indexing_error_message | String, nullable |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

Many Documents

↓

One Session

One Document

↓

Zero or One FileMetadata

New uploads start with `status = uploaded`. The synchronous ingestion phase then
moves readable supported documents through `processing` to `indexed`. Extraction
or indexing errors move to `failed` with safe failure details. Original file
metadata remains linked to failed documents; source-location metadata for
indexed content is stored in Qdrant chunk payloads rather than PostgreSQL.

---

# Entity: FileMetadata

Purpose

Represents the physical source file backing a logical document. PostgreSQL stores
metadata and storage references only; it does not store uploaded file bytes.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| document_id | UUID, nullable unique |
| user_id | UUID, nullable FK users.id |
| original_filename | String |
| storage_key | String |
| storage_backend | String |
| content_type | String, nullable |
| normalized_extension | String |
| size_bytes | BigInteger |
| status | stored, failed |
| checksum_sha256 | String, nullable |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

Zero or One FileMetadata

↓

One Document

---

# Entity: WorkflowExecution

Purpose

Represents a persisted workflow run. A workflow may create a session when it is
invoked independently, or it may link to an existing reusable conversation
session when started from `POST /api/v1/messages`.

For message submissions, the selected orchestration route is persisted in
`input_payload.route` as either `direct_rag` or `langgraph`. This avoids a new
column while keeping route choice auditable through the existing workflow model.
LangGraph workflow outputs persist safe response status, citations/sources when
available, matched routing rules, and workflow details.

When optional Langfuse observability is enabled, `trace_id` stores the Langfuse
trace reference for workflows that create `workflow_executions` rows. The
application does not store trace events, prompts, extracted document text, file
bytes, storage keys, local paths, or credentials in PostgreSQL for
observability. Runtime spans send bounded operational metadata to Langfuse:
workflow/session/message IDs, logical document IDs, route choices, counts,
statuses, model/provider names, and provider usage details.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| session_id | UUID |
| user_id | UUID, nullable FK users.id |
| workflow_name | String |
| workflow_version | String, nullable |
| status | pending, running, completed, failed |
| input_payload | JSONB, nullable |
| output_payload | JSONB, nullable |
| error_message | Text, nullable |
| trace_id | String, nullable |
| started_at | Timestamp |
| finished_at | Timestamp |
| created_at | Timestamp |
| updated_at | Timestamp |

Relationships

Many WorkflowExecutions

↓

One Session

One WorkflowExecution

↓

Zero or More ConversationMessages

---

# Entity: ToolExecution

Purpose

Stores every deterministic tool execution.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| workflow_id | UUID |
| tool_name | String |
| execution_time_ms | Integer |
| status | Enum |
| trace_id | UUID |

---

# Entity: Report

Purpose

Generated reports.

Fields

| Field | Type |
|--------|------|
| id | UUID |
| workflow_id | UUID |
| format | Enum |
| location | String |
| generated_at | Timestamp |

---

# Entity Relationship Diagram

```text
Session

│

├── ConversationMessages ── ConversationMessageDocuments ── Documents ── FileMetadata

├── Documents ── FileMetadata

└── WorkflowExecutions
```

---

# PostgreSQL Indexing

Recommended indexes:

Session

- created_at

File

- session_id
- file_type

Workflow

- session_id
- status

ConversationMessage

- session_id
- workflow_id
- unique `(session_id, sequence)`

ConversationMessageDocument

- message_id
- document_id
- file_metadata_id

ToolExecution

- workflow_id
- tool_name

---

# Qdrant Design

Purpose

Store semantic embeddings.

Collection

documents

Payload

```json
{
  "document_id": "logical-document-uuid",
  "user_id": "local-user-uuid",
  "filename": "example.pdf",
  "chunk_id": "chunk_abc123",
  "chunk_index": 14,
  "location_type": "page",
  "source_location": "page:2",
  "page_number": 2,
  "file_type": "pdf"
}
```

Retrieval and delete operations that scope by `document_id` also include
`user_id`. PostgreSQL ownership validation is authoritative; Qdrant metadata
filters are a second isolation control, not a replacement for SQL checks.

Vector

```
1536 dimensions
```

(OpenAI embedding model)

---

# Chunk Strategy

Initial Strategy

- Recursive Character Splitter

Chunk Size

```
1000 characters
```

Overlap

```
200 characters
```

Future strategies may include:

- Semantic chunking
- Markdown chunking
- Table-aware chunking

---

# Local File Storage

Purpose

Store uploaded source files.

Example

```
storage/

    session_id/

        document.pdf

        budget.xlsx

        sales.csv
```

The database stores only metadata.

---

# Langfuse Storage

Langfuse stores:

- prompt traces
- workflow traces
- token usage
- latency
- LLM costs

The application stores only the Langfuse Trace ID.

---

# Data Lifecycle

Upload

↓

Metadata

↓

Store File

↓

Extract Text

↓

Generate Embeddings

↓

Store Vector

↓

Answer Questions

↓

Generate Report

↓

Persist Workflow

---

# Soft Delete Strategy

Files should not be physically removed immediately.

Recommended fields:

```
deleted_at

is_deleted
```

This simplifies recovery and auditing.

---

# Migration Strategy

Schema evolution shall use:

Alembic

Migration principles:

- forward-only migrations
- reproducible environments
- version-controlled schema

---

# ORM Strategy

ORM

SQLAlchemy 2.x

Model style

Declarative

Primary Key

UUID

Relationships

Lazy loading where appropriate.

---

# Future Database Extensions

Future versions may introduce:

- User entity
- Team entity
- Shared workspaces
- Conversation history
- Evaluation datasets
- Tool registry
- MCP registry

These additions should require minimal schema changes.

---

# Database Design Principles

The persistence layer follows these principles:

- Separation of Concerns
- Single Source of Truth
- Immutable execution history
- Metadata over file duplication
- Retrieval optimized for semantic search
- Production-ready schema evolution
