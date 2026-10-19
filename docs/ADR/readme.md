# Architecture Decision Records (ADR)

This directory contains the Architecture Decision Records (ADRs) for Rastin-AI.

Each ADR documents a significant architectural decision made during the design of the system.

The project follows the ADR format proposed by Michael Nygard.

## ADR Structure

Each ADR includes:

- Context
- Decision
- Alternatives Considered
- Consequences
- References

## Purpose

ADRs provide historical context for architectural decisions.

Rather than documenting *what* the system does, ADRs explain *why* specific technologies, patterns, or approaches were selected.

## Current Decisions

### Platform

- FastAPI
- LangGraph
- OpenAI

### Persistence

- PostgreSQL
- Qdrant
- Local Storage
- Storage Abstraction

### Quality

- Langfuse
- DeepEval & Ragas
- GitHub Actions

### Infrastructure

- Docker
- Azure
- REST API

## Status

Unless otherwise specified, all ADRs are considered **Accepted**.