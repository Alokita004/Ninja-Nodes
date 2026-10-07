"""Persistent embedding cache keyed by content hash and model identity."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from benchmark.ingestion.identifiers import content_hash


class EmbeddingCache:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (content_hash TEXT NOT NULL, model_name TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY (content_hash, model_name))"
            )

    def get(self, text: str, model_name: str) -> list[float] | None:
        key = content_hash(text)
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT vector FROM embeddings WHERE content_hash = ? AND model_name = ?", (key, model_name)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, text: str, model_name: str, vector: list[float]) -> None:
        key = content_hash(text)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO embeddings(content_hash, model_name, vector) VALUES (?, ?, ?)",
                (key, model_name, json.dumps(vector)),
            )

    def count(self) -> int:
        with sqlite3.connect(self.path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])