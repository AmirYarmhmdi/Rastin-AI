# User Stories

> This document translates the project vision into user-centered stories.
> The goal is to derive required system capabilities from real knowledge-worker needs, not from a predefined tool list.

---

# Design Question

The core design question for this document is:

> What do knowledge workers need to accomplish when their work spans documents, spreadsheets, data, calculations, and reports?

For Rastin-AI, a knowledge worker is a professional who makes decisions or produces analytical outputs by combining information from multiple sources.

They do not only want a chatbot answer. They need a workspace that can:

- read source material
- analyze structured data
- compare information across files
- perform calculations
- explain how results were produced
- generate useful analytical outputs

---

# Story Design Principles

User stories should follow the project philosophy:

> The LLM coordinates work. It does not perform the work.

Each story should therefore imply:

- what the user is trying to achieve
- what sources the system must inspect
- what tools may be required
- what evidence or trace the user needs to trust the result

The stories in this document intentionally focus on user outcomes before naming technical components.

---

# Agent Responsibilities

Across all user stories, the agent is responsible for:

- understanding the user's analytical intent
- identifying relevant documents and structured data
- selecting appropriate deterministic tools
- planning multi-step analytical workflows
- executing tools in the correct order
- distinguishing evidence from inference
- communicating uncertainty
- producing grounded and explainable answers

These responsibilities remain consistent regardless of the user's persona or workflow.

---

# Primary Personas

The MVP focuses on five primary personas:

1. Project Manager
2. Business Analyst
3. Engineer
4. Researcher
5. Consultant

These personas represent recurring knowledge-work patterns across planning, analysis, technical reasoning, research synthesis, and advisory work.

---

# Core Product Workflow

Every analytical workflow in Rastin-AI follows the same high-level execution model:

1. Upload one or more sources
2. Inspect extracted content
3. Ask an analytical question
4. Agent understands the request
5. Agent selects relevant tools
6. Agent retrieves required evidence
7. Deterministic tools execute the analysis
8. Agent synthesizes the results
9. User reviews evidence and execution trace
10. User refines the analysis if needed

All user stories in this document represent variations of this workflow.

---

# Epic 1: Ingest And Understand Work Materials

Knowledge workers need to bring documents and data into one workspace before analysis can begin.

## User Stories

### US-001: Upload Mixed Work Files

As a knowledge worker, I want to upload PDFs, spreadsheets, CSV files, and text documents so that I can analyze related materials in one place.

Acceptance criteria:

- The user can upload at least PDF, CSV, XLSX, DOCX, TXT, and Markdown files.
- The system identifies file type and stores basic metadata.
- The system reports unsupported or unreadable files clearly.
- Uploaded files become available to later analytical workflows.

Implied capabilities:

- Document ingestion
- Spreadsheet ingestion
- File metadata extraction
- Error handling

### US-002: Preview Source Content

As a knowledge worker, I want to inspect what the system extracted from my files so that I can verify the analysis is based on the correct source material.

Acceptance criteria:

- The user can see extracted text or structured previews.
- The user can inspect file names, types, and basic metadata.
- The system indicates extraction failures or partial extraction.

Implied capabilities:

- Document reader
- Spreadsheet parser
- Extraction status tracking

---

# Epic 2: Ask Analytical Questions Across Sources

Knowledge workers often need to ask one question that requires multiple files and data types.

## User Stories

### US-003: Ask A Question Over Uploaded Materials

As a knowledge worker, I want to ask a question about uploaded documents and data so that I can get an answer grounded in my own materials.

Acceptance criteria:

- The user can submit a natural-language question.
- The system selects relevant uploaded sources.
- The answer cites or references the source material used.
- The answer distinguishes evidence from interpretation.

Implied capabilities:

- Query understanding
- Retrieval
- Tool selection
- Source-grounded response generation

### US-004: Explain The Workflow Used

As a knowledge worker, I want to see which tools and sources were used so that I can trust and audit the result.

Acceptance criteria:

- The system shows selected tools.
- The system shows source files used.
- The system shows key intermediate steps.
- The system shows errors or skipped steps when they occur.

Implied capabilities:

- Agent execution trace
- Tool call logging
- Source tracking
- Explainability layer

---

# Epic 3: Project Manager Workflows

Project Managers work with schedules, budgets, reports, risks, and project documentation.

## User Stories

### US-005: Compare Budget Against Timeline

As a Project Manager, I want to compare project budget data with the schedule so that I can identify whether spending aligns with planned progress.

Acceptance criteria:

- The system can read budget data from spreadsheet files.
- The system can read timeline or milestone information from documents or spreadsheets.
- The system identifies mismatches, delays, or budget concerns.
- The system explains which data points support each finding.

Implied capabilities:

- Excel analyzer
- Document reader
- Cross-source comparison
- Calculation tool
- Report generation

### US-006: Extract Project Risks

As a Project Manager, I want the system to extract risks from project reports so that I can quickly prepare a risk summary.

