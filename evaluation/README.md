# Evaluation

Rastin-AI owns a small, framework-neutral evaluation layer. Canonical datasets
live as JSONL records and can feed Ragas, DeepEval, or later evaluator adapters
without duplicating goldens. The checked-in smoke dataset currently covers RAG
context-building and agent tool-selection behavior.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `datasets/` | Stores versioned evaluation cases as JSONL. | Questions, expected answers, expected/retrieved contexts, tags, and metadata. | Validated goldens for smoke, regression, and evaluator-backed runs. |
| `README.md` | Explains dataset format and evaluation commands. | Evaluation conventions and local/CI workflows. | A guide for adding and running evaluations. |

## General Role

This folder contains evaluation data and evaluator-facing documentation. The
Python implementation that validates and runs these cases lives in
`src/rastin_ai/evaluation`, while tests for the evaluation layer live under
`tests/unit/evaluation` and `tests/evaluation`.

## Dataset Format

Each JSONL line is one `EvaluationCase` with:

- `id`: stable case identifier
- `input`: user query or workflow input
- `expected_output`: reference answer when a metric needs one
- `actual_output`: observed answer for stored smoke/regression cases
- `expected_contexts`: gold contexts
- `retrieved_contexts`: contexts returned by the system under evaluation
- `metadata`: arbitrary JSON object
- `tags`: filterable labels
- optional tool fields: `expected_tool_name`, `expected_tool_arguments`,
  `expected_behavior`

Records are validated with a strict schema: unknown fields are rejected, blank
lines are ignored, duplicate IDs fail validation, string values are stripped, and
list-like fields must contain non-empty strings. Use `tags` to select a subset
of cases for local or CI runs.

Static smoke/regression records may include checked-in `actual_output` and
`retrieved_contexts`. Those fields are hand-written observations used to test
evaluation infrastructure. They are not produced by the current runtime.

Live runtime datasets keep runtime setup under `metadata.live.documents`. The
live runner uploads those synthetic fixture documents, indexes them, asks the
runtime question, and builds a new in-memory `EvaluationCase` with generated
`actual_output` and `retrieved_contexts`. The source JSONL is not modified.
Cases may opt in to safe report text with `metadata.live.safe_report_text=true`.
That flag is intended only for synthetic fixtures that contain no private,
credential, or user-supplied content.

## Local Commands

Validate the dataset without external API calls:

```bash
uv run python -m rastin_ai.evaluation validate --dataset evaluation/datasets/smoke.jsonl
```

Validate only tagged smoke cases:

```bash
uv run python -m rastin_ai.evaluation validate --dataset evaluation/datasets/smoke.jsonl --tags smoke
```

Run deterministic evaluation infrastructure tests:

```bash
uv run pytest tests/unit/evaluation
```

Run Ragas smoke evaluation after installing evaluation dependencies and setting
`OPENAI_API_KEY`:

```bash
uv run --group evaluation python -m rastin_ai.evaluation ragas --dataset evaluation/datasets/smoke.jsonl --tags smoke
```

Run DeepEval regression tests:

```bash
uv run --group evaluation pytest -m evaluation tests/evaluation
```

Run the opt-in live runtime DeepEval path:

```bash
RUN_LIVE_EVALUATION=1 \
DATABASE_URL=postgresql+asyncpg://rastin_ai:rastin_ai_password@localhost:5432/rastin_ai \
QDRANT_URL=http://localhost:6333 \
QDRANT_COLLECTION_NAME=rastin_ai_live_eval \
OPENAI_API_KEY=... \
uv run --group evaluation python -m rastin_ai.evaluation live-deepeval \
  --dataset evaluation/datasets/live_smoke.jsonl \
  --tags live smoke \
  --max-cases 1 \
  --include-report-text \
  --context-preview-chars 500 \
  --report-path evaluation-results/live-deepeval-report.json
```

The live command requires:

- `RUN_LIVE_EVALUATION=1`
- evaluation dependencies installed with `uv sync --group evaluation`
- a reachable PostgreSQL database with Rastin-AI migrations already applied
- a reachable Qdrant instance
- `OPENAI_API_KEY`
- a dedicated small `QDRANT_COLLECTION_NAME` for evaluation runs

The live path uses the configured runtime models:

- embeddings: `OPENAI_EMBEDDING_MODEL`
- answer generation: `OPENAI_RESPONSE_MODEL`
- evaluator model: `EVALUATION_MODEL`

The default live command runs only one tagged smoke case. Increase
`--max-cases` explicitly when you are ready to spend more. Reports include
scores, thresholds, pass/fail status, latency, model name, token usage when the
provider returns it, workflow/trace IDs when available, and safe context counts.
They do not include API keys, credentials, arbitrary uploaded user documents, or
full retrieved document text.

By default, report text is omitted. Add `--include-report-text` only for
synthetic cases marked with `metadata.live.safe_report_text=true`; the report
will then include `input`, `expected_output`, `actual_output`, and bounded
retrieved-context previews. `--context-preview-chars` controls the maximum
characters per retrieved context preview. Reports containing this text are marked
with `contains_safe_test_text=true` and per-case `report_text_policy` values.

`trace_id` is `null` when Langfuse tracing is disabled, unavailable, or not
configured with credentials. Live evaluation does not require Langfuse and does
not fail when tracing is unavailable. When Langfuse is enabled and returns a
trace ID, the existing question-answering workflow persistence path stores it on
the workflow record and the live report surfaces it.

## Thresholds

Thresholds are centralized in `Settings` and `EvaluationThresholds`. The initial
defaults are baseline values for early CI smoke runs and should be calibrated
against real production goldens:

- answer relevancy: `0.70` minimum
- faithfulness: `0.70` minimum
- context precision: `0.70` minimum
- context recall: `0.70` minimum
- hallucination: `0.30` maximum

## CI

The main CI workflow owns linting, formatting, unit tests, integration tests,
and Docker builds. The separate evaluation workflow owns evaluation-specific
checks.

For pull requests and pushes to `main`, the evaluation workflow runs only when
evaluation-relevant files change. The automatic job validates tagged smoke cases
without external API calls and uploads `dataset-validation.json`.

LLM-backed DeepEval and Ragas smoke checks run only from `workflow_dispatch`.
They use the existing `OPENAI_API_KEY` secret when available. If the secret is
not configured, the workflow records a JSON skip report instead of failing
before any evaluator runs.
