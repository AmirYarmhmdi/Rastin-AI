# ADR-0012: Adopt Microsoft Azure as the Primary Cloud Platform

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

Rastin-AI should demonstrate production-ready cloud deployment.

The platform requires infrastructure capable of hosting:

- API
- Database
- Vector database
- Monitoring
- Containers

The cloud provider should support future scaling without requiring architectural redesign.

---

# Decision

Rastin-AI adopts **Microsoft Azure** as the primary cloud platform.

Azure is selected because of:

- strong enterprise adoption
- managed services
- container support
- AI ecosystem
- future Azure OpenAI compatibility

---

# Alternatives Considered

## AWS

Advantages

- Largest cloud ecosystem
- Mature services

Disadvantages

- Not selected for this project

Decision

Rejected.

---

## Google Cloud Platform

Advantages

- Strong AI services

Disadvantages

- Smaller adoption within target market

Decision

Rejected.

---

## Self-hosted Infrastructure

Advantages

- Full control

Disadvantages

- Increased operational overhead

Decision

Rejected.

---

# Consequences

Positive

- Enterprise-ready deployment
- Cloud-native architecture
- Managed infrastructure
- Future Azure OpenAI integration

Negative

- Azure-specific knowledge required
- Potential vendor dependency

---

# Architecture Impact

The architecture shall remain cloud-agnostic whenever possible.

Azure-specific implementation details should remain isolated to the infrastructure layer.

Business logic shall remain independent of the cloud provider.

---

# Future Considerations

Future deployment may use:

- Azure App Service
- Azure Container Apps
- Azure Kubernetes Service (AKS)
- Azure Blob Storage
- Azure Database for PostgreSQL

---

# References

- Microsoft Azure Documentation
- Azure Architecture Center