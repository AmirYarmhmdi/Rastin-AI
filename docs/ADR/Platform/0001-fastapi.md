# ADR-0001: Adopt FastAPI as the Backend Framework

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI requires a backend framework responsible for exposing REST APIs, managing user sessions, handling file uploads, orchestrating AI workflows, and serving as the entry point to the platform.

The framework should support:

- High-performance asynchronous request handling
- Automatic OpenAPI documentation
- Strong type validation
- Dependency Injection
- Modern Python features
- Easy integration with LangGraph
- Production deployment using Docker

---

# Decision

Rastin-AI adopts **FastAPI** as the primary backend framework.

FastAPI will be responsible for:

- REST API implementation
- Request validation
- Session management
- File upload endpoints
- Dependency Injection
- API versioning
- OpenAPI schema generation

Business logic will remain outside the API layer.

---

# Alternatives Considered

## Flask

Advantages

- Simple
- Mature ecosystem

Disadvantages

- No native type validation
- OpenAPI requires additional libraries
- Less opinionated architecture
- More boilerplate

Decision

Rejected.

---

## Django

Advantages

- Complete web framework
- ORM included
- Authentication included

Disadvantages

- Too heavyweight for an AI orchestration platform
- Tight coupling between components
- Unnecessary features for MVP

Decision

Rejected.

---

## Litestar

Advantages

- Modern architecture
- High performance

Disadvantages

- Smaller ecosystem
- Lower industry adoption

Decision

Rejected.

---

# Consequences

Positive

- Automatic Swagger UI
- Automatic OpenAPI generation
- Excellent async support
- Strong typing
- Large community
- Native Pydantic integration
- Easy Docker deployment

Negative

- Requires familiarity with asynchronous programming
- Dependency Injection introduces additional concepts
- Breaking changes may occur between major versions

---

# Architecture Impact

FastAPI becomes the Presentation Layer.

The API layer remains intentionally thin.

It delegates application logic to:

- LangGraph
- Tool Layer
- Persistence Layer

---

# Future Considerations

Future versions may include:

- Authentication
- Rate limiting
- WebSocket streaming
- Background workers

These additions should not require replacing FastAPI.

---

# References

- FastAPI Documentation
- OpenAPI 3.1 Specification
- Pydantic Documentation