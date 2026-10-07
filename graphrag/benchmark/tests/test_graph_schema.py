from __future__ import annotations

from pathlib import Path


def test_document_schema_is_source_faithful() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = (root / "benchmark" / "graph" / "document_schema.gsql").read_text(encoding="utf-8")
    for field in ("doc_id", "title", "url", "wikidata_qid", "wikipedia_pageid", "approx_tokens", "text"):
        assert field in schema
    assert "CREATE VERTEX Document" in schema
    assert "CREATE EDGE" not in schema
    assert "CREATE VERTEX Entity" not in schema
    assert "CREATE VERTEX Chunk" not in schema


def test_schema_script_is_not_an_execution_or_dynamic_query() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = (root / "benchmark" / "graph" / "document_schema.gsql").read_text(encoding="utf-8")
    assert "INTERPRET QUERY" not in schema
    assert "RUN QUERY" not in schema
    assert "DROP GRAPH" not in schema