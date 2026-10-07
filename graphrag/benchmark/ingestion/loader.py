"""Batch, retrying, idempotent Document vertex loader."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .checkpoint import Checkpoint, CheckpointStore
from .chunker import preserve_document_text
from .identifiers import document_vertex_id
from .parser import iter_documents


@dataclass(frozen=True)
class IngestionResult:
    processed: int
    loaded: int
    next_line: int
    dry_run: bool


def document_attributes(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": record["title"],
        "url": record["url"],
        "wikidata_qid": record["wikidata_qid"],
        "wikipedia_pageid": record["wikipedia_pageid"],
        "approx_tokens": record["approx_tokens"],
        "text": preserve_document_text(record["text"]),
    }


def ingest_documents(
    source_path: str | Path,
    connection: Any | None = None,
    *,
    checkpoint_path: str | Path = "ingestion.checkpoint.json",
    batch_size: int = 25,
    max_retries: int = 3,
    backoff_seconds: float = 0.5,
    dry_run: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> IngestionResult:
    if batch_size < 1 or max_retries < 1:
        raise ValueError("batch_size and max_retries must be positive")
    if not dry_run and connection is None:
        raise ValueError("connection is required unless dry_run is enabled")

    source = str(Path(source_path))
    store = CheckpointStore(checkpoint_path)
    checkpoint = store.load(source)
    batch: list[tuple[str, dict[str, Any]]] = []
    processed = checkpoint.processed
    loaded = checkpoint.loaded
    next_line = checkpoint.next_line

    def flush(items: list[tuple[str, dict[str, Any]]]) -> int:
        if dry_run:
            return len(items)
        vertices = [(vertex_id, document_attributes(record)) for vertex_id, record in items]
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return int(connection.upsertVertices("Document", vertices))
            except Exception as error:  # retry only at the batch boundary
                last_error = error
                if attempt + 1 < max_retries:
                    sleep(backoff_seconds * (2**attempt))
        raise RuntimeError("Document batch load failed after retries") from last_error

    for line_number, record in iter_documents(source_path, start_line=checkpoint.next_line):
        batch.append((document_vertex_id(record["doc_id"]), record))
        processed += 1
        next_line = line_number + 1
        if len(batch) >= batch_size:
            loaded += flush(batch)
            batch.clear()
            checkpoint = Checkpoint(source, next_line, processed, loaded, 0)
            store.save(checkpoint)

    if batch:
        loaded += flush(batch)
    checkpoint = Checkpoint(source, next_line, processed, loaded, 0)
    store.save(checkpoint)
    return IngestionResult(processed, loaded, next_line, dry_run)