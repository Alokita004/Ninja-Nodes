from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.graph.client import GraphClientConfig, GraphQueryError, TigerGraphClient
from benchmark.graph.models import DocumentCount
from benchmark.graph.queries import get_document, get_document_count, list_document_headers


class FakeRows:
    def __init__(self, rows: list[dict]):
        self.index = list(range(len(rows)))
        self._rows = rows
        self.iloc = self

    def __getitem__(self, index: int):
        return FakeRow(self._rows[index])


class FakeRow:
    def __init__(self, row: dict):
        self.row = row

    def to_dict(self) -> dict:
        return self.row


class FakeConnection:
    def __init__(self):
        self.document = {"doc_id": "d1", "title": "T", "url": "u", "wikidata_qid": "Q1", "wikipedia_pageid": 1, "approx_tokens": 2, "text": "body"}

    def getVertexCount(self, *_args, **_kwargs):
        return 1

    def getVertexDataFrameById(self, *_args, **_kwargs):
        return FakeRows([self.document])

    def getVertices(self, *_args, **_kwargs):
        return [self.document]


def test_document_queries_are_typed_and_bounded() -> None:
    client = TigerGraphClient(FakeConnection(), GraphClientConfig(timeout_seconds=5))
    assert get_document_count(client) == DocumentCount(1)
    assert get_document(client, "d1").document_id == "d1"
    assert list_document_headers(client, 2)[0]["doc_id"] == "d1"


def test_query_input_and_errors_are_explicit() -> None:
    client = TigerGraphClient(FakeConnection())
    with pytest.raises(ValueError):
        client.document_by_id("")
    with pytest.raises(ValueError):
        client.list_documents(0)

    class Broken:
        def getVertexCount(self, *_args, **_kwargs):
            raise RuntimeError("unavailable")

    with pytest.raises(GraphQueryError, match="document_count failed"):
        TigerGraphClient(Broken()).document_count()