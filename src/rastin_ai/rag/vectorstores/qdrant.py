"""File guide.

- Use: Stores and searches RAG chunks in Qdrant.
- Usage: Import QdrantVectorStore from rastin_ai.rag.vectorstores.qdrant.
- Duties: Defines QdrantVectorStore and related helper logic.
- Depends on: Project modules: rastin_ai.core.config,
  rastin_ai.rag.exceptions, rastin_ai.rag.models, and
  rastin_ai.rag.vectorstores.base.
"""

import logging
import uuid
from typing import Any

from rastin_ai.core.config import Settings, get_settings
from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.rag.exceptions import VectorStoreError
from rastin_ai.rag.models import Chunk, RetrievedChunk
from rastin_ai.rag.vectorstores.base import MetadataFilter

logger = logging.getLogger(__name__)

DEFAULT_QDRANT_COLLECTION_NAME = "rastin_ai_rag_chunks"

PAYLOAD_CHUNK_ID = "chunk_id"
PAYLOAD_DOCUMENT_ID = "document_id"
PAYLOAD_USER_ID = "user_id"
PAYLOAD_ORGANIZATION_ID = "organization_id"
PAYLOAD_PROJECT_ID = "project_id"
PAYLOAD_DOCUMENT_SCOPE = "document_scope"
PAYLOAD_SESSION_ID = "session_id"
PAYLOAD_UPLOADED_BY_USER_ID = "uploaded_by_user_id"
PAYLOAD_TEXT = "text"
PAYLOAD_CHUNK_INDEX = "chunk_index"
PAYLOAD_SOURCE = "source"
PAYLOAD_METADATA = "metadata"

TOP_LEVEL_FILTER_KEYS = frozenset(
    {
        PAYLOAD_DOCUMENT_ID,
        PAYLOAD_USER_ID,
        PAYLOAD_ORGANIZATION_ID,
        PAYLOAD_PROJECT_ID,
        PAYLOAD_DOCUMENT_SCOPE,
        PAYLOAD_SESSION_ID,
        PAYLOAD_UPLOADED_BY_USER_ID,
    }
)


