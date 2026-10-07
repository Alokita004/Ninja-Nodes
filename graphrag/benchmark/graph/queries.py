"""Deterministic query functions supported by the current graph schema."""

from __future__ import annotations

from typing import Any

from .client import TigerGraphClient
from .models import DocumentCount, DocumentRecord


def get_document_count(client: TigerGraphClient) -> DocumentCount:
    return DocumentCount(client.document_count())


def get_document(client: TigerGraphClient, document_id: str) -> DocumentRecord | None:
    row = client.document_by_id(document_id)
    if row is None:
        return None
    return DocumentRecord(
        document_id=str(row.get("doc_id") or row.get("v_id") or row.get("id")),
        title=str(row["title"]),
        url=str(row["url"]),
        wikidata_qid=str(row["wikidata_qid"]),
        wikipedia_pageid=int(row["wikipedia_pageid"]),
        approx_tokens=int(row["approx_tokens"]),
        text=str(row["text"]),
    )


def list_document_headers(client: TigerGraphClient, limit: int = 20) -> list[dict[str, Any]]:
    """Return bounded raw rows for inspection; no dynamic GSQL is generated."""
    return client.list_documents(limit)