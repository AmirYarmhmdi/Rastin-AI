# ADR-0009: Adopt DeepEval and Ragas for AI Evaluation

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Traditional software tests verify deterministic behavior.

LLM systems also require evaluation of response quality and retrieval effectiveness.

Evaluation should become part of the engineering lifecycle.

---

# Decision

Rastin-AI adopts two complementary evaluation frameworks.

DeepEval evaluates:

- Answer quality
- Faithfulness
- Correctness
- Hallucination
- Tool behavior

Ragas evaluates:

- Retrieval quality
- Context precision
- Context recall
- Answer relevance
- Faithfulness

---

# Alternatives Considered

## Manual Evaluation

Advantages

- Flexible

Disadvantages

- Not reproducible
- Time consuming

Decision

Rejected.

---

## Promptfoo

Advantages

- Excellent regression testing
- Prompt comparison

Disadvantages

- Better suited as a complementary tool

Decision

Deferred to Phase 2.

---

# Consequences

Positive

- Automated evaluation
- Repeatable benchmarks
- CI integration
- Objective quality metrics

Negative

- Benchmark maintenance
- Evaluation cost

---

# Architecture Impact

Evaluation becomes a first-class component of the platform rather than a post-development activity.

---

# Future Considerations

Future versions may include Promptfoo and Phoenix evaluations.

---

# References

- DeepEval Documentation
- Ragas Documentation