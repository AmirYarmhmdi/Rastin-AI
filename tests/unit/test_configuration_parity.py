"""File guide.

- Use: Tests deployment/configuration parity across Settings, env, and Compose.
- Usage: Run with pytest when editing runtime configuration or deployment docs.
- Duties: Prevents stale environment-variable names and accidental startup
  migration coupling.
- Depends on: Standard library plus PyYAML from project dependencies. Project
  module: rastin_ai.core.config.
"""

from pathlib import Path

import yaml

from rastin_ai.core.config import application_setting_names

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_app_environment_names_match_settings() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text())
    app_environment = compose["services"]["rastin-ai"]["environment"]

    unknown_names = set(app_environment) - set(application_setting_names())

    assert unknown_names == set()


def test_env_example_covers_application_settings() -> None:
    env_names = _env_example_names()

    missing = set(application_setting_names()) - env_names

    assert missing == set()


def test_migration_strategy_is_external_to_application_replica_startup() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text()
    main = (PROJECT_ROOT / "src/rastin_ai/main.py").read_text()

    assert "alembic upgrade" not in dockerfile
    assert "alembic upgrade" not in compose
    assert "alembic" not in main


def _env_example_names() -> set[str]:
    names = set()
    for line in (PROJECT_ROOT / ".env.example").read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, _value = stripped.partition("=")
        names.add(name)
    return names
