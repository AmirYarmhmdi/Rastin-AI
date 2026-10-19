# Personas

> This document defines the primary user personas of **Rastin-AI**.
>
> Personas describe who the users are, what they are trying to accomplish, the types of information they work with, and the capabilities they expect from the platform.
>
> These personas drive user stories, functional requirements, tool design, and agent behavior throughout the project.

---

# Traceability

## Inputs

- 00-project-vision.md

## Outputs

- 02-user-stories.md
- 03-functional-requirements.md
- 07-agent-architecture.md
- 08-tool-specification.md

---

# Persona Design Principles

Personas in Rastin-AI are **role-based**, not individual-based.

They describe categories of knowledge workers with similar goals and workflows rather than fictional users.

Each persona captures:

- business goals
- analytical challenges
- typical information sources
- expected AI assistance
- required platform capabilities

---

# Persona 1 — Project Manager

## Overview

Project Managers coordinate complex projects involving schedules, budgets, technical documentation, and risk management.

They need rapid access to reliable insights across multiple information sources.

---

## Goals

- Monitor project health
- Detect schedule risks
- Compare budget against progress
- Produce executive summaries
- Support decision making

---

## Typical Sources

- Project Charter (PDF)
- Budget (Excel)
- Schedule (Excel)
- Risk Register (CSV)
- Meeting Minutes (PDF)

---

## Typical Questions

- Are we exceeding the allocated budget?
- Which milestones are delayed?
- What are the highest project risks?
- Which deliverables require attention?
- Summarize project status.

---

## Required Agent Capabilities

- Multi-document reasoning
- Spreadsheet analysis
- Cross-source comparison
- Report generation
- Evidence extraction

---

## Typical Workflow

Upload project documents

↓

Ask analytical questions

↓

Review findings

↓

Generate executive report

---

# Persona 2 — Business Analyst

## Overview

Business Analysts transform structured data into business insights.

Their work focuses on discovering trends, validating assumptions, and communicating results.

---

## Goals

- Analyze business metrics
- Identify trends
- Compare datasets
- Build management reports

---

## Typical Sources

- CSV datasets
- Excel reports
- KPI dashboards
- Sales reports
- Operational metrics

---

## Typical Questions

- Which metrics changed significantly?
- What trends are emerging?
- Compare this quarter against the previous one.
- Identify anomalies.

---

## Required Agent Capabilities

- CSV analysis
- Spreadsheet analysis
- Statistical calculations
- Visualization
- Executive summaries

---

## Typical Workflow

Upload datasets

↓

Ask analytical questions

↓

Review charts and insights

↓

Export report

---

# Persona 3 — Engineer

## Overview

Engineers work with technical documentation, specifications, calculations, and structured engineering data.

Accuracy and traceability are more important than conversational responses.

---

## Goals

- Understand technical documentation
- Verify engineering information
- Compare specifications
- Support engineering decisions

---

## Typical Sources

- Technical specifications
- Engineering reports
- Design documents
- Standards
- Calculation sheets

---

## Typical Questions

- Compare these specifications.
- Extract engineering requirements.
- Summarize the design document.
- Identify inconsistencies.

---

## Required Agent Capabilities

- Technical document understanding
- Cross-document comparison
- Deterministic calculations
- Evidence extraction
- Structured reporting

---

## Typical Workflow

Upload engineering documents

↓

Ask technical questions

↓

Review evidence

↓

Export technical report

---

# Persona 4 — Researcher

## Overview

Researchers work with scientific literature and large collections of documents.

Their primary challenge is synthesizing knowledge across multiple sources.

---

## Goals

- Review literature
- Compare publications
- Extract evidence
- Build summaries

---

## Typical Sources

- Research papers
- PDFs
- Technical reports
- White papers

---

## Typical Questions

- Compare these papers.
- What are the main contributions?
- Which findings are consistent?
- Summarize the current state of the art.

---

## Required Agent Capabilities

- Multi-document RAG
- Citation extraction
- Cross-paper comparison
- Summarization
- Evidence tracking

---

## Typical Workflow

Upload papers

↓

Ask research questions

↓

Review synthesized findings

↓

Generate literature review

---

# Persona 5 — Consultant

## Overview

Consultants analyze client information to identify issues, evaluate alternatives, and produce actionable recommendations.

---

## Goals

- Understand client context
- Compare documents
- Identify risks
- Produce recommendations

---

## Typical Sources

- Client reports
- Contracts
- Business documents
- Financial reports
- Meeting notes

---

## Typical Questions

- What risks exist?
- Compare contract versions.
- Summarize client documentation.
- What recommendations can be made?

---

## Required Agent Capabilities

- Multi-document reasoning
- Cross-document comparison
- Report generation
- Evidence extraction
- Recommendation support

---

## Typical Workflow

Upload client documents

↓

Ask analytical questions

↓

Review evidence

↓

Generate recommendation report

---

# Cross-Persona Capabilities

Regardless of the persona, Rastin-AI should consistently provide:

- Reliable document understanding
- Multi-document reasoning
- Structured data analysis
- Deterministic tool execution
- Transparent evidence retrieval
- Explainable decision support
- Report generation
- Execution trace visibility

---

# Design Implications

These personas directly influence the design of:

- User Stories
- Functional Requirements
- Agent Architecture
- Tool Specifications
- RAG Pipeline
- Evaluation Strategy

Every major capability implemented in Rastin-AI should support at least one documented persona.

Capabilities that do not address a real user need should not be included in the MVP.