"""Streaming forensic profiler for the GraphMind JSONL datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DATASET_NAMES = ("corpus", "eval_public", "eval_hidden")
ID_FIELDS = {"corpus": "doc_id", "eval_public": "qid", "eval_hidden": "qid"}


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _percentiles(values: list[int | float]) -> dict[str, int | float]:
    if not values:
        return {"min": 0, "p25": 0, "median": 0, "p75": 0, "max": 0}
    ordered = sorted(values)

    def percentile(fraction: float) -> int | float:
        position = (len(ordered) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {
        "min": ordered[0],
        "p25": percentile(0.25),
        "median": percentile(0.5),
        "p75": percentile(0.75),
        "max": ordered[-1],
    }


def _iter_jsonl(path: Path) -> Iterable[tuple[int, Any | None, str | None]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                yield line_number, json.loads(line), None
            except json.JSONDecodeError as error:
                yield line_number, None, error.msg


def _field_summary(field_counts: dict[str, Counter[str]], null_counts: Counter[str], record_count: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in sorted(field_counts):
        observed = field_counts[field]
        present = sum(observed.values())
        result[field] = {
            "present": present,
            "missing": record_count - present,
            "required_by_observation": present == record_count,
            "null": null_counts[field],
            "observed_types": dict(sorted(observed.items())),
        }
    return result


def profile_file(path: str | Path, dataset_name: str, *, include_public_answers: bool = False) -> dict[str, Any]:
    """Profile one JSONL file using constant-size record processing."""
    file_path = Path(path)
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    null_counts: Counter[str] = Counter()
    ids: set[str] = set()
    duplicate_ids = 0
    duplicate_documents = 0
    document_hashes: set[str] = set()
    malformed: list[dict[str, Any]] = []
    records = 0
    lengths: list[int] = []
    token_lengths: list[int] = []
    question_types: Counter[str] = Counter()
    answer_shapes: Counter[str] = Counter()
    public_references: set[str] = set()
    public_reference_count = 0
    samples: list[dict[str, Any]] = []

    for line_number, record, error in _iter_jsonl(file_path):
        if error is not None:
            malformed.append({"line": line_number, "error": error})
            continue
        records += 1
        if not isinstance(record, dict):
            malformed.append({"line": line_number, "error": "record is not an object"})
            continue
        for field, value in record.items():
            field_counts[field][_type_name(value)] += 1
            if value is None:
                null_counts[field] += 1

        id_field = ID_FIELDS[dataset_name]
        identifier = record.get(id_field)
        if isinstance(identifier, str):
            if identifier in ids:
                duplicate_ids += 1
            ids.add(identifier)

        if dataset_name == "corpus":
            text = record.get("text")
            if isinstance(text, str):
                lengths.append(len(text))
                token_lengths.append(len(text.split()))
            digest = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            if digest in document_hashes:
                duplicate_documents += 1
            document_hashes.add(digest)
        else:
            question = record.get("question")
            if isinstance(question, str):
                lengths.append(len(question))
                token_lengths.append(len(question.split()))
            if isinstance(record.get("qtype"), str):
                question_types[record["qtype"]] += 1
            if dataset_name == "eval_public":
                answer = record.get("answer")
                answer_shapes[_type_name(answer)] += 1
                references = record.get("gold_doc_ids")
                if isinstance(references, list):
                    public_reference_count += len(references)
                    public_references.update(item for item in references if isinstance(item, str))

        if len(samples) < 2 and (dataset_name != "eval_hidden" or not record.get("answer")):
            samples.append(record if dataset_name != "eval_hidden" else {"fields": sorted(record)})

    result: dict[str, Any] = {
        "path": str(file_path),
        "dataset": dataset_name,
        "record_count": records,
        "malformed_records": malformed,
        "field_summary": _field_summary(field_counts, null_counts, records),
        "duplicate_id_count": duplicate_ids,
        "null_field_count": dict(sorted(null_counts.items())),
        "length_unit": "characters",
        "length_distribution": _percentiles(lengths),
        "whitespace_token_distribution": _percentiles(token_lengths),
        "representative_records": samples,
    }
    if dataset_name == "corpus":
        result["duplicate_document_count"] = duplicate_documents
        result["explicit_entity_or_relationship_fields"] = sorted(
            field for field in field_counts if field.lower() in {"entity", "entities", "relationship", "relationships", "edges"}
        )
    else:
        result["question_type_counts"] = dict(sorted(question_types.items()))
        if dataset_name == "eval_public":
            result["answer_shape_counts"] = dict(sorted(answer_shapes.items()))
            result["gold_document_reference_count"] = public_reference_count
            result["unique_gold_document_reference_count"] = len(public_references)
            if not include_public_answers:
                result["representative_records"] = [
                    {key: value for key, value in record.items() if key not in {"answer", "gold_doc_ids"}}
                    for record in samples
                ]
    return result


def build_profile(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    corpus = profile_file(root_path / "corpus.jsonl", "corpus")
    public = profile_file(root_path / "eval_public.jsonl", "eval_public", include_public_answers=True)
    hidden = profile_file(root_path / "eval_hidden.jsonl", "eval_hidden")
    corpus_ids = set()
    for _, record, error in _iter_jsonl(root_path / "corpus.jsonl"):
        if error is None and isinstance(record, dict) and isinstance(record.get("doc_id"), str):
            corpus_ids.add(record["doc_id"])
    public_refs = set()
    for _, record, error in _iter_jsonl(root_path / "eval_public.jsonl"):
        if error is None and isinstance(record, dict):
            public_refs.update(item for item in record.get("gold_doc_ids", []) if isinstance(item, str))
    public["gold_document_references_missing_from_corpus"] = len(public_refs - corpus_ids)
    public["questions_with_gold_document_references"] = public["record_count"] - sum(
        1 for _, record, error in _iter_jsonl(root_path / "eval_public.jsonl")
        if error is None and isinstance(record, dict) and not record.get("gold_doc_ids")
    )
    hidden["hidden_values_redacted"] = True
    return {"profile_version": 1, "datasets": {"corpus": corpus, "eval_public": public, "eval_hidden": hidden}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile GraphMind JSONL datasets")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    profile = build_profile(args.root)
    payload = json.dumps(profile, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()