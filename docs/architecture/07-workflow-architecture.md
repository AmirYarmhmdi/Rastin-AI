# Workflow Architecture

> This document defines how the Rastin-AI agent reasons, plans, and executes analytical workflows.
>
> It specifies the internal workflow logic independently of implementation details.
>
> Future LangGraph implementations should follow this architecture.

---

# Traceability

## Inputs

- 02-user-stories.md
- 03-functional-requirements.md
- 06-high-level-architecture.md
- 06.5-sequence-diagrams.md

## Outputs

- 08-tool-specification.md

---

# Workflow Philosophy

Rastin-AI does not answer questions directly.

Instead, it executes analytical workflows composed of deterministic steps coordinated by an LLM.

The LLM decides.

Tools execute.

Evidence supports every answer.

---

# Generic Workflow

```text
Receive Request
        ↓
Understand Intent
        ↓
Inspect Session
        ↓
Locate Sources
        ↓
Retrieve Evidence
        ↓
Plan Workflow
        ↓
Select Tools
        ↓
Execute Tools
        ↓
Validate Outputs
        ↓
Synthesize Response
        ↓
Generate Evidence
        ↓
Return Answer
```

---

# Workflow Stages

## Stage 1 — Request Reception

Input:

- user message
- uploaded files
- session context

Output:

Request object

---

## Stage 2 — Intent Analysis

Responsibilities

- classify intent
- identify requested task
- detect required sources

Output

Intent object

---

## Stage 3 — Context Resolution

Responsibilities

- inspect uploaded documents
- inspect session memory
- determine relevant sources

Output

Context object

---

## Stage 4 — Evidence Retrieval

Responsibilities

- query vector database
- collect relevant chunks
- filter low-quality matches

Output

Evidence package

---

## Stage 5 — Workflow Planning

Responsibilities

- determine execution order
- identify required tools
- estimate dependencies

Output

Execution plan

---

## Stage 6 — Tool Selection

Responsibilities

- choose deterministic tools
- validate inputs
- prepare execution

Examples

- PDF Reader
- Spreadsheet Analyzer
- Python Executor
- Report Generator

---

## Stage 7 — Tool Execution

Responsibilities

- execute tools
- collect outputs
- handle failures
- retry when appropriate

---

## Stage 8 — Validation

Responsibilities

- validate tool outputs
- detect inconsistencies
- verify required evidence exists

---

## Stage 9 — Response Synthesis

Responsibilities

- summarize findings
- generate structured response
- include evidence references
- communicate uncertainty

---

# Workflow Categories

## Retrieval Workflow

PDF

↓

Embedding

↓

Qdrant

↓

Retriever

↓

LLM

---

## Spreadsheet Workflow

Excel

↓

Parser

↓

Spreadsheet Tool

↓

Python

↓

Report

---

## Cross-Document Workflow

Multiple Sources

↓

Retriever

↓

Comparison Tool

↓

Evidence

↓

Report

---

## Research Workflow

Papers

↓

Retriever

↓

Citation Extraction

↓

Comparison

↓

Summary

---

# Error Handling

Every workflow should support:

- validation failures
- missing files
- unavailable tools
- LLM errors
- retrieval failures

The workflow should degrade gracefully whenever possible.

---

# Workflow Principles

Every workflow shall satisfy:

- Explainability
- Traceability
- Deterministic execution
- Modularity
- Observability
- Human-in-the-loop

---

# Future LangGraph Mapping

| Workflow Stage | Future LangGraph Node |
|----------------|----------------------|
| Request Reception | InputNode |
| Intent Analysis | IntentNode |
| Context Resolution | ContextNode |
| Evidence Retrieval | RetrievalNode |
| Workflow Planning | PlannerNode |
| Tool Selection | ToolRouterNode |
| Tool Execution | ToolExecutorNode |
| Validation | ValidationNode |
| Response Synthesis | ResponseNode |

---

# Future Extensions

The workflow architecture is intentionally designed to support:

- parallel tool execution
- multi-agent collaboration
- MCP tool discovery
- human approval nodes
- asynchronous execution
- workflow persistence
- resumable workflows

These extensions should require new workflow nodes without redesigning the overall architecture.