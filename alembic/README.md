# Alembic

This folder contains database migration configuration and migration revisions for
Rastin-AI's PostgreSQL schema.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `env.py` | Connects Alembic to the application database metadata and runtime settings. | Alembic commands, database URL/settings, SQLAlchemy model metadata. | A configured migration environment that can create or apply revisions. |
| `script.py.mako` | Template used when Alembic generates a new migration file. | `uv run alembic revision ...` commands. | New revision files with the expected Python structure. |
| `versions/` | Ordered migration history for schema changes. | Schema changes expressed as migration scripts. | Database tables, columns, indexes, and constraints applied in a repeatable order. |

## General Role

Alembic keeps the database schema synchronized with the application models under
`src/rastin_ai/database`. It is the bridge between source-controlled schema
intent and the actual PostgreSQL database used by the API, services, and tests.

## Typical Flow

1. SQLAlchemy models change in `src/rastin_ai/database/models`.
2. A migration is created under `alembic/versions`.
3. `uv run alembic upgrade head` applies the migration.
4. The running application can read and write data using the new schema.
