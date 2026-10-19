# System Context

> This document defines the external environment of Rastin-AI.
>
> It identifies the primary users, external systems, and services that interact with the platform while intentionally avoiding internal implementation details.
>
> This document corresponds to **C4 Model – Level 1 (System Context)**.

---

# Traceability

## Inputs

- 00-project-vision.md
- 03-functional-requirements.md
- 04-non-functional-requirements.md

## Outputs

- 06-high-level-architecture.md
- 07-agent-architecture.md
- 08-tool-specification.md

---

# Purpose

Rastin-AI enables knowledge workers to analyze heterogeneous information sources using AI-assisted analytical workflows.

The platform acts as an orchestration layer between users, Large Language Models, deterministic tools, vector retrieval, and structured storage.

The system is designed to augment human decision-making rather than automate decisions.

---

# Primary Actors

## Knowledge Worker

Represents users such as:

- Project Managers
- Engineers
- Researchers
- Business Analysts
- Consultants

Responsibilities:

- Upload documents
- Ask analytical questions
- Review evidence
- Validate results

---

## AI Platform Administrator

Responsible for:

- Deployment
- Configuration
- Monitoring
- API keys
- Infrastructure maintenance

This role is outside the MVP user interface but important for production deployment.

---

# External Systems

## OpenAI API

Purpose

Provides language model capabilities including:

- reasoning
- planning
- structured output
- tool calling

Interaction

Rastin-AI sends structured prompts and receives model responses.

---

## Qdrant

Purpose

Stores vector embeddings used during retrieval.

Interaction

Receives embeddings.

Returns relevant document chunks.

---

## PostgreSQL

Purpose

Stores:

- users
- sessions
- uploaded sources
- metadata
- execution history

---

## Local File Storage

Purpose

Stores uploaded files before processing.

Future implementations may replace local storage with cloud object storage.

---

## Langfuse

Purpose

Observability.

Captures:

- prompts
- tool execution
- traces
- latency
- cost
- token usage

---

## GitHub Actions

Purpose

Continuous Integration.

Responsible for:

- testing
- linting
- formatting
- evaluation

---

## Azure

Purpose

Deployment environment.

May host:

- FastAPI
- PostgreSQL
- Containers

Future versions may support Kubernetes deployment.

---

# System Boundary

Rastin-AI is responsible for:

- document ingestion
- structured data ingestion
- workflow orchestration
- retrieval
- tool execution
- report generation
- execution trace

Rastin-AI is NOT responsible for:

- training language models
- fine-tuning foundation models
- document authoring
- enterprise authentication (MVP)

---

# External Data Flow

Typical interaction:

Knowledge Worker

↓

Upload PDF / Excel / CSV

↓

Rastin-AI

↓

OpenAI

↓

Qdrant

↓

PostgreSQL

↓

Deterministic Tools

↓

Grounded Response

↓

Knowledge Worker

---

# Design Principles

The system follows several architectural principles:

- Human-in-the-loop
- Tool-first reasoning
- Explainability
- Modularity
- Deterministic execution
- Retrieval before generation
- Traceable workflows

---

# Future Extensions

The context is intentionally designed to support future additions including:

- MCP servers
- Azure OpenAI
- Anthropic
- Google Gemini
- Self-hosted LLMs
- External enterprise APIs
- Cloud object storage

These additions should require minimal architectural changes.