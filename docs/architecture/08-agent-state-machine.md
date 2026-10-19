# Agent State Machine

> This document defines the execution state machine of the Rastin-AI agent.
>
> The state machine specifies **how the agent transitions between operational states** during analytical workflows.
>
> It is intentionally implementation-independent and serves as the behavioral contract for future LangGraph development.

---

# Traceability

## Inputs

- 02-user-stories.md
- 03-functional-requirements.md
- 07-workflow-architecture.md

## Outputs

- LangGraph implementation
- Tool orchestration logic
- Retry strategy
- Error handling implementation

---

# Design Philosophy

The agent is modeled as a **deterministic workflow coordinator** rather than an autonomous conversational entity.

Its responsibilities are:

- understand analytical intent
- gather evidence
- orchestrate tools
- validate results
- produce grounded answers

The agent never skips states silently.

Every transition should be observable and traceable.

---

# State Overview

```text
                 ┌──────────────┐
                 │     Idle     │
                 └──────┬───────┘
                        │
                        ▼
             ┌────────────────────┐
             │ Receive Request    │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Understand Intent  │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Resolve Context    │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Retrieve Evidence  │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Plan Workflow      │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Execute Tools      │
             └─────────┬──────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Validate Results   │
             └─────────┬──────────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
    ┌───────────────-─┐   ┌────────────────┐
    │ Synthesize      │   │ Retry / Repair │
    └────────┬────────┘   └────────┬───────┘
             │                     │
             ▼                     │
      ┌──────────────┐             │
      │   Complete   │◄────────────┘
      └──────────────┘
```

---

# State Definitions

## State: Idle

### Purpose

Waiting for a new analytical request.

### Entry Conditions

- no active workflow
- previous workflow completed

### Exit Trigger

- user submits a request

---

## State: Receive Request

### Responsibilities

- accept user input
- register request
- attach uploaded sources
- create workflow context

### Outputs

- Request ID
- Session Context

### Failure Conditions

- invalid request
- unsupported file type

---

## State: Understand Intent

### Responsibilities

- classify analytical task
- identify user goal
- determine required capabilities

### Example Intents

- summarize
- compare
- analyze
- calculate
- generate report
- explain

### Outputs

- Intent Object
- Confidence Score

### Transition Rules

- High confidence → Resolve Context
- Low confidence → Ask Clarifying Question (future)

---

## State: Resolve Context

### Responsibilities

- inspect session memory
- identify available documents
- locate relevant datasets
- resolve references such as "this file"

### Outputs

- Context Object
- Source List

### Failure Conditions

- missing required documents
- ambiguous references

---

## State: Retrieve Evidence

### Responsibilities

- perform vector search
- collect relevant document chunks
- filter low-quality matches
- rank evidence

### Outputs

- Evidence Package

### Transition Rules

- Evidence sufficient → Plan Workflow
- Evidence insufficient → Continue with available context

---

## State: Plan Workflow

### Responsibilities

- determine execution strategy
- select required tools
- define execution order
- identify dependencies

### Example Plan

Read PDF

↓

Analyze Excel

↓

Compare findings

↓

Generate report

### Outputs

- Execution Plan

---

## State: Execute Tools

### Responsibilities

- invoke deterministic tools
- pass structured inputs
- collect outputs
- monitor execution

### Tool Categories

- document tools
- spreadsheet tools
- Python execution
- reporting
- visualization

### Failure Conditions

- tool unavailable
- execution error
- invalid input

---

## State: Validate Results

### Responsibilities

- verify tool outputs
- detect inconsistencies
- ensure required evidence exists
- check execution completeness

### Validation Types

- schema validation
- data validation
- evidence validation
- workflow validation

### Transition Rules

- Valid → Synthesize
- Invalid → Retry / Repair

---

## State: Retry / Repair

### Responsibilities

- retry failed tools
- repair malformed outputs
- re-run retrieval if needed
- adjust workflow

### Retry Policy

- maximum retry count configurable
- deterministic tools preferred
- repeated failures reported to user

### Transition Rules

- Recovery successful → Validate Results
- Recovery failed → Synthesize with limitations

---

## State: Synthesize

### Responsibilities

- combine evidence
- generate final answer
- communicate uncertainty
- produce structured output

### Required Properties

- grounded
- explainable
- traceable
- concise

### Outputs

- Final Response
- Evidence References

---

## State: Complete

### Responsibilities

- persist workflow metadata
- finalize trace
- update session state
- release resources

### Exit Transition

- return to Idle

---

# State Transition Table

| Current State | Trigger | Next State |
|---------------|---------|------------|
| Idle | User request | Receive Request |
| Receive Request | Request accepted | Understand Intent |
| Understand Intent | Intent resolved | Resolve Context |
| Resolve Context | Context available | Retrieve Evidence |
| Retrieve Evidence | Evidence collected | Plan Workflow |
| Plan Workflow | Plan created | Execute Tools |
| Execute Tools | Tools finished | Validate Results |
| Validate Results | Validation passed | Synthesize |
| Validate Results | Validation failed | Retry / Repair |
| Retry / Repair | Recovery successful | Validate Results |
| Retry / Repair | Recovery failed | Synthesize |
| Synthesize | Response generated | Complete |
| Complete | Workflow finalized | Idle |

---

# Failure States

## Missing Sources

Occurs when required documents are unavailable.

System behavior:

- stop workflow
- explain missing sources
- request user action

---

## Tool Failure

Occurs when deterministic execution fails.

System behavior:

- retry
- isolate failure
- continue when possible
- report limitations

---

## Retrieval Failure

Occurs when no relevant evidence is found.

System behavior:

- continue with available context
- explicitly communicate low evidence confidence

---

## LLM Failure

Occurs when the language model is unavailable.

System behavior:

- preserve workflow state
- allow future resume
- report temporary failure

---

# Observability Events

Each state transition should emit an event.

Example:

```json
{
  "workflow_id": "wf_001",
  "from_state": "Plan Workflow",
  "to_state": "Execute Tools",
  "timestamp": "...",
  "duration_ms": 124
}
```

These events will later be captured by Langfuse.

---

# LangGraph Mapping

| State | Future LangGraph Node |
|--------|----------------------|
| Receive Request | InputNode |
| Understand Intent | IntentNode |
| Resolve Context | ContextNode |
| Retrieve Evidence | RetrievalNode |
| Plan Workflow | PlannerNode |
| Execute Tools | ToolExecutorNode |
| Validate Results | ValidationNode |
| Retry / Repair | RetryNode |
| Synthesize | ResponseNode |
| Complete | PersistNode |

---

# Future Extensions

The state machine is intentionally designed to support future capabilities without redesigning the core workflow.

Planned extensions:

- Human Approval State
- Parallel Tool Execution
- Multi-Agent Collaboration
- MCP Tool Discovery
- Workflow Persistence
- Pause / Resume Execution
- Scheduled Workflows

These extensions should introduce new states or transitions while preserving the existing execution model.