"""Strict, streaming validation for the Phase 1 dataset contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DOCUMENT_FIELDS = frozenset(
    {"doc_id", "title", "url", "wikidata_qid", "wikipedia_pageid", "approx_tokens", "text"}
)
PUBLIC_FIELDS = frozenset(
    {
        "qid",
        "question",
        "qtype",
        "answer_named_in_question",
        "guess_baseline",
        "gold_doc_ids",
        "answer_verified",
        "answer",
    }
)
HIDDEN_FIELDS = frozenset({"qid", "question", "qtype"})


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    line: int | None
    message: str

    def __str__(self) -> str:
        location = f"{self.path}:{self.line}" if self.line is not None else self.path
        return f"{location}: {self.message}"


class DatasetValidationError(ValueError):
    """Raised when one or more dataset records violate the contract."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("Dataset validation failed:\n" + "\n".join(str(issue) for issue in issues))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_type(record: dict[str, Any], field: str, expected: type | str, path: str, line: int, issues: list[ValidationIssue]) -> None:
    value = record.get(field)
    valid = {
        str: isinstance(value, str),
        int: isinstance(value, int) and not isinstance(value, bool),
        bool: isinstance(value, bool),
        "number": _is_number(value),
        "string_list": isinstance(value, list) and all(isinstance(item, str) for item in value),
    }[expected]
    if not valid:
        expected_name = expected if isinstance(expected, str) else expected.__name__
        issues.append(ValidationIssue(path, line, f"field {field!r} must be {expected_name}"))


def _check_record_shape(record: Any, allowed: frozenset[str], path: str, line: int, issues: list[ValidationIssue]) -> bool:
    if not isinstance(record, dict):
        issues.append(ValidationIssue(path, line, "record must be a JSON object"))
        return False
    unknown = sorted(set(record) - allowed)
    if unknown:
        issues.append(ValidationIssue(path, line, f"unknown fields: {unknown}"))
    missing = sorted(allowed - set(record))
    if missing:
        issues.append(ValidationIssue(path, line, f"missing required fields: {missing}"))
    for field, value in record.items():
        if value is None:
            issues.append(ValidationIssue(path, line, f"field {field!r} must not be null"))
    return not unknown and not missing


def _validate_document(record: Any, path: str, line: int, issues: list[ValidationIssue]) -> None:
    if not _check_record_shape(record, DOCUMENT_FIELDS, path, line, issues):
        if not isinstance(record, dict):
            return
    for field in ("doc_id", "title", "url", "wikidata_qid", "text"):
        if field in record:
            _check_type(record, field, str, path, line, issues)
    for field in ("wikipedia_pageid", "approx_tokens"):
        if field in record:
            _check_type(record, field, int, path, line, issues)


def _validate_hidden(record: Any, path: str, line: int, issues: list[ValidationIssue]) -> None:
    if not _check_record_shape(record, HIDDEN_FIELDS, path, line, issues):
        if not isinstance(record, dict):
            return
    for field in HIDDEN_FIELDS:
        if field in record:
            _check_type(record, field, str, path, line, issues)


def _validate_public(record: Any, path: str, line: int, issues: list[ValidationIssue]) -> None:
    if not _check_record_shape(record, PUBLIC_FIELDS, path, line, issues):
        if not isinstance(record, dict):
            return
    for field in ("qid", "question", "qtype"):
        if field in record:
            _check_type(record, field, str, path, line, issues)
    for field in ("answer_named_in_question", "answer_verified"):
        if field in record:
            _check_type(record, field, bool, path, line, issues)
    if "guess_baseline" in record:
        _check_type(record, "guess_baseline", "number", path, line, issues)
    for field in ("gold_doc_ids", "answer"):
        if field in record:
            _check_type(record, field, "string_list", path, line, issues)


def _iter_jsonl(path: Path) -> Iterable[tuple[int, Any | None, str | None]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line, raw in enumerate(handle, 1):
            try:
                yield line, json.loads(raw), None
            except json.JSONDecodeError as error:
                yield line, None, error.msg


def validate_jsonl(path: str | Path, dataset_name: str, *, corpus_ids: set[str] | None = None) -> int:
    """Validate one dataset stream and return its valid record count."""
    file_path = Path(path)
    issues: list[ValidationIssue] = []
    identifiers: set[str] = set()
    document_hashes: set[str] = set()
    record_count = 0
    id_field = "doc_id" if dataset_name == "corpus" else "qid"
    validator = {"corpus": _validate_document, "eval_public": _validate_public, "eval_hidden": _validate_hidden}.get(dataset_name)
    if validator is None:
        raise ValueError(f"Unknown dataset name: {dataset_name}")

    for line, record, parse_error in _iter_jsonl(file_path):
        if parse_error is not None:
            issues.append(ValidationIssue(str(file_path), line, f"malformed JSON: {parse_error}"))
            continue
        record_count += 1
        validator(record, str(file_path), line, issues)
        if not isinstance(record, dict):
            continue
        identifier = record.get(id_field)
        if isinstance(identifier, str):
            if identifier in identifiers:
                issues.append(ValidationIssue(str(file_path), line, f"duplicate {id_field}: {identifier}"))
            identifiers.add(identifier)
        if dataset_name == "corpus":
            digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            if digest in document_hashes:
                issues.append(ValidationIssue(str(file_path), line, "duplicate complete document"))
            document_hashes.add(digest)
        if dataset_name == "eval_public" and corpus_ids is not None and isinstance(record.get("gold_doc_ids"), list):
            for document_id in record["gold_doc_ids"]:
                if isinstance(document_id, str) and document_id not in corpus_ids:
                    issues.append(ValidationIssue(str(file_path), line, f"gold_doc_ids references unknown document: {document_id}"))

    if issues:
        raise DatasetValidationError(issues)
    return record_count


def _collect_corpus_ids(path: Path) -> set[str]:
    identifiers: set[str] = set()
    for _, record, error in _iter_jsonl(path):
        if error is None and isinstance(record, dict) and isinstance(record.get("doc_id"), str):
            identifiers.add(record["doc_id"])
    return identifiers


def validate_datasets(root: str | Path) -> dict[str, int]:
    """Validate all three datasets, raising instead of repairing invalid input."""
    root_path = Path(root)
    corpus_path = root_path / "corpus.jsonl"
    counts = {"corpus": validate_jsonl(corpus_path, "corpus")}
    corpus_ids = _collect_corpus_ids(corpus_path)
    counts["eval_public"] = validate_jsonl(root_path / "eval_public.jsonl", "eval_public", corpus_ids=corpus_ids)
    counts["eval_hidden"] = validate_jsonl(root_path / "eval_hidden.jsonl", "eval_hidden")
    return counts