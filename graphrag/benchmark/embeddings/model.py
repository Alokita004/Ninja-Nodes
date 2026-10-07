"""Embedding model protocol and configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class EmbeddingModel(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    batch_size: int = 16
    max_retries: int = 3
    backoff_seconds: float = 0.5
    dimensions: int | None = None

    @classmethod
    def from_service_config(cls, config: dict) -> "EmbeddingConfig":
        model_name = config.get("model_name")
        if not isinstance(model_name, str) or not model_name:
            raise ValueError("embedding model_name must be configured")
        return cls(
            model_name=model_name,
            batch_size=int(config.get("batch_size", 16)),
            max_retries=int(config.get("max_retries", 3)),
            backoff_seconds=float(config.get("backoff_seconds", 0.5)),
            dimensions=int(config["dimensions"]) if config.get("dimensions") is not None else None,
        )