Acceptance criteria:

- The system identifies risk statements from one or more documents.
- The system groups similar risks when possible.
- The system reports source references for extracted risks.
- The output can be reused in a project report.

Implied capabilities:

- PDF and DOCX reader
- Information extraction
- Clustering or grouping
- Summary generation

### US-007: Generate Status Report Draft

As a Project Manager, I want to generate a status report from project documents and spreadsheets so that I can reduce manual reporting work.

Acceptance criteria:

- The report includes progress, risks, blockers, and key metrics when available.
- The system identifies missing information instead of inventing it.
- The output is structured and editable.
- The report references the source files used.

Implied capabilities:

- Multi-source synthesis
- Spreadsheet analysis
- Document analysis
- Report generator

---

# Epic 4: Business Analyst Workflows

Business Analysts work with KPIs, CSV files, Excel files, metrics, trends, and business reports.

## User Stories

### US-008: Analyze KPI Data

As a Business Analyst, I want to analyze KPI data from CSV or Excel files so that I can understand trends and anomalies.

Acceptance criteria:

- The system detects columns, data types, and missing values.
- The system computes relevant summary statistics.
- The system identifies trends, outliers, or anomalies when possible.
- The system explains which calculations were performed.

Implied capabilities:

- CSV analyzer
- Excel analyzer
- Python calculation tool
- Data profiling

### US-009: Create Charts From Business Data

As a Business Analyst, I want to generate charts from structured data so that I can communicate findings clearly.

Acceptance criteria:

- The system recommends chart types based on the data and question.
- The system generates chart-ready outputs.
- The chart is based on deterministic data processing.
- The system explains the fields and filters used.

Implied capabilities:

- Data analysis tool
- Visualization tool
- Python executor

### US-010: Compare Metrics Across Reports

As a Business Analyst, I want to compare metrics across reports so that I can identify inconsistencies or changes over time.

Acceptance criteria:

- The system can extract comparable metrics from multiple files.
- The system identifies matching and conflicting values.
- The system preserves source references for each metric.
- The system summarizes the business impact of differences.

Implied capabilities:

- Document reader
- Spreadsheet analyzer
- Cross-document comparison
- Evidence tracking

---

# Epic 5: Engineer Workflows

Engineers work with specifications, standards, calculations, technical reports, and compliance constraints.

## User Stories

### US-011: Check Technical Requirements Against A Standard

As an Engineer, I want to compare a technical specification with a standard so that I can find gaps or compliance issues.

Acceptance criteria:

- The system extracts requirements from the specification.
- The system extracts relevant clauses from the standard.
- The system identifies matches, gaps, and possible conflicts.
- The system cites the relevant source sections.

Implied capabilities:

- PDF reader
- RAG search
- Requirement extraction
- Cross-document comparison

### US-012: Perform Engineering Calculations

As an Engineer, I want the system to perform calculations using values from documents or spreadsheets so that results are accurate and reproducible.

Acceptance criteria:

- The system extracts or asks for required input values.
- The system performs calculations using deterministic code.
- The system shows formulas or calculation steps.
- The system avoids guessing missing values.

Implied capabilities:

- Data extraction
- Python executor
- Calculation trace
- Validation checks

### US-013: Summarize A Technical Report

As an Engineer, I want to summarize a technical report so that I can quickly understand assumptions, methods, results, and limitations.

Acceptance criteria:

- The summary separates facts, assumptions, results, and limitations.
- The system preserves references to important sections.
- The system flags uncertainty or missing information.

Implied capabilities:

- Document reader
- Structured summarization
- Source citation

---

# Epic 6: Researcher Workflows

Researchers work with papers, literature reviews, comparisons, citations, and evidence extraction.

## User Stories

### US-014: Summarize Research Papers

As a Researcher, I want to summarize research papers so that I can understand the question, method, findings, and limitations quickly.

Acceptance criteria:

- The system extracts title, authors, abstract, method, results, and limitations when available.
- The summary stays grounded in the paper.
- The system does not invent missing claims.
- The system references source sections or pages when possible.

Implied capabilities:

- PDF reader
- Paper structure extraction
- Summarization
- Citation-aware references

### US-015: Compare Multiple Papers

As a Researcher, I want to compare multiple papers so that I can identify agreements, disagreements, methods, datasets, and evidence gaps.

Acceptance criteria:

- The system compares papers using consistent dimensions.
- The system identifies conflicting claims or different assumptions.
- The output includes a comparison table.
- Each comparison point is traceable to source material.

Implied capabilities:

- Multi-document retrieval
- Comparison table generation
- Evidence extraction

### US-016: Extract Citations And References

As a Researcher, I want to extract citations and references so that I can organize research sources.

Acceptance criteria:

- The system extracts references when they are available in the document.
- The system preserves citation text and metadata when possible.
- The system reports when references cannot be reliably extracted.

Implied capabilities:

- PDF parsing
- Citation extraction
- Metadata extraction

---

# Epic 7: Consultant Workflows

