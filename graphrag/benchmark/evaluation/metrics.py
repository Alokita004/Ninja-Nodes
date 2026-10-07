"""Aggregate benchmark metrics."""

from __future__ import annotations

from dataclasses import asdict
from statistics import mean
from typing import Any, Iterable

from .schemas import BenchmarkRecord


def summarize(records: Iterable[BenchmarkRecord]) -> dict[str, Any]:
    rows = list(records)
    if not rows:
        return {"record_count": 0, "accuracy": None, "completeness": None, "grounding": None, "retrieval_precision": None, "retrieval_recall": None, "mrr": None, "citation_precision": None, "citation_recall": None, "evidence_coverage": None, "unsupported_claim_rate": None, "average_tokens": 0.0, "average_latency_seconds": 0.0, "average_retrieval_latency_seconds": 0.0, "average_generation_latency_seconds": 0.0, "average_evidence_count": 0.0, "average_agent_steps": 0.0, "average_tool_calls": 0.0, "average_strategy_changes": 0.0, "failure_rate": 0.0, "timeout_rate": 0.0, "empty_retrieval_rate": 0.0}
    completed = [row for row in rows if row.error is None]
    def average(attribute: str) -> float | None:
        values = [getattr(row, attribute) for row in completed if getattr(row, attribute) is not None]
        return mean(values) if values else None

    return {
        "record_count": len(rows),
        "completed_count": len(completed),
        "accuracy": average("correct"),
        "completeness": average("completeness"),
        "grounding": average("grounding"),
        "retrieval_precision": average("retrieval_precision"),
        "retrieval_recall": average("retrieval_recall"),
        "mrr": average("reciprocal_rank"),
        "citation_precision": average("citation_precision"),
        "citation_recall": average("citation_recall"),
        "evidence_coverage": average("evidence_coverage"),
        "unsupported_claim_rate": average("unsupported_claim_rate"),
        "average_tokens": mean(row.total_tokens for row in completed) if completed else 0.0,
        "average_latency_seconds": mean(row.latency_seconds for row in completed) if completed else 0.0,
        "average_retrieval_latency_seconds": mean(row.retrieval_latency_seconds for row in completed) if completed else 0.0,
        "average_generation_latency_seconds": mean(row.generation_latency_seconds for row in completed) if completed else 0.0,
        "average_evidence_count": mean(row.evidence_count for row in completed) if completed else 0.0,
        "average_agent_steps": mean(row.agent_steps for row in completed) if completed else 0.0,
        "average_tool_calls": mean(row.tool_calls for row in completed) if completed else 0.0,
        "average_strategy_changes": mean(row.strategy_changes for row in completed) if completed else 0.0,
        "failure_rate": sum(row.error is not None for row in rows) / len(rows),
        "timeout_rate": sum(row.error is not None and "timeout" in row.error.lower() for row in rows) / len(rows),
        "empty_retrieval_rate": sum(row.empty_retrieval for row in rows) / len(rows),
        "records": [asdict(row) for row in rows],
    }