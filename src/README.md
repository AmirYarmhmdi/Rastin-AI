# Source

This folder contains the installable Python source tree.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `rastin_ai/` | Main backend package for API, services, agent components, RAG, storage, persistence, evaluation, and tools. | HTTP requests, uploaded files, environment settings, database state, vector-store state, and model-provider responses. | API responses, persisted metadata, workflow records, retrieved context, generated answers, and evaluation results. |

## General Role

`src/` separates application code from repository-level files such as tests,
documentation, migrations, and deployment configuration. Python packaging is
configured in `pyproject.toml`, which points the build system at
`src/rastin_ai`.

## Development Notes

Tests import this package through the configured `pythonpath = ["src"]` setting
in `pyproject.toml`. New backend modules should usually live somewhere under
`src/rastin_ai` and should have matching tests under `tests/`.
