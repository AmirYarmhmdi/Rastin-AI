# Docker Runtime

The root `Dockerfile` builds the Rastin-AI application image. The root
`docker-compose.yml` runs the local development stack: Rastin-AI, PostgreSQL,
Qdrant, Langfuse, ClickHouse, Redis, and MinIO.

## Local Compose Matrix

| Concern | Compose setting | Container setting |
| --- | --- | --- |
| API bind | `COMPOSE_RASTIN_AI_BIND_HOST`, `COMPOSE_RASTIN_AI_PORT` | `HOST=0.0.0.0`, `PORT=8000` |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/...` |
| Qdrant | `COMPOSE_QDRANT_BIND_HOST` | `QDRANT_URL=http://qdrant:6333` |
| Local storage | named volume `rastin_ai_storage` | `STORAGE_BACKEND=local`, `LOCAL_STORAGE_ROOT=/app/storage` |
| Langfuse tracing | `LANGFUSE_*` project keys | Optional; disabled unless `LANGFUSE_ENABLED=true` and keys are present |

The app container receives canonical application variable names from
`rastin_ai.core.config.Settings`. Compose-only variables are used only for
host port binding and local support services.

## Commands

Build and start the local stack:

```bash
docker compose up -d --build
```

Run migrations explicitly after PostgreSQL is healthy:

```bash
docker compose run --rm rastin-ai uv run alembic upgrade head
```

Check health:

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/ready
```

Stop the stack:

```bash
docker compose down
```

Use `docker compose down -v` only when intentionally deleting local persisted
volumes.

Run the isolated end-to-end test stack:

```bash
bash scripts/run_e2e.sh
```

The E2E script starts the standalone `docker-compose.e2e.yml` Postgres/Qdrant
stack. It uses separate host ports and named volumes, runs Alembic migrations
against a disposable `_test` database, disables Langfuse, and exercises public
API upload, indexing, RAG, session, routing, and failure flows with
deterministic model doubles.

## Migration Boundary

The application image starts Uvicorn only. It does not run Alembic at container
startup, because multiple app replicas must not independently run schema
migrations. Run migrations as an explicit local command or one-off deployment
job before rolling app replicas.
