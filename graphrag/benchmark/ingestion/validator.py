"""Strict validation for corpus records before graph writes."""

from __future__ import annotations

from typing import Any

from benchmark.dataset.validator import DOCUMENT_FIELDS


def validate_document_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("document record must be a JSON object")
    if set(record) != DOCUMENT_FIELDS:
        missing = sorted(DOCUMENT_FIELDS - set(record))
        unknown = sorted(set(record) - DOCUMENT_FIELDS)
        raise ValueError(f"invalid document fields; missing={missing}, unknown={unknown}")
    if any(value is None for value in record.values()):
        raise ValueError("document fields must not be null")
    if not isinstance(record["doc_id"], str) or not record["doc_id"]:
        raise ValueError("doc_id must be a non-empty string")
    for field in ("title", "url", "wikidata_qid", "text"):
        if not isinstance(record[field], str):
            raise ValueError(f"{field} must be a string")
    for field in ("wikipedia_pageid", "approx_tokens"):
        if not isinstance(record[field], int) or isinstance(record[field], bool):
            raise ValueError(f"{field} must be an integer")
    return record