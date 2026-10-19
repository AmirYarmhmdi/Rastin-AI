"""File guide.

- Use: Provides optional Langfuse-backed observability helpers.
- Usage: Call observed_* context managers around workflow, generation, and tool
  boundaries.
- Duties: Lazily configures Langfuse, injects LangChain callbacks, redacts traced
  payloads, and shuts telemetry down safely.
- Depends on: Standard library plus optional Langfuse SDK. Project module:
  rastin_ai.core.config.
"""

import logging
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from typing import Any

from pydantic import BaseModel

from rastin_ai.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_OBSERVED_STRING_LENGTH = 2_000
MAX_OBSERVED_SEQUENCE_ITEMS = 20
MAX_OBSERVED_MAPPING_ITEMS = 50
MAX_OBSERVED_DEPTH = 5

SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "file_path",
    "local_path",
    "password",
    "private_key",
    "secret",
    "storage_key",
    "token",
)
SENSITIVE_EXACT_KEYS = ("path",)

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._\-]+"),
    re.compile(r"(?i)\b(sk|pk)-[a-z0-9._\-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|password|secret|token)"
        r"([:=\-\s]+)[^,\s;}]+"
    ),
)


def is_observability_enabled(settings: Settings | None = None) -> bool:
    """Return whether Langfuse tracing should be active for this process."""
    resolved = _resolve_settings(settings)
    if resolved is None:
        return False
    return bool(
        resolved.LANGFUSE_ENABLED
        and resolved.LANGFUSE_PUBLIC_KEY
        and resolved.LANGFUSE_SECRET_KEY
    )


def startup_observability(settings: Settings | None = None) -> bool:
    """Prepare optional observability and log the effective state."""
    resolved = settings or get_settings()
    if not resolved.LANGFUSE_ENABLED:
        logger.info("Observability disabled.")
        return False

    if not is_observability_enabled(resolved):
        logger.warning(
            "Observability disabled because Langfuse credentials are incomplete."
        )
        return False

    _configure_langfuse_environment(resolved)
    if _get_langfuse_client(resolved) is None:
        logger.warning("Observability disabled because Langfuse could not initialize.")
        return False

    logger.info("Observability enabled with Langfuse.")
    return True


def shutdown_observability(settings: Settings | None = None) -> None:
    """Flush and close telemetry without making shutdown depend on Langfuse."""
    client = _get_langfuse_client(settings)
    if client is None:
        return

    for method_name in ("flush", "shutdown"):
        method = getattr(client, method_name, None)
        if method is None:
            continue
        try:
            method()
        except Exception:
            logger.debug(
                "Langfuse %s failed during shutdown.",
                method_name,
                exc_info=True,
            )


def get_langchain_callbacks(settings: Settings | None = None) -> list[Any]:
    """Return callback handlers for LangChain/LangGraph invocations."""
    if not is_observability_enabled(settings):
        return []

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.warning("Langfuse LangChain callback is unavailable.")
        return []

    try:
        return [CallbackHandler()]
    except Exception:
        logger.debug("Failed to create Langfuse LangChain callback.", exc_info=True)
        return []