Consultants work with client documents, current-state analysis, benchmark comparisons, recommendations, and presentation-ready reports.

## User Stories

### US-017: Analyze Client Documents

As a Consultant, I want to analyze client documents so that I can understand the current situation, key issues, and available evidence.

Acceptance criteria:

- The system extracts themes, issues, constraints, and opportunities.
- The system groups related findings.
- The system references the documents behind each finding.
- The system distinguishes explicit evidence from inferred conclusions.

Implied capabilities:

- Document reader
- Multi-document synthesis
- Thematic extraction
- Evidence tracking

### US-018: Compare Client Documents

As a Consultant, I want to compare client documents so that I can find inconsistencies, gaps, and repeated patterns.

Acceptance criteria:

- The system compares documents across user-selected dimensions.
- The system highlights contradictions or missing information.
- The system produces a structured comparison output.
- The system links findings back to source files.

Implied capabilities:

- Cross-document comparison
- Retrieval
- Structured output generation

### US-019: Generate Recommendation Report

As a Consultant, I want to generate a recommendation report so that I can turn analysis into a client-ready deliverable.

Acceptance criteria:

- The report includes findings, evidence, risks, and recommendations.
- Recommendations are tied to source evidence.
- The system identifies assumptions and missing information.
- The report is structured for later editing.

Implied capabilities:

- Report generator
- Evidence-grounded synthesis
- Risk extraction
- Recommendation drafting

---

# Epic 8: Trust, Control, And Correction

Users must stay in control of analytical workflows and be able to inspect or correct outputs.

## User Stories

### US-020: Review Source Evidence

As a knowledge worker, I want to review the source evidence behind an answer so that I can validate important claims.

Acceptance criteria:

- Each major claim includes a reference to source material where possible.
- The user can inspect the source file or extracted text.
- Unsupported claims are marked as assumptions or omitted.

Implied capabilities:

- Citation or source linking
- Evidence extraction
- Answer validation

### US-021: Correct Or Refine The Request

As a knowledge worker, I want to refine my question after seeing an answer so that I can guide the analysis toward the right outcome.

Acceptance criteria:

- The user can ask follow-up questions.
- The system keeps relevant workflow context.
- The system can rerun or adjust tool selection based on the refined request.

Implied capabilities:

- Conversation state
- Workflow context
- Agent replanning

### US-022: Know When The System Is Uncertain

As a knowledge worker, I want the system to communicate uncertainty so that I do not overtrust weak or incomplete results.

Acceptance criteria:

- The system flags missing data, low-confidence extraction, or unsupported conclusions.
- The system asks for clarification when required information is unavailable.
- The system avoids fabricating values, citations, or calculations.

Implied capabilities:

- Confidence reporting
- Input validation
- Guardrails

---

# MVP Story Set

The MVP should focus on a small set of stories that prove the core product loop:

| Story | Why it belongs to the MVP |
| --- | --- |
| US-001 | Enables file ingestion |
| US-003 | Defines the primary interaction |
| US-004 | Introduces explainability |
| US-005 | Demonstrates multi-tool orchestration |
| US-008 | Validates structured data analysis |
| US-011 | Shows engineering reasoning |
| US-014 | Validates document understanding |
| US-020 | Builds user trust through evidence |

This set validates the essential workflow:

> Upload sources -> ask analytical question -> select tools -> execute workflow -> produce grounded answer -> show evidence and trace.

---

# Capability Map

The stories imply the following early capabilities:

| Capability | Stories | Future Module |
| --- | --- | --- |
| File ingestion | US-001, US-002 | ingestion |
| Document reading | US-002, US-006, US-011, US-014 | document_tools |
| Spreadsheet analysis | US-005, US-008, US-009 | spreadsheet_tools |
| Retrieval & grounding | US-003, US-011, US-015, US-020 | rag |
| Deterministic calculations | US-005, US-008, US-012 | python_executor |
| Cross-document reasoning | US-005, US-010, US-011, US-015, US-018 | comparison |
| Report generation | US-007, US-019 | reporting |
| Visualization | US-009 | visualization |
| Agent planning | US-003, US-004, US-021 | planner |
| Observability | US-004, US-020, US-022 | observability |

---

# Out Of Scope For MVP

The following stories or capabilities should be deferred unless needed for a focused demo:

- Full user management and authentication
- Enterprise permissions
- Multi-user collaboration
- Voice interaction
- Fine-tuning or model training
- Self-hosted LLM deployment
- Complex project management integrations
- Full citation manager functionality
- Presentation slide generation

---

# Story Traceability

This document intentionally serves as the bridge between product design and software architecture.

The traceability path throughout the project is:

Project Vision
-> Personas
-> User Stories
-> Functional Requirements
-> Agent Architecture
-> Tool Specifications
-> API Design
-> Implementation
-> Evaluation

---

# Next Step

This document should feed directly into functional requirements.

The next design question is:

> What system capabilities are required to satisfy the MVP user stories reliably?
