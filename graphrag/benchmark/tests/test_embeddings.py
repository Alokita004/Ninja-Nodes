from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.embeddings.cache import EmbeddingCache
from benchmark.embeddings.chunker import chunk_document
from benchmark.embeddings.embedder import Embedder
from benchmark.embeddings.model import EmbeddingConfig


class FakeModel:
    def __init__(self, dimension: int = 3, failures: int = 0) -> None:
        self.dimension = dimension
        self.failures = failures
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise RuntimeError("transient failure")
        return [[float(len(text) + index)] * self.dimension for index, text in enumerate(texts)]


def test_chunks_are_deterministic_and_bounded() -> None:
    first = chunk_document("d1", "abcdefghij", chunk_size=4, chunk_overlap=1)
    second = chunk_document("d1", "abcdefghij", chunk_size=4, chunk_overlap=1)
    assert first == second
    assert all(1 <= len(chunk.text) <= 4 for chunk in first)


def test_chunk_config_validation() -> None:
    with pytest.raises(ValueError):
        chunk_document("d1", "text", chunk_size=4, chunk_overlap=4)


def test_cache_avoids_duplicate_model_calls(tmp_path: Path) -> None:
    model = FakeModel()
    cache = EmbeddingCache(tmp_path / "embeddings.sqlite")
    config = EmbeddingConfig(model_name="fake-v1", batch_size=2)
    embedder = Embedder(model, config, cache)
    first = embedder.embed_documents(["one", "two"])
    second = embedder.embed_documents(["one", "two"])
    assert first.dimension == 3
    assert first.model_calls == 1
    assert second.cache_hits == 2
    assert second.model_calls == 0
    assert model.calls == 1


def test_embedding_retries_and_validates_dimension(tmp_path: Path) -> None:
    model = FakeModel(dimension=2, failures=1)
    cache = EmbeddingCache(tmp_path / "embeddings.sqlite")
    sleeps: list[float] = []
    embedder = Embedder(model, EmbeddingConfig(model_name="fake-v1", max_retries=2), cache, sleep=sleeps.append)
    result = embedder.embed_documents(["one"])
    assert result.dimension == 2
    assert model.calls == 2
    assert sleeps == [0.5]


def test_config_does_not_infer_or_require_dimension() -> None:
    config = EmbeddingConfig.from_service_config({"model_name": "configured-model"})
    assert config.dimensions is None