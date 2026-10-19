# ADR-0002: Adopt LangGraph as the Agent Orchestration Framework

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI is not a traditional chatbot.

The platform coordinates multiple deterministic tools to execute analytical workflows.

The orchestration framework should support:

- Stateful execution
- Workflow branching
- Retry mechanisms
- Human-in-the-loop
- Tool calling
- Future multi-agent collaboration

---

# Decision

Rastin-AI adopts **LangGraph** as the workflow orchestration framework.

LangGraph is responsible for:

- Workflow execution
- State management
- Tool routing
- Execution control
- Retry logic
- Future checkpointing

The LLM is not responsible for workflow execution.

LangGraph coordinates execution.

---

# Alternatives Considered

## LangChain AgentExecutor

Advantages

- Easy to start
- Mature ecosystem

Disadvantages

- Limited workflow control
- Difficult to visualize execution
- Less suitable for complex state machines

Decision

Rejected.

---

## CrewAI

Advantages

- Simple multi-agent development

Disadvantages

- Focused on autonomous agents
- Less explicit workflow control
- Reduced determinism

Decision

Rejected.

---

## AutoGen

Advantages

- Powerful conversational agents

Disadvantages

- Conversation-oriented
- Higher complexity
- Less deterministic execution

Decision

Rejected.

---

## Custom Orchestrator

Advantages

- Full flexibility

Disadvantages

- Significant maintenance cost
- Reinvents existing capabilities
- Higher implementation complexity

Decision

Rejected.

---

# Consequences

Positive

- Explicit workflow graph
- Native state management
- Easy debugging
- Better observability
- Human approval nodes
- Future scalability

Negative

- Additional learning curve
- Rapid ecosystem evolution
- API changes across releases

---

# Architecture Impact

LangGraph becomes the orchestration layer between:

- API
- Tools
- Retrieval
- LLM

Business logic remains independent from the workflow engine.

---

# Future Considerations

Future versions may introduce:

- Multi-agent workflows
- Persistent checkpoints
- Distributed execution
- MCP integration

No architectural redesign should be required.

---

# References

- LangGraph Documentation
- State Machine Design Patterns
- Workflow Orchestration Principles