"""File guide.

- Use: Contains unit tests for embeddings behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.core.config,
  rastin_ai.rag.embeddings.openai, and rastin_ai.rag.exceptions.
"""

from types import SimpleNamespace

import pytest

from rastin_ai.core.config import Settings
from rastin_ai.rag.embeddings.openai import OpenAIEmbeddingProvider
from rastin_ai.rag.exceptions import EmbeddingError


class FakeEmbeddingsAPI:
    def __init__(self, batches: list[list[list[float]]]) -> None:
        self.batches = batches
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, input: list[str]) -> object:
        self.calls.append({"model": model, "input": input})
        embeddings = self.batches.pop(0)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=embedding)
                for index, embedding in enumerate(embeddings)
            ]
        )


class FakeOpenAIClient:
    def __init__(self, batches: list[list[list[float]]]) -> None:
        self.embeddings = FakeEmbeddingsAPI(batches)


def test_openai_embedding_provider_embeds_documents_in_batches() -> None:
    client = FakeOpenAIClient(
        batches=[
            [[0.1, 0.2], [0.3, 0.4]],
            [[0.5, 0.6]],
        ]
    )
    provider = OpenAIEmbeddingProvider(
        model="fake-model",
        dimension=2,
        batch_size=2,
        client=client,
    )

    embeddings = provider.embed_documents(["a", "b", "c"])

    assert embeddings == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    assert client.embeddings.calls == [
        {"model": "fake-model", "input": ["a", "b"]},
        {"model": "fake-model", "input": ["c"]},
    ]


def test_openai_embedding_provider_embeds_query() -> None:
    provider = OpenAIEmbeddingProvider(
        model="fake-model",
        dimension=2,
        client=FakeOpenAIClient([[[0.7, 0.8]]]),
    )

    assert provider.embed_query("question") == [0.7, 0.8]


def test_openai_embedding_provider_rejects_empty_query() -> None:
    provider = OpenAIEmbeddingProvider(
        model="fake-model",
        dimension=2,
        client=FakeOpenAIClient([]),
    )

    with pytest.raises(EmbeddingError, match="must not be empty"):
        provider.embed_query(" ")


def test_openai_embedding_provider_validates_response_count() -> None:
    provider = OpenAIEmbeddingProvider(
        model="fake-model",
        dimension=2,
        client=FakeOpenAIClient([[[0.1, 0.2]]]),
    )

    with pytest.raises(EmbeddingError, match="response count"):
        provider.embed_documents(["a", "b"])


def test_openai_embedding_provider_validates_dimension() -> None:
    provider = OpenAIEmbeddingProvider(
        model="fake-model",
        dimension=2,
        client=FakeOpenAIClient([[[0.1]]]),
    )

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        provider.embed_documents(["a"])


def test_openai_embedding_provider_requires_api_key_without_injected_client() -> None:
    settings = Settings(DEBUG=False, OPENAI_API_KEY=None)

    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider(settings=settings)
