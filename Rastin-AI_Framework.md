# Rastin-AI Project Framework

## Vision
An open-source AI platform for knowledge workers (project managers, analysts, engineers, consultants, researchers) that can reason over documents and data, decide which tools to use, and produce reliable answers and reports.

## High-Level Architecture

```text
                Web UI (later)
                     │
                FastAPI REST API
                     │
              LangGraph Supervisor
                     │
     ┌───────────────┼────────────────┐
     │               │                │
Document Tools   Data Tools      Reasoning
(PDF/DOCX)      (CSV/XLSX)      OpenAI LLM
     │               │                │
     └───────────────┼────────────────┘
                     │
              Tool Calling Layer
                     │
  ┌─────────────┬──────────────┬─────────────┐
  │             │              │             │
RAG         Python Tool    Report Tool   Visualization
  │
Qdrant + pgvector(PostgreSQL)
                     │
               Langfuse Tracing
                     │
      DeepEval + Ragas (Evaluation)
                     │
 Docker → Docker Compose → Azure
                     │
          GitHub Actions (CI/CD)
```

## Core Components

### API
- FastAPI
- Authentication (later)
- REST endpoints
- Streaming responses

### Agent
- LangGraph supervisor
- Planning
- Tool routing
- Memory (later)

### LLM
- OpenAI
- Structured outputs
- Function/Tool calling

### Storage
- PostgreSQL
- pgvector
- Qdrant

### Observability
- Langfuse
- OpenTelemetry (later)

### Evaluation
- DeepEval
- Ragas

### Deployment
- Docker
- Docker Compose
- Azure
- GitHub Actions

### MCP
- Planned after MVP.

## Initial Tools

1. Document Reader
- PDF
- DOCX
- TXT
- Markdown

2. Spreadsheet Analyzer
- CSV
- XLSX

3. Python Executor
- Statistics
- Charts
- Calculations

4. RAG Search

5. Report Generator
- Markdown
- PDF (later)

6. Visualization
- Tables
- Charts

## Typical Workflow

1. Upload files.
2. Ask a question.
3. LangGraph plans.
4. Select tools.
5. Retrieve context.
6. Execute calculations if needed.
7. Generate answer.
8. Log traces.
9. Evaluate quality.

## Roadmap

### Phase 1 (MVP)
- FastAPI
- LangGraph
- OpenAI
- Document Reader
- Spreadsheet Analyzer
- Python Tool

### Phase 2
- PostgreSQL
- pgvector
- Qdrant
- RAG

### Phase 3
- Langfuse
- DeepEval
- Ragas

### Phase 4
- Docker
- Docker Compose
- GitHub Actions
- Azure

### Phase 5
- MCP
- Authentication
- Multi-user

----------
Next high-value formats

1. TXT
2. Markdown
3. JSON
4. DOCX
5. PPTX
6. HTML
7. XML