# ADR-0007: Introduce a Storage Abstraction Layer

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI stores uploaded files before they are processed.

The MVP uses the local filesystem, but future deployments may require cloud object storage.

The application should avoid coupling business logic to a specific storage provider.

Supported storage backends may evolve over time.

---

# Decision

Rastin-AI introduces a Storage Abstraction Layer.

All file operations shall be performed through a common Storage Provider interface.

Application components must never interact directly with the filesystem.

---

# Storage Interface

```python
class StorageProvider(ABC):

    def upload(...):
        ...

    def download(...):
        ...

    def delete(...):
        ...

    def exists(...):
        ...

    def generate_uri(...):
        ...
```

---

# Initial Implementation

```
LocalStorageProvider
```

Future implementations:

- AzureBlobStorageProvider
- S3StorageProvider
- MinIOStorageProvider
- GoogleCloudStorageProvider

---

# Alternatives Considered

## Direct Filesystem Access

Advantages

- Very simple

Disadvantages

- Tight coupling
- Difficult cloud migration
- Harder testing

Decision

Rejected.

---

## Cloud SDK Everywhere

Advantages

- Direct provider access

Disadvantages

- Vendor lock-in
- Difficult provider replacement

Decision

Rejected.

---

# Consequences

Positive

- Storage provider independence
- Easier testing
- Cleaner architecture
- Future cloud migration without business logic changes

Negative

- One additional abstraction layer
- Slight implementation overhead

---

# Architecture Impact

The Storage Layer becomes the single entry point for file operations.

Business logic interacts only with StorageProvider.

The selected implementation is resolved through dependency injection.

---

# Future Considerations

Future versions may support:

- Object versioning
- Signed URLs
- CDN integration
- Multi-region storage
- Lifecycle policies

These features should be implemented inside Storage Providers without impacting application services.

---

# References

- SOLID Principles
- Dependency Inversion Principle
- Strategy Pattern
- Twelve-Factor App