#!/usr/bin/env bash
# File guide.
# Use: Starts disposable local services and runs the Rastin-AI E2E suite.
# Usage: bash scripts/run_e2e.sh
# Duties: Runs Postgres/Qdrant in an isolated Compose project and cleans them up.
# Depends on: docker-compose.e2e.yml, uv, and pytest.

set -euo pipefail

COMPOSE_FILES=(-f docker-compose.e2e.yml)

cleanup() {
  docker compose "${COMPOSE_FILES[@]}" down -v --remove-orphans
}

trap cleanup EXIT

docker compose "${COMPOSE_FILES[@]}" up -d --wait postgres qdrant

export RASTIN_AI_E2E=1
export RASTIN_AI_TEST_DATABASE_URL="postgresql+asyncpg://rastin_ai_e2e:rastin_ai_e2e_password@127.0.0.1:15432/rastin_ai_e2e_test"
export RASTIN_AI_TEST_QDRANT_URL="http://127.0.0.1:16333"
export DEBUG=false
export ENVIRONMENT=test
export LANGFUSE_ENABLED=false

if [ "$#" -gt 0 ]; then
  uv run pytest "$@"
else
  uv run pytest tests/e2e -m e2e -v
fi
