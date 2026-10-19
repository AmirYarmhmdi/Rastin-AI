# Rastin-AI Package

This folder contains the main Python backend package.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `main.py` | Creates the FastAPI application and mounts the API router. | Application settings and router definitions. | Running ASGI app for Uvicorn or Docker. |
| `api/` | Defines HTTP routing, API versioning, endpoints, and dependencies. | HTTP requests, uploaded files, query/path/body parameters. | Validated responses and calls into service-layer use cases. |
| `services/` | Coordinates application use cases such as uploads, questions, messages, documents, and workflows. | API-layer requests, repositories, storage providers, RAG helpers, and agent components. | Business outcomes returned to APIs and persisted through repositories. |
| `schemas/` | Holds Pydantic request and response contracts. | API and service data structures. | Validated, serializable objects shared across boundaries. |
| `database/` | Configures SQLAlchemy engine/session and ORM models. | Database settings and repository operations. | Database sessions and mapped entities for PostgreSQL persistence. |
| `repositories/` | Encapsulates persistence queries. | Database sessions and domain identifiers. | Stored or retrieved workflow/file metadata without leaking SQL details upward. |
| `storage/` | Provides file persistence implementations. | File bytes, object names, storage settings. | Stored files and retrievable file references from local disk or Azure Blob Storage. |
| `rag/` | Implements retrieval-augmented generation support. | Documents, chunks, embeddings, vector-store queries, and source metadata. | Indexed content, retrieved passages, and answer context. |
| `agent/` | Contains planning, tool selection, execution, response, state, and graph components. | User goals, available tools, selected plans, execution state. | Orchestrated workflow steps and generated response state. |
| `tools/` | Defines generic tool contracts and registry behavior. | Tool definitions and execution arguments. | Discoverable deterministic tools for agent workflows. |
| `skills/` | Groups higher-level capabilities and document-processing tools. | Skill/tool inputs such as file paths or document payloads. | Structured extracted content and registered capabilities. |
| `evaluation/` | Loads datasets and runs evaluator adapters. | JSONL evaluation cases, thresholds, evaluator settings. | Validation results and RAG/evaluator reports. |
| `observability/` | Integrates tracing helpers. | Runtime events, spans, metadata, and redaction rules. | Optional Langfuse traces and structured observability data. |
| `core/` | Holds shared settings, logging, and exception definitions. | Environment variables and application-wide errors. | Typed configuration, logging setup, and common exception behavior. |
| `workflows/` | Reserved package for workflow-specific modules. | Future workflow definitions and state machines. | Reusable workflow implementations as the system grows. |

## General Role

The package implements the backend behind Rastin-AI: REST APIs receive user
work, services coordinate the work, persistence and storage keep durable state,
RAG and tools produce grounded context, and agent modules orchestrate multi-step
behavior.

## Typical Request Flow

1. A client calls an endpoint in `api/`.
2. The endpoint validates data with `schemas/` and delegates to `services/`.
3. Services use `storage/`, `repositories/`, `rag/`, `agent/`, or `skills/` as
   needed.
4. Durable state is stored through `database/` and `repositories/`.
5. The API returns a validated response to the caller.
