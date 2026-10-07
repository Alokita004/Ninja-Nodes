from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.ingestion.checkpoint import CheckpointStore
from benchmark.ingestion.identifiers import content_hash, document_vertex_id
from benchmark.ingestion.loader import ingest_documents
from benchmark.ingestion.parser import iter_documents
from benchmark.ingestion.validator import validate_document_record


def _record(doc_id: str = "d1") -> dict:
    return {"doc_id": doc_id, "title": "Title", "url": "https://example.test", "wikidata_qid": "Q1", "wikipedia_pageid": 1, "approx_tokens": 2, "text": "body"}


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[tuple[str, dict]]]] = []

    def upsertVertices(self, vertex_type: str, vertices: list[tuple[str, dict]]) -> int:
        self.calls.append((vertex_type, vertices))
        return len(vertices)


def test_parser_streams_and_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text(json.dumps(_record()) + "\n{bad}\n", encoding="utf-8")
    records = iter_documents(path)
    assert next(records)[1]["doc_id"] == "d1"
    with pytest.raises(ValueError, match="malformed JSON"):
        next(records)


def test_identifiers_are_deterministic() -> None:
    assert document_vertex_id("d1") == document_vertex_id("d1")
    assert content_hash("body") == content_hash("body")
    assert content_hash("body") != content_hash("other")


def test_checkpoint_is_atomic_and_source_bound(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoint.json")
    checkpoint = store.load("corpus.jsonl")
    checkpoint.next_line = 4
    store.save(checkpoint)
    assert store.load("corpus.jsonl").next_line == 4
    with pytest.raises(ValueError, match="source_path"):
        store.load("other.jsonl")


def test_dry_run_is_resumable_and_does_not_write_graph(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("\n".join(json.dumps(_record(f"d{i}")) for i in range(1, 4)) + "\n", encoding="utf-8")
    result = ingest_documents(corpus, checkpoint_path=tmp_path / "checkpoint.json", batch_size=2, dry_run=True)
    assert result == result.__class__(processed=3, loaded=3, next_line=4, dry_run=True)


def test_loader_batches_and_retries(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("\n".join(json.dumps(_record(f"d{i}")) for i in range(1, 4)) + "\n", encoding="utf-8")
    connection = FakeConnection()
    result = ingest_documents(corpus, connection, checkpoint_path=tmp_path / "checkpoint.json", batch_size=2)
    assert result.loaded == 3
    assert [len(call[1]) for call in connection.calls] == [2, 1]
    assert connection.calls[0][0] == "Document"


def test_validator_rejects_unknown_fields() -> None:
    invalid = _record()
    invalid["entities"] = []
    with pytest.raises(ValueError, match="unknown"):
        validate_document_record(invalid)