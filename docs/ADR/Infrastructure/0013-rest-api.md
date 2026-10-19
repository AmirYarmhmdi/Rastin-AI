# ADR-0013: Adopt REST as the Primary External API Style

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI exposes application functionality to external clients.

The API should:

- be simple
- be well documented
- support standard HTTP semantics
- integrate with OpenAPI
- be easy to consume from frontend applications

---

# Decision

Rastin-AI adopts **REST** as the primary external API style.

REST endpoints expose application resources.

The Agent, workflow engine, and tools remain internal implementation details.

---

# Alternatives Considered

## GraphQL

Advantages

- Flexible queries
- Reduced over-fetching

Disadvantages

- Increased complexity
- Limited benefit for current workflows

Decision

Rejected.

---

## gRPC

Advantages

- High performance
- Strong typing

Disadvantages

- Less browser friendly
- More complex tooling

Decision

Rejected.

---

## Direct MCP Interface

Advantages

- AI-native interaction

Disadvantages

- Not yet widely adopted
- Does not replace public REST APIs

Decision

Deferred.

---

# Consequences

Positive

- Standard HTTP semantics
- Broad tooling support
- Automatic OpenAPI documentation
- Easy frontend integration

Negative

- Some operations may require multiple requests
- Less flexible than GraphQL

---

# Architecture Impact

REST acts as the external contract of the platform.

Internal orchestration remains independent from the API implementation.

Future interfaces (WebSocket, MCP, gRPC) should coexist without replacing REST.

---

# API Principles

The API shall:

- be stateless
- expose versioned endpoints
- return structured errors
- use JSON
- follow resource-oriented design

---

# Future Considerations

Future versions may introduce:

- WebSocket streaming
- Server-Sent Events
- MCP endpoints
- gRPC internal services

REST will remain the primary public interface.

---

# References

- REST Architectural Style
- HTTP/1.1 RFC 9110
- OpenAPI Specification