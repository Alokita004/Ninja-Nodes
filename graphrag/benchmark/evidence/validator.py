"""Validation and deterministic identity helpers for evidence."""

from __future__ import annotations

import hashlib
import json
import math

from .models import Evidence, EvidenceSet


class EvidenceValidationError(ValueError):
    pass


def evidence_id(document_id: str, text: str, retrieval_method: str, chunk_id: str | None = None) -> str:
    payload = json.dumps([document_id, text, retrieval_method, chunk_id], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_evidence(item: Evidence) -> Evidence:
    if not isinstance(item, Evidence):
        raise EvidenceValidationError("evidence must be an Evidence instance")
    for field_name in ("evidence_id", "document_id", "text", "retrieval_method"):
        value = getattr(item, field_name)
        if not isinstance(value, str) or not value.strip():
            raise EvidenceValidationError(f"{field_name} must be a non-empty string")
    if item.chunk_id is not None and (not isinstance(item.chunk_id, str) or not item.chunk_id.strip()):
        raise EvidenceValidationError("chunk_id must be a non-empty string when present")
    if item.relevance_score is not None and (
        not isinstance(item.relevance_score, (int, float))
        or isinstance(item.relevance_score, bool)
        or not math.isfinite(float(item.relevance_score))
    ):
        raise EvidenceValidationError("relevance_score must be finite numeric data")
    if item.graph_path is not None and (
        not isinstance(item.graph_path, list) or not all(isinstance(node, str) and node for node in item.graph_path)
    ):
        raise EvidenceValidationError("graph_path must be a list of non-empty strings")
    if not isinstance(item.metadata, dict):
        raise EvidenceValidationError("metadata must be an object")
    return item


def validate_evidence_set(items: EvidenceSet) -> EvidenceSet:
    if not isinstance(items, EvidenceSet):
        raise EvidenceValidationError("evidence set must be an EvidenceSet instance")
    seen: set[str] = set()
    for item in items.items:
        validate_evidence(item)
        if item.evidence_id in seen:
            raise EvidenceValidationError(f"duplicate evidence_id: {item.evidence_id}")
        seen.add(item.evidence_id)
    return items