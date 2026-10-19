# ADR-0004: Adopt PostgreSQL as the Primary Relational Database

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI requires persistent storage for structured application data.

The platform needs to store:

- Sessions
- Uploaded file metadata
- Workflow metadata
- Tool execution history
- Reports
- Future user accounts

The database should provide:

- ACID transactions
- Strong consistency
- Mature ecosystem
- Excellent Python support
- Docker compatibility
- Cloud deployment support

---

# Decision

Rastin-AI adopts **PostgreSQL** as the primary relational database.

PostgreSQL stores application metadata only.

Large files are stored separately.

Embeddings are stored in Qdrant.

Execution traces are stored in Langfuse.

---

# Alternatives Considered

## SQLite

Advantages

- Zero configuration
- Lightweight
- Excellent for prototyping

Disadvantages

- Limited concurrency
- Poor production scalability
- Not suitable for cloud deployments

Decision

Rejected.

---

## MySQL

Advantages

- Mature ecosystem
- High performance

Disadvantages

- Fewer advanced features for analytical workloads
- Less flexible JSON support

Decision

Rejected.

---

## MongoDB

Advantages

- Flexible schema
- Easy document storage

Disadvantages

- Weak relational modeling
- Not ideal for strongly connected entities

Decision

Rejected.

---

# Consequences

Positive

- Mature ecosystem
- Reliable transactions
- Excellent SQLAlchemy integration
- Cloud-native support
- Rich indexing capabilities

Negative

- Schema migrations required
- More operational complexity than SQLite

---

# Architecture Impact

PostgreSQL stores only structured metadata.

It is not responsible for:

- embeddings
- uploaded documents
- LLM traces

Those responsibilities belong to specialized storage systems.

---

# Future Considerations

Future versions may introduce:

- Read replicas
- Database partitioning
- Full-text search
- Row-level security

No redesign should be required.

---

# References

- PostgreSQL Documentation
- SQLAlchemy Documentation
- Alembic Documentation