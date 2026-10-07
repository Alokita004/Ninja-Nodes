"""Deterministic character-based document chunking for Phase 6."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    ordinal: int
    text: str


def chunk_document(document_id: str, text: str, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    if not document_id or not isinstance(document_id, str):
        raise ValueError("document_id must be a non-empty string")
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if chunk_size < 1 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be between zero and chunk_size - 1")
    chunks: list[Chunk] = []
    step = chunk_size - chunk_overlap
    for ordinal, start in enumerate(range(0, len(text), step)):
        piece = text[start : start + chunk_size]
        if not piece:
            break
        digest = hashlib.sha256(f"{document_id}:{ordinal}:{piece}".encode("utf-8")).hexdigest()[:16]
        chunks.append(Chunk(f"{document_id}_chunk_{ordinal}_{digest}", document_id, ordinal, piece))
        if start + chunk_size >= len(text):
            break
    return chunks