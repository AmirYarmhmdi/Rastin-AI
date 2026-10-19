# Rastin-AI Documentation

Welcome to the Rastin-AI documentation.

This directory contains the complete technical documentation for the project, covering its architecture, engineering principles, and architectural decisions.

The documentation follows a **Design First** approach, where the system is designed before implementation.

## Directory Structure

```
docs/

├── architecture/
│   System design and technical specifications
│
├── ADR/
│   Architecture Decision Records
│
└── engineering/
    Engineering principles and development practices
```

## Parts, Duties, Inputs, And Outcomes

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `architecture/` | Defines product intent, requirements, system design, API contracts, workflow architecture, and database design. | Product goals, user stories, technical constraints, and implementation discoveries. | Source-of-truth design documents that guide backend, frontend, persistence, RAG, and agent work. |
| `ADR/` | Records important architectural decisions and their tradeoffs. | A decision point, available alternatives, and project context. | Decision history that explains why the system uses specific technologies or patterns. |
| `engineering/` | Documents development principles and quality practices. | Team conventions and desired engineering standards. | Guidance for design-first, observability-first, and evaluation-first implementation. |
| `images/` | Stores documentation images and branding assets. | Image files referenced by Markdown documents. | Rendered visuals in project documentation and README pages. |

## Documentation Philosophy

The documentation is organized into three complementary sections:

### Architecture

Describes **what** the system is and **how** it is designed.

Examples include:

- Vision
- Requirements
- System Architecture
- Agent Architecture
- API Design
- Database Design

---

### ADR (Architecture Decision Records)

Explains **why** architectural decisions were made.

Each ADR documents:

- Context

- Decision
- Alternatives
- Consequences

---

### Engineering

Defines **how** the project is developed.

Examples include:

- Design First
- Observability
- Evaluation Strategy

---

## Guiding Principles

Rastin-AI follows:

- Design First
- API First
- Evaluation First
- Observability by Design
- Clean Architecture
- SOLID Principles