class QdrantVectorStore:
    """Qdrant implementation of the Rastin-AI vector store interface."""

    def __init__(
        self,
        *,
        collection_name: str | None = None,
        dimension: int,
        distance: str = "Cosine",
        url: str | None = None,
        api_key: str | None = None,
        client: Any | None = None,
        settings: Settings | None = None,
        ensure_collection: bool = True,
        wait: bool | None = None,
    ) -> None:
        if dimension <= 0:
            msg = "Vector dimension must be greater than zero."
            raise VectorStoreError(msg)

        resolved_settings = settings
        if resolved_settings is None and (
            collection_name is None or (client is None and url is None)
        ):
            resolved_settings = get_settings()

        self.collection_name = collection_name or (
            resolved_settings.QDRANT_COLLECTION_NAME
            if resolved_settings is not None
            else DEFAULT_QDRANT_COLLECTION_NAME
        )
        if not self.collection_name:
            msg = "QDRANT_COLLECTION_NAME must not be empty."
            raise VectorStoreError(msg)

        self.dimension = dimension
        self.distance = distance
        self._url = url or (
            resolved_settings.QDRANT_URL if resolved_settings is not None else None
        )
        self._api_key = api_key or (
            resolved_settings.QDRANT_API_KEY if resolved_settings is not None else None
        )
        self._client = client or self._build_client()
        self._models: Any | None = None
        self._wait = wait

        if ensure_collection:
            self.ensure_collection()

    def collection_exists(self) -> bool:
        """Return whether the configured Qdrant collection exists."""
        try:
            return bool(self._client.collection_exists(self.collection_name))
        except Exception as exc:
            msg = f"Could not check Qdrant collection: {self.collection_name}"
            raise VectorStoreError(msg) from exc

    def ensure_collection(self) -> None:
        models = self._qdrant_models()

        try:
            exists = self.collection_exists()
            if not exists:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimension,
                        distance=self._distance_value(models),
                    ),
                )
                return

            collection = self._client.get_collection(self.collection_name)
        except Exception as exc:
            msg = f"Could not prepare Qdrant collection: {self.collection_name}"
            raise VectorStoreError(msg) from exc

        existing_size = self._extract_collection_vector_size(collection)
        if existing_size is not None and existing_size != self.dimension:
            msg = (
                "Qdrant collection vector dimension mismatch: "
                f"expected {self.dimension}, got {existing_size}."
            )
            raise VectorStoreError(msg)

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            msg = (
                "Cannot upsert chunks and embeddings with different lengths: "
                f"{len(chunks)} chunks, {len(embeddings)} embeddings."
            )
            raise VectorStoreError(msg)

        models = self._qdrant_models()
        points = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self._validate_embedding(embedding)
            points.append(
                models.PointStruct(
                    id=self._point_id(chunk.id),
                    vector=embedding,
                    payload=self._payload_from_chunk(chunk),
                )
            )

        if not points:
            return

        with observed_span(
            name="qdrant.upsert",
            input={
                "collection_name": self.collection_name,
                "point_count": len(points),
                "document_ids": sorted({chunk.document_id for chunk in chunks}),
            },
        ) as observation:
            try:
                self._client.upsert(
                    **self._upsert_kwargs(points),
                )
            except Exception as exc:
                msg = (
                    "Could not upsert chunks into Qdrant collection: "
                    f"{self.collection_name}"
                )
                raise VectorStoreError(msg) from exc
            safe_update_observation(
                observation,
                output={"status": "upserted", "point_count": len(points)},
            )

        logger.info(
            "Qdrant upsert completed",
            extra={"collection_name": self.collection_name, "point_count": len(points)},
        )

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: MetadataFilter | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            msg = "top_k must be greater than zero."
            raise VectorStoreError(msg)
        self._validate_embedding(query_embedding)

        if filters and PAYLOAD_DOCUMENT_ID in filters:
            _validate_document_scope_filters(filters, action="search")

        query_filter = self._build_filter(filters)
        with observed_span(
            name="qdrant.search",
            input={
                "collection_name": self.collection_name,
                "top_k": top_k,
                "has_filters": bool(filters),
                "document_id": _filter_document_id(filters),
                "score_threshold": score_threshold,
            },
            metadata={"document_id": _filter_document_id(filters)},
        ) as observation:
            try:
                points = self._search_points(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    query_filter=query_filter,
                    score_threshold=score_threshold,
                )
            except Exception as exc:
                msg = f"Could not search Qdrant collection: {self.collection_name}"
                raise VectorStoreError(msg) from exc
            safe_update_observation(
                observation,
                output={"result_count": len(points)},
            )

        results = [self._retrieved_chunk_from_point(point) for point in points]
        logger.info(
            "Retrieval completed",
            extra={
                "collection_name": self.collection_name,
                "result_count": len(results),
            },
        )
        return results

    def delete(
        self,
        *,
        chunk_ids: list[str] | None = None,
        document_id: str | None = None,
        user_id: str | None = None,
        filters: MetadataFilter | None = None,
    ) -> None:
        if not chunk_ids and document_id is None:
            msg = "delete requires chunk_ids, document_id, or both."
            raise VectorStoreError(msg)
        delete_filters = {**(filters or {})}
        if document_id is not None:
            delete_filters[PAYLOAD_DOCUMENT_ID] = document_id
        if user_id is not None:
            delete_filters[PAYLOAD_USER_ID] = user_id
        if document_id is not None:
            _validate_document_scope_filters(delete_filters, action="delete")

        models = self._qdrant_models()
        with observed_span(
            name="qdrant.delete",
            input={
                "collection_name": self.collection_name,
                "chunk_id_count": len(chunk_ids or ()),
                "document_id": document_id,
                "has_filters": bool(delete_filters),
            },
            metadata={"document_id": document_id},
        ) as observation:
            try:
                if chunk_ids:
                    self._client.delete(
                        collection_name=self.collection_name,
                        points_selector=models.PointIdsList(
                            points=[self._point_id(chunk_id) for chunk_id in chunk_ids],
                        ),
                    )
                if document_id is not None:
                    self._client.delete(
                        collection_name=self.collection_name,
                        points_selector=models.FilterSelector(
                            filter=self._build_filter(delete_filters)
                        ),
                    )
            except Exception as exc:
                msg = (
                    "Could not delete chunks from Qdrant collection: "
                    f"{self.collection_name}"
                )
                raise VectorStoreError(msg) from exc
            safe_update_observation(
                observation,
                output={"status": "deleted"},
            )

    def delete_collection(self) -> None:
        """Delete the configured Qdrant collection if it exists."""
        try:
            if self.collection_exists():
                self._client.delete_collection(collection_name=self.collection_name)
        except Exception as exc:
            msg = f"Could not delete Qdrant collection: {self.collection_name}"
            raise VectorStoreError(msg) from exc

    def _build_client(self) -> Any:
        if not self._url:
            msg = "QDRANT_URL must be set before creating a Qdrant vector store."
            raise VectorStoreError(msg)

        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            msg = "The qdrant-client package is required for Qdrant vector storage."
            raise VectorStoreError(msg) from exc

        return QdrantClient(url=self._url, api_key=self._api_key)

    def _qdrant_models(self) -> Any:
        if self._models is None:
            try:
                from qdrant_client import models
            except ImportError as exc:
                msg = "The qdrant-client package is required for Qdrant vector storage."
                raise VectorStoreError(msg) from exc
            self._models = models

        return self._models

    def _distance_value(self, models: Any) -> Any:
        normalized = self.distance.upper()
        try:
            return getattr(models.Distance, normalized)
        except AttributeError as exc:
            msg = f"Unsupported Qdrant distance metric: {self.distance}"
            raise VectorStoreError(msg) from exc

    def _search_points(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        query_filter: Any,
        score_threshold: float | None,
    ) -> list[Any]:
        if hasattr(self._client, "search"):
            return list(
                self._client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                )
            )

        response = self._client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
        )
        return list(getattr(response, "points", response))

    def _build_filter(self, filters: MetadataFilter | None) -> Any:
        if not filters:
            return None

        models = self._qdrant_models()
        conditions = []
        for key, value in filters.items():
            payload_key = (
                key if key in TOP_LEVEL_FILTER_KEYS else f"{PAYLOAD_METADATA}.{key}"
            )
            conditions.append(
                models.FieldCondition(
                    key=payload_key,
                    match=models.MatchValue(value=value),
                )
            )
        return models.Filter(must=conditions)

    def _retrieved_chunk_from_point(self, point: Any) -> RetrievedChunk:
        payload = dict(getattr(point, "payload", {}) or {})
        metadata = dict(payload.get(PAYLOAD_METADATA) or {})
        chunk_id = str(payload.get(PAYLOAD_CHUNK_ID) or point.id)
        document_id = str(
            payload.get(PAYLOAD_DOCUMENT_ID) or metadata.get(PAYLOAD_DOCUMENT_ID) or ""
        )
        text = str(payload.get(PAYLOAD_TEXT) or "")
        chunk_index = int(payload.get(PAYLOAD_CHUNK_INDEX) or 0)

        if not document_id or not text:
            msg = "Qdrant payload did not contain enough data to rebuild a chunk."
            raise VectorStoreError(msg)

        return RetrievedChunk(
            chunk=Chunk(
                id=chunk_id,
                document_id=document_id,
                text=text,
                chunk_index=chunk_index,
                metadata=metadata,
                token_count=int(metadata.get("token_count") or len(text.split())),
            ),
            score=float(getattr(point, "score", 0.0)),
        )

    def _payload_from_chunk(self, chunk: Chunk) -> dict[str, Any]:
        metadata = {**chunk.metadata, "token_count": chunk.token_count}
        return {
            PAYLOAD_CHUNK_ID: chunk.id,
            PAYLOAD_DOCUMENT_ID: chunk.document_id,
            PAYLOAD_USER_ID: metadata.get(PAYLOAD_USER_ID),
            PAYLOAD_ORGANIZATION_ID: metadata.get(PAYLOAD_ORGANIZATION_ID),
            PAYLOAD_PROJECT_ID: metadata.get(PAYLOAD_PROJECT_ID),
            PAYLOAD_DOCUMENT_SCOPE: metadata.get(PAYLOAD_DOCUMENT_SCOPE),
            PAYLOAD_SESSION_ID: metadata.get(PAYLOAD_SESSION_ID),
            PAYLOAD_UPLOADED_BY_USER_ID: metadata.get(PAYLOAD_UPLOADED_BY_USER_ID),
            PAYLOAD_TEXT: chunk.text,
            PAYLOAD_CHUNK_INDEX: chunk.chunk_index,
            PAYLOAD_SOURCE: metadata.get("source"),
            PAYLOAD_METADATA: metadata,
        }

    def _validate_embedding(self, embedding: list[float]) -> None:
        if len(embedding) != self.dimension:
            msg = (
                "Embedding dimension mismatch: "
                f"expected {self.dimension}, got {len(embedding)}."
            )
            raise VectorStoreError(msg)

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    @staticmethod
    def _extract_collection_vector_size(collection: Any) -> int | None:
        config = getattr(collection, "config", None)
        params = getattr(config, "params", None)
        vectors = getattr(params, "vectors", None) or getattr(
            params,
            "vectors_config",
            None,
        )

        if vectors is None:
            return None
        if isinstance(vectors, dict):
            first_vector = next(iter(vectors.values()), None)
            return getattr(first_vector, "size", None)
        return getattr(vectors, "size", None)

    def _upsert_kwargs(self, points: list[Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "collection_name": self.collection_name,
            "points": points,
        }
        if self._wait is not None:
            kwargs["wait"] = self._wait
        return kwargs


def _filter_document_id(filters: MetadataFilter | None) -> str | None:
    if not filters:
        return None
    value = filters.get(PAYLOAD_DOCUMENT_ID)
    return str(value) if value is not None else None


def _validate_document_scope_filters(
    filters: MetadataFilter,
    *,
    action: str,
) -> None:
    has_legacy_scope = PAYLOAD_USER_ID in filters
    has_project_scope = all(
        key in filters
        for key in (
            PAYLOAD_ORGANIZATION_ID,
            PAYLOAD_PROJECT_ID,
            PAYLOAD_DOCUMENT_SCOPE,
        )
    )
    if not has_legacy_scope and not has_project_scope:
        msg = (
            f"document-scoped {action} requires user_id or "
            "organization_id, project_id, and document_scope."
        )
        raise VectorStoreError(msg)
