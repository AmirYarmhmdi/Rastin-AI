# Project Structure

> This document defines the directory structure, architectural boundaries, and development conventions for Rastin-AI.

The project follows a modular architecture inspired by Clean Architecture and Domain-Driven Design (DDD). Each module has a single responsibility and communicates through well-defined interfaces.

---

# Objectives

The project structure aims to:

- Keep responsibilities separated.
- Improve maintainability.
- Support independent testing.
- Simplify onboarding.
- Enable future scalability.

---

# High-Level Repository Structure

```text
Rastin-AI/

├── app/
├── tests/
├── docs/
├── docker/
├── scripts/
├── alembic/
├── storage/
├── .github/
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
└── README.md
```

---

# Application Structure

```text
app/

├── api/
├── core/
├── agents/
├── workflows/
├── tools/
├── services/
├── repositories/
├── models/
├── schemas/
├── database/
├── storage/
├── retrieval/
├── llm/
├── evaluation/
├── observability/
└── main.py
```

---

# Module Responsibilities

## api/

Responsible for exposing REST endpoints.

Contains:

- Routers
- Request validation
- Response serialization
- Dependency injection

Does **not** contain business logic.

---

## core/

Shared application infrastructure.

Contains:

- Configuration
- Settings
- Constants
- Logging
- Exceptions
- Utilities

---

## agents/

Contains LangGraph agent definitions.

Responsible for:

- Planning
- Decision making
- Workflow execution

---

## workflows/

Defines workflow graphs and state machines.

Examples:

- Document Analysis
- Multi-file Comparison
- Report Generation

---

## tools/

Deterministic tools available to the agent.

Examples:

- PDF Reader
- Excel Reader
- CSV Reader
- Retriever
- Report Generator

Each tool should have:

- Input schema
- Output schema
- Unit tests

---

## services/

Application services implementing business use cases.

Examples:

- Upload Service
- Question Service
- Report Service

Services coordinate repositories and tools.

---

## repositories/

Responsible for persistence.

Repositories abstract:

- PostgreSQL
- Qdrant
- Storage providers

Business logic should never access databases directly.

---

## models/

SQLAlchemy ORM models.

Contains database entities only.

---

## schemas/

Pydantic models.

Used for:

- API requests
- API responses
- Tool contracts

---

## database/

Database infrastructure.

Contains:

- Session management
- Alembic configuration
- Database initialization

---

## storage/

Storage providers.

Initial implementation:

- Local Storage

Future implementations:

- Azure Blob
- S3
- MinIO

---

## retrieval/

RAG pipeline.

Contains:

- Chunking
- Embeddings
- Retrieval
- Re-ranking (future)

---

## llm/

LLM abstraction layer.

Responsible for:

- Provider integration
- Prompt execution
- Structured outputs
- Tool calling

Future providers:

- OpenAI
- Azure OpenAI
- Anthropic
- Gemini
- Ollama

---

## evaluation/

Evaluation framework.

Contains:

- DeepEval
- Ragas
- Evaluation datasets
- Benchmarks

---

## observability/

Application observability.

Contains:

- Langfuse integration
- Trace management
- Metrics
- Logging adapters

---

# Tests Structure

```text
tests/

├── unit/
├── integration/
├── evaluation/
├── fixtures/
└── data/
```

---

# Documentation Structure

```text
docs/

Architecture Documents
ADR
Engineering Guidelines
```

---

# Dependency Rule

Dependencies flow inward.

```text
API
↓

Services
↓

Agents

↓

Tools

↓

Repositories

↓

Infrastructure
```

Outer layers may depend on inner layers.

Inner layers must never depend on outer layers.

---

# Naming Conventions

Python files:

snake_case.py

Classes:

PascalCase

Functions:

snake_case

Constants:

UPPER_CASE

Private methods:

_prefix()

---

# Import Rules

Allowed:

```text
API
↓

Services
↓

Repositories
```

Not allowed:

```text
Repositories

↓

API
```

Modules should avoid circular dependencies.

---

# Configuration

All configuration must come from environment variables.

Examples:

- OPENAI_API_KEY
- DATABASE_URL
- QDRANT_URL
- LANGFUSE_SECRET_KEY

No secrets shall be committed to the repository.

---

# Coding Standards

The project follows:

- Ruff
- Black
- Pytest
- Type hints
- Pydantic
- SQLAlchemy 2.x

Every public function should include:

- Type annotations
- Docstrings (where appropriate)
- Unit tests

---

# Development Workflow

1. Create feature branch.
2. Implement functionality.
3. Write tests.
4. Run formatting.
5. Run evaluation.
6. Open Pull Request.
7. Pass CI.
8. Merge.

---

# Design Principles

The project follows:

- Clean Architecture
- SOLID Principles
- Separation of Concerns
- Design First
- Evaluation First
- Observability by Design
- API First

---

# Future Extensions

The structure should support future additions without major refactoring.

Potential future modules include:

- mcp/
- auth/
- workers/
- cache/
- frontend/
- plugins/

The architecture is intentionally modular to enable incremental evolution.