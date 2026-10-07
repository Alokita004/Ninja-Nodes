"""
PHASE 0: Dataset Intelligence & Forensic Inspection
====================================================
Streams and profiles the GraphMind hackathon dataset files without
loading the entire corpus into memory.

Outputs:
    benchmark/dataset/dataset_profile.json  — machine-readable profile

Usage:
    python benchmark/dataset/profile.py
    python benchmark/dataset/profile.py --corpus ./corpus.jsonl \
        --eval_public ./eval_public.jsonl \
        --eval_hidden ./eval_hidden.jsonl \
        --output benchmark/dataset/dataset_profile.json
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import statistics
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("graphmind.dataset.profile")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stream_jsonl(path: Path) -> Any:
    """Yield parsed JSON objects from a JSONL file, one line at a time.

    Args:
        path: Path to the .jsonl file.

    Yields:
        Parsed JSON object for each non-empty line.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: Logged as a warning; the line is skipped.
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open(encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Malformed JSON on line %d of %s: %s", lineno, path.name, exc)


def _field_stats(counter: collections.Counter, total: int) -> dict[str, Any]:
    """Return presence/null frequency stats for a field counter."""
    present = counter.get("__present__", 0)
    null_count = counter.get("__null__", 0)
    missing_count = total - present
    return {
        "present": present,
        "null": null_count,
        "missing_field": missing_count,
        "frequency": round(present / total, 4) if total else 0.0,
    }


def _distribution_stats(values: list[int | float]) -> dict[str, Any]:
    """Return min/max/mean/median/p95 statistics for a numeric list."""
    if not values:
        return {"count": 0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    p95_idx = min(int(0.95 * n), n - 1)
    return {
        "count": n,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": sorted_vals[p95_idx],
        "stdev": round(statistics.stdev(values), 2) if n > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Corpus Profiler
# ---------------------------------------------------------------------------

def profile_corpus(corpus_path: Path) -> dict[str, Any]:
    """Stream and profile corpus.jsonl.

    Args:
        corpus_path: Path to corpus.jsonl.

    Returns:
        Dictionary with corpus statistics.
    """
    logger.info("Profiling corpus: %s", corpus_path)

    total_docs: int = 0
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()

    # Field tracking
    field_counters: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    expected_fields = ["doc_id", "title", "url", "wikidata_qid", "wikipedia_pageid", "approx_tokens", "text"]

    # Distribution lists
    text_lengths: list[int] = []
    approx_tokens_list: list[int] = []
    title_lengths: list[int] = []

    # Content analysis
    domains: collections.Counter = collections.Counter()

    for doc in _stream_jsonl(corpus_path):
        total_docs += 1

        # Track field presence/nulls
        for field in expected_fields:
            if field in doc:
                field_counters[field]["__present__"] += 1
                if doc[field] is None:
                    field_counters[field]["__null__"] += 1
            else:
                field_counters[field]["__missing__"] += 1

        # Duplicate ID tracking
        doc_id = doc.get("doc_id") or doc.get("wikidata_qid", "")
        if doc_id:
            if doc_id in seen_ids:
                duplicate_ids.append(doc_id)
            else:
                seen_ids.add(doc_id)

        # Text statistics
        text = doc.get("text", "") or ""
        text_lengths.append(len(text))

        # Token estimates
        approx_tokens = doc.get("approx_tokens")
        if isinstance(approx_tokens, (int, float)):
            approx_tokens_list.append(int(approx_tokens))

        # Title stats
        title = doc.get("title", "") or ""
        title_lengths.append(len(title))

        # URL domain extraction
        url = doc.get("url", "") or ""
        if "wikipedia.org" in url:
            domains["wikipedia.org"] += 1
        elif url:
            domain = url.split("/")[2] if len(url.split("/")) > 2 else "unknown"
            domains[domain] += 1

    logger.info("Corpus profiled: %d documents, %d duplicates", total_docs, len(duplicate_ids))

    # Build field stats
    fields_analysis: dict[str, Any] = {}
    for field in expected_fields:
        fields_analysis[field] = _field_stats(field_counters[field], total_docs)

    return {
        "total_documents": total_docs,
        "unique_ids": len(seen_ids),
        "duplicate_ids": duplicate_ids[:20],  # cap list for readability
        "duplicate_id_count": len(duplicate_ids),
        "fields": fields_analysis,
        "text_length_distribution": _distribution_stats(text_lengths),
        "approx_tokens_distribution": _distribution_stats(approx_tokens_list),
        "title_length_distribution": _distribution_stats(title_lengths),
        "top_domains": dict(domains.most_common(10)),
    }


# ---------------------------------------------------------------------------
# Public Evaluation Profiler
# ---------------------------------------------------------------------------

def profile_eval_public(eval_path: Path) -> dict[str, Any]:
    """Stream and profile eval_public.jsonl.

    Args:
        eval_path: Path to eval_public.jsonl.

    Returns:
        Dictionary with evaluation question statistics.
        NOTE: Ground truth answers are included only in aggregate stats, not exposed raw.
    """
    logger.info("Profiling public eval: %s", eval_path)

    total_questions: int = 0
    question_ids: list[str] = []
    qtypes: collections.Counter = collections.Counter()
    question_lengths: list[int] = []
    answer_named_in_question_count: int = 0
    answer_verified_count: int = 0
    answer_lengths: list[int] = []  # length of answer list per question
    multi_doc_count: int = 0  # questions requiring multiple docs
    gold_doc_counts: list[int] = []

    expected_fields = ["qid", "question", "qtype", "answer_named_in_question",
                       "guess_baseline", "gold_doc_ids", "answer_verified", "answer"]
    field_counters: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for q in _stream_jsonl(eval_path):
        total_questions += 1

        qid = q.get("qid", "")
        question_ids.append(qid)

        qtype = q.get("qtype", "unknown")
        qtypes[qtype] += 1

        question_text = q.get("question", "") or ""
        question_lengths.append(len(question_text))

        if q.get("answer_named_in_question"):
            answer_named_in_question_count += 1

        if q.get("answer_verified"):
            answer_verified_count += 1

        # Answer length distribution (aggregate only)
        answer = q.get("answer", [])
        if isinstance(answer, list):
            answer_lengths.append(len(answer))
        elif isinstance(answer, str):
            answer_lengths.append(1)

        # Gold doc analysis
        gold_doc_ids = q.get("gold_doc_ids", []) or []
        gold_doc_counts.append(len(gold_doc_ids))
        if len(gold_doc_ids) > 1:
            multi_doc_count += 1

        # Field tracking
        for field in expected_fields:
            if field in q:
                field_counters[field]["__present__"] += 1
                if q[field] is None:
                    field_counters[field]["__null__"] += 1

    # Duplicate QID check
    duplicate_qids = [qid for qid, count in collections.Counter(question_ids).items() if count > 1]

    logger.info(
        "Public eval profiled: %d questions, qtypes: %s",
        total_questions, dict(qtypes)
    )

    fields_analysis: dict[str, Any] = {}
    for field in expected_fields:
        fields_analysis[field] = _field_stats(field_counters[field], total_questions)

    return {
        "total_questions": total_questions,
        "duplicate_qids": duplicate_qids,
        "duplicate_qid_count": len(duplicate_qids),
        "question_type_distribution": dict(qtypes),
        "unique_qtypes": list(qtypes.keys()),
        "question_length_distribution": _distribution_stats(question_lengths),
        "gold_doc_count_distribution": _distribution_stats(gold_doc_counts),
        "multi_doc_question_count": multi_doc_count,
        "answer_named_in_question_count": answer_named_in_question_count,
        "answer_verified_count": answer_verified_count,
        "answer_length_distribution": _distribution_stats(answer_lengths),
        "fields": fields_analysis,
    }


# ---------------------------------------------------------------------------
# Hidden Evaluation Profiler
# ---------------------------------------------------------------------------

def profile_eval_hidden(eval_path: Path) -> dict[str, Any]:
    """Stream and profile eval_hidden.jsonl — NEVER exposing ground truth.

    The hidden file only has: qid, question, qtype
    No answer or gold_doc_ids are present, so there is nothing to expose.

    Args:
        eval_path: Path to eval_hidden.jsonl.

    Returns:
        Dictionary with ONLY structural/statistical information.
        Ground truth answers are NOT present in this file and are NOT accessed.
    """
    logger.info("Profiling hidden eval (structure only): %s", eval_path)

    total_questions: int = 0
    question_ids: list[str] = []
    qtypes: collections.Counter = collections.Counter()
    question_lengths: list[int] = []
    available_fields: set[str] = set()

    # SECURITY: Only read legitimate fields; explicitly ignore any unexpected answer fields
    SAFE_FIELDS = {"qid", "question", "qtype"}

    for q in _stream_jsonl(eval_path):
        total_questions += 1

        # Track which fields exist
        for field in q.keys():
            available_fields.add(field)

        # SECURITY: Do NOT read answer, gold_doc_ids, or any non-safe fields
        qid = q.get("qid", "")
        question_ids.append(qid)

        qtype = q.get("qtype", "unknown")
        qtypes[qtype] += 1

        question_text = q.get("question", "") or ""
        question_lengths.append(len(question_text))

    duplicate_qids = [qid for qid, count in collections.Counter(question_ids).items() if count > 1]

    # Verify no unexpected fields with potential ground truth
    unexpected_fields = available_fields - SAFE_FIELDS
    if unexpected_fields:
        logger.warning(
            "Hidden eval contains unexpected fields: %s — these will NOT be read or stored",
            unexpected_fields,
        )

    logger.info("Hidden eval profiled: %d questions, qtypes: %s", total_questions, dict(qtypes))

    return {
        "total_questions": total_questions,
        "duplicate_qids": duplicate_qids,
        "available_fields": sorted(list(available_fields & SAFE_FIELDS)),
        "question_type_distribution": dict(qtypes),
        "unique_qtypes": list(qtypes.keys()),
        "question_length_distribution": _distribution_stats(question_lengths),
        "security_note": "Ground truth answers are NOT present in this file and are NOT accessed or stored.",
    }


# ---------------------------------------------------------------------------
# Main Profile Function
# ---------------------------------------------------------------------------

def generate_profile(
    corpus_path: Path,
    eval_public_path: Path,
    eval_hidden_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Generate the full dataset profile and save it to JSON.

    Args:
        corpus_path: Path to corpus.jsonl.
        eval_public_path: Path to eval_public.jsonl.
        eval_hidden_path: Path to eval_hidden.jsonl.
        output_path: Path to write the profile JSON.

    Returns:
        The complete profile dictionary.
    """
    logger.info("=== PHASE 0: Dataset Intelligence & Forensic Inspection ===")

    corpus_profile = profile_corpus(corpus_path)
    public_profile = profile_eval_public(eval_public_path)
    hidden_profile = profile_eval_hidden(eval_hidden_path)

    profile: dict[str, Any] = {
        "schema_version": "1.0",
        "phase": "0",
        "description": "GraphMind dataset intelligence profile",
        "corpus": corpus_profile,
        "eval_public": public_profile,
        "eval_hidden": hidden_profile,
    }

    # Save profile
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, ensure_ascii=False)

    logger.info("Profile saved to: %s", output_path)

    # Print summary
    print("\n" + "=" * 60)
    print("DATASET INTELLIGENCE SUMMARY")
    print("=" * 60)
    print(f"Corpus documents:          {corpus_profile['total_documents']:>8,}")
    print(f"Duplicate document IDs:    {corpus_profile['duplicate_id_count']:>8,}")
    print(f"Public questions:          {public_profile['total_questions']:>8,}")
    print(f"Hidden questions:          {hidden_profile['total_questions']:>8,}")
    print(f"Public question types:     {public_profile['unique_qtypes']}")
    print(f"Hidden question types:     {hidden_profile['unique_qtypes']}")
    print(f"Avg text length (chars):   {corpus_profile['text_length_distribution'].get('mean', 'N/A'):>8}")
    print(f"Avg approx tokens:         {corpus_profile['approx_tokens_distribution'].get('mean', 'N/A'):>8}")
    print(f"Multi-doc questions:       {public_profile['multi_doc_question_count']:>8,}")
    print("=" * 60)

    return profile


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for the dataset profiler."""
    # Determine default paths relative to the script or project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent  # benchmark/dataset/profile.py → project root

    parser = argparse.ArgumentParser(
        description="Phase 0: GraphMind Dataset Intelligence & Forensic Inspection"
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=project_root / "corpus.jsonl",
        help="Path to corpus.jsonl",
    )
    parser.add_argument(
        "--eval_public",
        type=Path,
        default=project_root / "eval_public.jsonl",
        help="Path to eval_public.jsonl",
    )
    parser.add_argument(
        "--eval_hidden",
        type=Path,
        default=project_root / "eval_hidden.jsonl",
        help="Path to eval_hidden.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "dataset_profile.json",
        help="Output path for profile JSON",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(args.log_level)

    try:
        generate_profile(
            corpus_path=args.corpus,
            eval_public_path=args.eval_public,
            eval_hidden_path=args.eval_hidden,
            output_path=args.output,
        )
    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during profiling: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
