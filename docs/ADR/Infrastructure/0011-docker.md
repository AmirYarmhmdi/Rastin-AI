# ADR-0011: Adopt Docker as the Standard Deployment Environment

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI consists of multiple services:

- FastAPI
- PostgreSQL
- Qdrant
- Langfuse
- Future background workers

Developers should be able to start the entire platform with minimal setup.

The deployment environment should remain consistent across:

- local development
- CI
- production

---

# Decision

Rastin-AI adopts **Docker** as the standard runtime environment.

Every service shall execute inside an isolated container.

Application dependencies shall be bundled into immutable container images.

---

# Alternatives Considered

## Native Installation

Advantages

- Simple for small projects

Disadvantages

- Dependency conflicts
- Platform differences
- Difficult onboarding

Decision

Rejected.

---

## Python Virtual Environments Only

Advantages

- Lightweight

Disadvantages

- Infrastructure services still require manual installation

Decision

Rejected.

---

# Consequences

Positive

- Reproducible environments
- Platform independence
- Easy onboarding
- Cloud portability
- Consistent CI

Negative

- Additional Docker knowledge required
- Slight resource overhead

---

# Architecture Impact

Each major component shall run inside its own container.

Examples include:

- API
- PostgreSQL
- Qdrant
- Langfuse

Future workers should also execute independently.

---

# Future Considerations

Future versions may include:

- Multi-stage builds
- Image optimization
- Security scanning
- Distroless images

---

# References

- Docker Documentation
- OCI Image Specification