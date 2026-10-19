# ADR-0006: Adopt Local File Storage for MVP

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI allows users to upload source documents including:

- PDF
- Excel
- CSV

The application requires a storage mechanism for original files before processing.

The MVP prioritizes simplicity, reproducibility, and local development.

---

# Decision

Rastin-AI stores uploaded files on the local filesystem during the MVP.

Only file metadata is stored in PostgreSQL.

Embeddings are stored in Qdrant.

Original files remain on disk.

---

# Alternatives Considered

## Azure Blob Storage

Advantages

- Cloud-native
- Highly scalable
- Managed infrastructure

Disadvantages

- Additional cloud dependency
- Increased deployment complexity

Decision

Deferred.

---

## Amazon S3

Advantages

- Industry standard
- Reliable
- Scalable

Disadvantages

- External infrastructure
- Vendor dependency

Decision

Deferred.

---

## Database BLOB Storage

Advantages

- Single storage system

Disadvantages

- Database growth
- Slower backups
- Reduced performance

Decision

Rejected.

---

# Consequences

Positive

- Simple architecture
- Easy local development
- Easy Docker integration
- Minimal infrastructure

Negative

- Not horizontally scalable
- Requires shared storage in clustered deployments

---

# Architecture Impact

Files become immutable resources.

The database stores only:

- logical document identifiers and lifecycle status
- linked file metadata
- storage key/backend references
- file size and checksum

Business logic never accesses files directly.

All file access occurs through dedicated services.

---

# Storage Layout

Example:

```
storage/

    session-001/

        report.pdf

        sales.xlsx

        budget.csv
```

Future implementations may replace the storage backend without changing the application layer.

---

# Future Considerations

Potential future storage providers:

- Azure Blob Storage
- Amazon S3
- Google Cloud Storage
- MinIO

The Storage Service abstraction should make these transitions transparent.

---

# References

- Azure Blob Storage Documentation
- Amazon S3 Documentation
- Twelve-Factor App Principles