def with_langgraph_callbacks(
    config: Mapping[str, Any] | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Return LangGraph invocation config with Langfuse callbacks when enabled."""
    callbacks = get_langchain_callbacks(settings)
    if not callbacks:
        return dict(config) if config is not None else None

    merged_config = dict(config) if config is not None else {}
    existing_callbacks = merged_config.get("callbacks", [])
    if existing_callbacks is None:
        existing_callbacks = []
    elif not isinstance(existing_callbacks, list):
        existing_callbacks = list(existing_callbacks)

    merged_config["callbacks"] = [*existing_callbacks, *callbacks]
    return merged_config


@contextmanager
def observed_workflow(
    *,
    name: str,
    input: Any = None,
    metadata: Mapping[str, Any] | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    settings: Settings | None = None,
) -> Iterator[Any]:
    """Create a root workflow observation when Langfuse is enabled."""
    metadata_payload = dict(metadata or {})
    with _propagated_attributes(
        settings=settings,
        metadata=metadata_payload,
        session_id=session_id,
        user_id=user_id,
    ):
        with _safe_current_observation(
            settings=settings,
            as_type="agent",
            name=name,
            input=sanitize_for_observability(input),
            metadata=sanitize_for_observability(metadata_payload),
        ) as observation:
            yield observation


@contextmanager
def observed_generation(
    *,
    name: str,
    model: str,
    input: Any,
    metadata: Mapping[str, Any] | None = None,
    settings: Settings | None = None,
) -> Iterator[Any]:
    """Create a generation observation for direct model SDK calls."""
    with _safe_current_observation(
        settings=settings,
        as_type="generation",
        name=name,
        model=model,
        input=sanitize_for_observability(input),
        metadata=sanitize_for_observability(metadata or {}),
    ) as observation:
        yield observation


@contextmanager
def observed_span(
    *,
    name: str,
    input: Any = None,
    metadata: Mapping[str, Any] | None = None,
    settings: Settings | None = None,
) -> Iterator[Any]:
    """Create a child span observation when Langfuse is enabled."""
    with _safe_current_observation(
        settings=settings,
        as_type="span",
        name=name,
        input=sanitize_for_observability(input),
        metadata=sanitize_for_observability(metadata or {}),
    ) as observation:
        yield observation


@contextmanager
def observed_tool(
    *,
    name: str,
    input: Any,
    metadata: Mapping[str, Any] | None = None,
    settings: Settings | None = None,
) -> Iterator[Any]:
    """Create a tool observation for deterministic tool execution."""
    with _safe_current_observation(
        settings=settings,
        as_type="tool",
        name=name,
        input=sanitize_for_observability(input),
        metadata=sanitize_for_observability(metadata or {}),
    ) as observation:
        yield observation


def safe_update_observation(observation: Any, **kwargs: Any) -> None:
    """Update an observation with bounded, redacted payloads."""
    _safe_update(
        observation,
        **{key: sanitize_for_observability(value) for key, value in kwargs.items()},
    )


def trace_id_from_observation(observation: Any) -> str | None:
    """Best-effort extraction of the active trace ID from a Langfuse observation."""
    for attr_name in ("trace_id", "traceId"):
        value = getattr(observation, attr_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for method_name in ("get_trace_id", "trace_id"):
        method = getattr(observation, method_name, None)
        if callable(method):
            try:
                value = method()
            except Exception:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()

    trace = getattr(observation, "trace", None)
    if trace is not None:
        trace_id = getattr(trace, "id", None)
        if isinstance(trace_id, str) and trace_id.strip():
            return trace_id.strip()

    return None


def sanitize_for_observability(value: Any, *, _depth: int = 0) -> Any:
    """Return a bounded, JSON-friendly representation for telemetry."""
    if _depth >= MAX_OBSERVED_DEPTH:
        return _summarize_value(value)

    if isinstance(value, BaseModel):
        return sanitize_for_observability(value.model_dump(mode="json"), _depth=_depth)

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:MAX_OBSERVED_MAPPING_ITEMS]:
            key_text = str(key)
            if _is_sensitive_key(key_text):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = sanitize_for_observability(
                    item,
                    _depth=_depth + 1,
                )
        if len(items) > MAX_OBSERVED_MAPPING_ITEMS:
            sanitized["_truncated_items"] = len(items) - MAX_OBSERVED_MAPPING_ITEMS
        return sanitized

    if isinstance(value, str):
        return _redact_and_truncate(value)

    if isinstance(value, bytes | bytearray | memoryview):
        return f"<binary length={len(value)}>"

    if isinstance(value, Sequence) and not isinstance(value, str):
        items = [
            sanitize_for_observability(item, _depth=_depth + 1)
            for item in list(value)[:MAX_OBSERVED_SEQUENCE_ITEMS]
        ]
        if len(value) > MAX_OBSERVED_SEQUENCE_ITEMS:
            items.append({"_truncated_items": len(value) - MAX_OBSERVED_SEQUENCE_ITEMS})
        return items

    if isinstance(value, int | float | bool) or value is None:
        return value

    return _redact_and_truncate(str(value))


def usage_details_from_response(response: Any) -> dict[str, int] | None:
    """Extract provider-reported token usage without estimating tokens."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    raw_usage = _object_to_mapping(usage)
    details: dict[str, int] = {}
    for key, value in raw_usage.items():
        if isinstance(value, int):
            details[key] = value

    for nested_name in ("input_tokens_details", "output_tokens_details"):
        nested = raw_usage.get(nested_name)
        if nested is None:
            continue
        prefix = nested_name.removesuffix("_details")
        for key, value in _object_to_mapping(nested).items():
            if isinstance(value, int):
                details[f"{prefix}_{key}"] = value

    return details or None


@contextmanager
def _safe_current_observation(
    *,
    settings: Settings | None,
    as_type: str,
    name: str,
    input: Any = None,
    metadata: Any = None,
    model: str | None = None,
) -> Iterator[Any]:
    client = _get_langfuse_client(settings)
    if client is None:
        yield _NoopObservation()
        return

    kwargs = {
        "as_type": as_type,
        "name": name,
        "input": input,
        "metadata": metadata,
    }
    if model is not None:
        kwargs["model"] = model

    manager = None
    observation = _NoopObservation()
    try:
        manager = client.start_as_current_observation(**kwargs)
        observation = manager.__enter__()
    except Exception:
        logger.debug("Failed to start Langfuse observation.", exc_info=True)
        yield _NoopObservation()
        return

    try:
        yield observation
    except BaseException as exc:
        _safe_update(
            observation,
            level="ERROR",
            status_message=_safe_error_message(exc),
        )
        if manager is not None:
            try:
                manager.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                logger.debug("Failed to close Langfuse observation.", exc_info=True)
        raise
    else:
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                logger.debug("Failed to close Langfuse observation.", exc_info=True)


@contextmanager
def _propagated_attributes(
    *,
    settings: Settings | None,
    metadata: Mapping[str, Any],
    session_id: str | None,
    user_id: str | None,
) -> Iterator[None]:
    if not is_observability_enabled(settings):
        yield
        return

    try:
        from langfuse import propagate_attributes
    except ImportError:
        yield
        return

    kwargs: dict[str, Any] = {
        "metadata": sanitize_for_observability(metadata),
        "tags": ("rastin_ai",),
    }
    if session_id is not None:
        kwargs["session_id"] = session_id
    if user_id is not None:
        kwargs["user_id"] = user_id

    with ExitStack() as stack:
        try:
            stack.enter_context(propagate_attributes(**kwargs))
        except Exception:
            logger.debug("Failed to propagate Langfuse attributes.", exc_info=True)
        yield


def _get_langfuse_client(settings: Settings | None = None) -> Any | None:
    resolved = _resolve_settings(settings)
    if resolved is None:
        return None
    if not is_observability_enabled(resolved):
        return None

    _configure_langfuse_environment(resolved)
    try:
        from langfuse import get_client
    except ImportError:
        return None

    try:
        return get_client()
    except Exception:
        logger.debug("Failed to get Langfuse client.", exc_info=True)
        return None


def _resolve_settings(settings: Settings | None = None) -> Settings | None:
    if settings is not None:
        return settings
    try:
        return get_settings()
    except Exception:
        logger.debug("Settings could not be loaded for observability.", exc_info=True)
        return None


def _configure_langfuse_environment(settings: Settings) -> None:
    if settings.LANGFUSE_PUBLIC_KEY:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
    if settings.LANGFUSE_SECRET_KEY:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
    base_url = settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST
    if base_url:
        os.environ["LANGFUSE_BASE_URL"] = base_url


def _safe_update(observation: Any, **kwargs: Any) -> None:
    update = getattr(observation, "update", None)
    if update is None:
        return
    try:
        update(**kwargs)
    except Exception:
        logger.debug("Failed to update Langfuse observation.", exc_info=True)


def _object_to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        except Exception:
            pass
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in SENSITIVE_EXACT_KEYS or any(
        part in normalized for part in SENSITIVE_KEY_PARTS
    )


def _redact_and_truncate(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_redacted_match, redacted)
    if len(redacted) <= MAX_OBSERVED_STRING_LENGTH:
        return redacted
    return f"{redacted[:MAX_OBSERVED_STRING_LENGTH]}...<truncated>"


def _redacted_match(match: re.Match[str]) -> str:
    if len(match.groups()) == 1:
        return f"{match.group(1)} [REDACTED]"
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def _safe_error_message(exc: BaseException) -> str:
    return _redact_and_truncate(f"{type(exc).__name__}: {exc}")


def _summarize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return f"<mapping length={len(value)}>"
    if isinstance(value, Sequence) and not isinstance(value, str):
        return f"<sequence length={len(value)}>"
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<binary length={len(value)}>"
    return _redact_and_truncate(str(value))


class _NoopObservation:
    def update(self, **kwargs: Any) -> None:
        return None

    def end(self, **kwargs: Any) -> None:
        return None

    def start_as_current_observation(
        self,
        **kwargs: Any,
    ) -> AbstractContextManager[Any]:
        return nullcontext(_NoopObservation())
