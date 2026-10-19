"""File guide.

- Use: Turns retrieved chunks into bounded context text for prompts.
- Usage: Import ContextBuilder, and ContextBuilderConfig from
  rastin_ai.rag.context.builder.
- Duties: Defines ContextBuilder, and ContextBuilderConfig and related helper logic.
- Depends on: Project modules: rastin_ai.rag.models.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.rag.models import BuiltContext, RetrievedChunk

logger = logging.getLogger(__name__)


class ContextBuilderConfig(BaseModel):
    """Configuration for deterministic retrieved-context formatting."""

    max_tokens: int | None = Field(default=None, ge=1)
    max_chars: int | None = Field(default=None, ge=1)


class ContextBuilder:
    """Format retrieved chunks into source-aware context for an LLM caller."""

    def __init__(
        self,
        *,
        max_tokens: int | None = None,
        max_chars: int | None = None,
    ) -> None:
        self.config = ContextBuilderConfig(max_tokens=max_tokens, max_chars=max_chars)

    def build(self, retrieved_chunks: list[RetrievedChunk]) -> BuiltContext:
        with observed_span(
            name="rag.context.build",
            input={
                "retrieved_chunk_count": len(retrieved_chunks),
                "max_tokens": self.config.max_tokens,
                "max_chars": self.config.max_chars,
            },
        ) as observation:
            context = self._build(retrieved_chunks)
            safe_update_observation(
                observation,
                output={
                    "source_count": len(context.sources),
                    "context_chars": len(context.text),
                },
            )
            return context

    def _build(self, retrieved_chunks: list[RetrievedChunk]) -> BuiltContext:
        if not retrieved_chunks:
            return BuiltContext(text="", sources=())

        sections: list[str] = []
        sources: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        seen_equivalent_chunks: set[tuple[str, str | None, str]] = set()
        used_tokens = 0
        used_chars = 0
        source_number = 1

        for result in retrieved_chunks:
            chunk = result.chunk
            if chunk.id in seen_chunk_ids:
                continue
            equivalent_key = _equivalent_chunk_key(result)
            if equivalent_key in seen_equivalent_chunks:
                continue

            chunk_tokens = chunk.token_count or len(chunk.text.split())
            if (
                self.config.max_tokens is not None
                and used_tokens + chunk_tokens > self.config.max_tokens
            ):
                break

            seen_chunk_ids.add(chunk.id)
            source = self._source_record(source_number, result)
            section = self._format_source(source, chunk.text)
            section_chars = len(section) + (2 if sections else 0)
            if (
                self.config.max_chars is not None
                and used_chars + section_chars > self.config.max_chars
            ):
                break

            seen_equivalent_chunks.add(equivalent_key)
            used_tokens += chunk_tokens
            used_chars += section_chars
            sources.append(source)
            sections.append(section)
            source_number += 1

        context = BuiltContext(text="\n\n".join(sections), sources=tuple(sources))
        logger.info(
            "Context built",
            extra={"source_count": len(context.sources), "token_count": used_tokens},
        )
        return context

    def _source_record(
        self,
        source_number: int,
        result: RetrievedChunk,
    ) -> dict[str, Any]:
        chunk = result.chunk
        metadata = chunk.metadata
        return {
            "source_number": source_number,
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "source": metadata.get("source"),
            "filename": metadata.get("filename"),
            "file_type": metadata.get("file_type"),
            "location_type": metadata.get("location_type"),
            "source_location": metadata.get("source_location"),
            "page_number": metadata.get("page_number"),
            "line_start": metadata.get("line_start"),
            "line_end": metadata.get("line_end"),
            "paragraph_index": metadata.get("paragraph_index"),
            "table_index": metadata.get("table_index"),
            "row_start": metadata.get("row_start"),
            "row_end": metadata.get("row_end"),
            "columns": metadata.get("columns"),
            "sheet_name": metadata.get("sheet_name"),
            "json_path": metadata.get("json_path"),
            "chunk_index": chunk.chunk_index,
            "score": result.score,
        }

    @staticmethod
    def _format_source(source: dict[str, Any], text: str) -> str:
        lines = [f"[Source {source['source_number']}]"]
        if source.get("filename"):
            lines.append(f"File: {source['filename']}")

        if source.get("page_number") is not None:
            lines.append(f"Page: {source['page_number']}")
        elif source.get("source_location") is not None:
            lines.append(f"Location: {source['source_location']}")

        lines.extend(["", text])
        return "\n".join(lines)


def _equivalent_chunk_key(result: RetrievedChunk) -> tuple[str, str | None, str]:
    chunk = result.chunk
    normalized_text = " ".join(chunk.text.split()).casefold()
    location = chunk.metadata.get("source_location")
    return (
        chunk.document_id,
        str(location) if location is not None else None,
        normalized_text,
    )
