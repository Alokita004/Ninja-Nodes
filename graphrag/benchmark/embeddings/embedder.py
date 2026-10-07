"""Retrying, cached batch embedding orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

from .cache import EmbeddingCache
from .model import EmbeddingConfig, EmbeddingModel


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    dimension: int
    cache_hits: int
    model_calls: int


class Embedder:
    def __init__(self, model: EmbeddingModel, config: EmbeddingConfig, cache: EmbeddingCache, *, sleep: Callable[[float], None] = time.sleep):
        if config.batch_size < 1 or config.max_retries < 1:
            raise ValueError("batch_size and max_retries must be positive")
        self.model = model
        self.config = config
        self.cache = cache
        self.sleep = sleep

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingResult:
        if any(not isinstance(text, str) for text in texts):
            raise TypeError("all texts must be strings")
        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []
        hits = 0
        for index, text in enumerate(texts):
            cached = self.cache.get(text, self.config.model_name)
            if cached is None:
                missing.append((index, text))
            else:
                vectors[index] = self._validate_vector(cached)
                hits += 1

        calls = 0
        for offset in range(0, len(missing), self.config.batch_size):
            batch = missing[offset : offset + self.config.batch_size]
            batch_vectors = self._embed_with_retry([text for _, text in batch])
            calls += 1
            for (index, text), vector in zip(batch, batch_vectors):
                checked = self._validate_vector(vector)
                vectors[index] = checked
                self.cache.put(text, self.config.model_name, checked)

        complete = [vector for vector in vectors if vector is not None]
        dimension = self._validate_dimensions(complete)
        return EmbeddingResult(complete, dimension, hits, calls)

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                vectors = self.model.embed_documents(texts)
                if len(vectors) != len(texts):
                    raise ValueError("embedding model returned an unexpected vector count")
                return vectors
            except Exception as error:
                last_error = error
                if attempt + 1 < self.config.max_retries:
                    self.sleep(self.config.backoff_seconds * (2**attempt))
        raise RuntimeError("embedding batch failed after retries") from last_error

    def _validate_vector(self, vector: list[float]) -> list[float]:
        if not isinstance(vector, list) or not vector or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector):
            raise ValueError("embedding vector must be a non-empty numeric list")
        if self.config.dimensions is not None and len(vector) != self.config.dimensions:
            raise ValueError(f"embedding dimension {len(vector)} does not match configured dimension {self.config.dimensions}")
        return [float(value) for value in vector]

    def _validate_dimensions(self, vectors: list[list[float]]) -> int:
        if not vectors:
            return self.config.dimensions or 0
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding vectors have inconsistent dimensions")
        return dimensions.pop()