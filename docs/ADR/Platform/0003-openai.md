# ADR-0003: Adopt OpenAI as the Primary LLM Provider

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI requires a Large Language Model capable of orchestrating deterministic analytical workflows.

The selected provider should support:

- Tool Calling
- Structured Outputs
- High reasoning quality
- Strong Python SDK
- Reliable production APIs
- Long-term ecosystem support

The LLM is responsible for reasoning and orchestration rather than deterministic computation.

---

# Decision

Rastin-AI adopts **OpenAI** as the primary LLM provider for the MVP.

OpenAI will be used for:

- Intent understanding
- Workflow planning
- Tool selection
- Response synthesis
- Structured output generation

Deterministic computation remains outside the LLM.

---

# Alternatives Considered

## Anthropic

Advantages

- Strong reasoning
- Excellent tool use
- High-quality responses

Disadvantages

- Smaller ecosystem
- Lower adoption within current project scope

Decision

Deferred.

---

## Google Gemini

Advantages

- Large context windows
- Strong multimodal capabilities

Disadvantages

- Ecosystem still evolving
- Lower maturity for the current architecture

Decision

Deferred.

---

## Self-hosted Models

Examples

- Llama
- Mistral
- Qwen

Advantages

- Full control
- Lower inference cost at scale
- Offline deployment

Disadvantages

- Infrastructure complexity
- GPU requirements
- Model lifecycle management

Decision

Deferred until Phase 2.

---

# Consequences

Positive

- Excellent reasoning quality
- Mature SDK
- Reliable API
- Structured Outputs
- Tool Calling support
- Easy integration with LangGraph

Negative

- External dependency
- API costs
- Internet connectivity required
- Vendor dependency

---

# Architecture Impact

The LLM layer becomes replaceable.

Application logic must never depend on provider-specific features beyond the abstraction layer.

Future providers should be integrated through a common interface.

---

# Future Considerations

Future versions may support:

- Azure OpenAI
- Anthropic
- Gemini
- Ollama
- vLLM
- Local models

The architecture is intentionally provider-agnostic beyond the integration layer.

---

# References

- OpenAI API Documentation
- OpenAI Structured Outputs
- OpenAI Tool Calling Documentation