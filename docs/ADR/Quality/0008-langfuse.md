# ADR-0008: Adopt Langfuse for LLM Observability

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

LLM applications require visibility into execution beyond traditional application logging.

The platform must observe:

- Prompt execution
- Tool calls
- Token usage
- Latency
- Costs
- Workflow traces

Traditional logs are insufficient for debugging AI workflows.

---

# Decision

Rastin-AI adopts **Langfuse** as the primary LLM observability platform.

Langfuse will collect execution traces for every workflow.

---

# Alternatives Considered

## Custom Logging

Advantages

- Full control

Disadvantages

- No AI-specific observability
- Difficult visualization

Decision

Rejected.

---

## Arize Phoenix

Advantages

- Strong evaluation ecosystem
- Rich tracing

Disadvantages

- More suitable after the MVP
- Additional operational complexity

Decision

Deferred.

---

# Consequences

Positive

- End-to-end tracing
- Prompt history
- Token accounting
- Cost monitoring
- Tool execution visibility

Negative

- Additional infrastructure
- External dependency

---

# Architecture Impact

Langfuse becomes the observability layer for AI execution.

Application logs remain separate from AI traces.

---

# Future Considerations

Future versions may integrate OpenTelemetry for unified observability.

---

# References

- Langfuse Documentation
- OpenTelemetry Concepts