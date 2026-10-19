# ADR-0010: Adopt GitHub Actions for Continuous Integration

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI requires automated validation for every code change.

Continuous Integration should verify:

- Formatting
- Linting
- Unit tests
- Integration tests
- AI evaluation
- Docker builds

The CI platform should integrate naturally with GitHub.

---

# Decision

Rastin-AI adopts **GitHub Actions** as the Continuous Integration platform.

Every Pull Request shall trigger automated validation.

---

# Alternatives Considered

## Azure DevOps

Advantages

- Enterprise ecosystem
- Strong Azure integration

Disadvantages

- Higher operational complexity
- Not required for MVP

Decision

Deferred.

---

## GitLab CI

Advantages

- Powerful pipelines

Disadvantages

- Repository hosted on GitHub

Decision

Rejected.

---

# Consequences

Positive

- Native GitHub integration
- Simple workflows
- Marketplace ecosystem
- Automated quality gates

Negative

- GitHub dependency

---

# Architecture Impact

CI becomes part of the engineering workflow.

No code should be merged without passing automated validation.

---

# Planned Pipeline

Every commit should execute:

1. Ruff
2. Black
3. Pytest
4. Integration Tests
5. DeepEval
6. Docker Build

Future additions:

- Security scanning
- Dependency scanning
- Performance benchmarks

---

# References

- GitHub Actions Documentation
- CI/CD Best Practices