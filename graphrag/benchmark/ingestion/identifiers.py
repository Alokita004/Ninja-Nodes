"""Deterministic identifiers for ingestion artifacts."""

from __future__ import annotations

import hashlib


def document_vertex_id(doc_id: str) -> str:
    """Return the stable source identifier used by the Document vertex."""
    if not doc_id or not isinstance(doc_id, str):
        raise ValueError("doc_id must be a non-empty string")
    return doc_id


def content_hash(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("content must be a string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ingestion_record_id(doc_id: str, text: str) -> str:
    """Identify a source record version for checkpoint and audit purposes."""
    return f"{document_vertex_id(doc_id)}:{content_hash(text)}"