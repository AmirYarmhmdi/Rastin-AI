# Tests

This folder contains automated tests for backend, frontend-adjacent contracts,
RAG, storage, agent behavior, evaluation infrastructure, and smoke workflows.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `unit/` | Tests isolated modules and service behavior. | Python functions/classes, mocked dependencies, fixtures. | Fast feedback about local correctness and regressions. |
| `integration/` | Tests cross-component behavior that needs more realistic wiring. | Multiple backend modules and external-service-style dependencies such as Qdrant. | Confidence that components work together across boundaries. |
| `evaluation/` | Runs evaluator-specific or LLM-backed evaluation tests. | Evaluation datasets, evaluator dependencies, model credentials when required. | Quality reports or marked test results for evaluation scenarios. |
| `e2e/` | Runs isolated end-to-end checks through public API routes. | Disposable PostgreSQL, Qdrant, local storage, Alembic migrations, deterministic model doubles. | Proof that upload, persistence, indexing, RAG, sessions, routing, and failure states work together without production data. |

## General Role

Tests protect the contracts described in `docs/` and implemented under
`src/rastin_ai`. Unit tests should cover most deterministic behavior;
integration, evaluation, and e2e tests should be used where confidence depends
on multiple moving parts.

## Useful Commands

```bash
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/evaluation
bash scripts/run_e2e.sh
```

Some evaluation tests require optional dependencies or credentials such as
`OPENAI_API_KEY`.

## Isolated End-To-End Tests

The repeatable E2E harness lives in `tests/e2e/` and is gated by
`RASTIN_AI_E2E=1`. It uses real FastAPI routing, Alembic migrations,
PostgreSQL repositories, local storage, Qdrant indexing/search, conversation
persistence, and workflow persistence. It replaces only external
model-dependent boundaries with deterministic test doubles: embeddings,
response generation, and the LangGraph graph object.

Run the full local E2E stack:

```bash
bash scripts/run_e2e.sh
```

Run one focused E2E scenario against the same disposable stack:

```bash
bash scripts/run_e2e.sh tests/e2e/test_real_runtime_workflow.py::test_persistent_multi_turn_conversation -v
```

The script starts the standalone `docker-compose.e2e.yml` Postgres/Qdrant
stack, binds PostgreSQL on `127.0.0.1:15432`, binds Qdrant on
`127.0.0.1:16333`, creates a unique Qdrant collection per test run, resets only
a database whose name ends in `_test`, disables Langfuse, and removes the
disposable Compose volumes on exit.

To run manually against already-running disposable services:

```bash
export RASTIN_AI_E2E=1
export RASTIN_AI_TEST_DATABASE_URL=postgresql+asyncpg://rastin_ai_e2e:rastin_ai_e2e_password@127.0.0.1:15432/rastin_ai_e2e_test
export RASTIN_AI_TEST_QDRANT_URL=http://127.0.0.1:16333
export LANGFUSE_ENABLED=false
uv run pytest tests/e2e -m e2e -v
```

Do not point `RASTIN_AI_TEST_DATABASE_URL` at a shared, development, staging,
or production database. The harness intentionally drops and recreates the
`public` schema and skips unless the database name ends in `_test`.
