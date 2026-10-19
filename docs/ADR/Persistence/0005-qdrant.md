# ADR-0005: Adopt Qdrant as the Vector Database

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI implements Retrieval-Augmented Generation (RAG).

The platform requires a vector database capable of:

- High-performance similarity search
- Metadata filtering
- Scalable collections
- Docker deployment
- Cloud deployment
- Python SDK integration

Embeddings should remain independent from relational metadata.

---

# Decision

Rastin-AI adopts **Qdrant** as the primary vector database.

Qdrant stores:

- Embeddings
- Chunk metadata
- Similarity indexes

Application metadata remains in PostgreSQL.

---

# Alternatives Considered

## pgvector

Advantages

- Integrated with PostgreSQL
- Simple architecture
- Fewer services

Disadvantages

- Lower scalability for dedicated vector workloads
- Shared database responsibilities

Decision

Rejected for MVP.

May be revisited for simpler deployments.

---

## Pinecone

Advantages

- Fully managed
- Excellent scalability

Disadvantages

- Vendor lock-in
- External dependency
- Usage costs

Decision

Rejected.

---

## Milvus

Advantages

- High performance
- Production ready

Disadvantages

- Operational complexity
- Larger infrastructure footprint

Decision

Rejected.

---

## Chroma

Advantages

- Easy setup
- Popular in tutorials

Disadvantages

- Less mature
- Limited production adoption

Decision

Rejected.

---

# Consequences

Positive

- Dedicated vector storage
- Metadata filtering
- Docker support
- Excellent retrieval performance
- Easy integration with LangChain and LangGraph

Negative

- Additional infrastructure component
- Synchronization required with PostgreSQL

---

# Architecture Impact

Qdrant stores only semantic information.

It never becomes the source of truth.

Metadata remains in PostgreSQL.

Files remain in local storage.

---

# Future Considerations

Future versions may support:

- Hybrid search
- Multi-vector search
- Sparse vectors
- Image embeddings
- Distributed clusters

---

# References

- Qdrant Documentation
- Vector Search Best Practices
- OpenAI Embeddings Documentation