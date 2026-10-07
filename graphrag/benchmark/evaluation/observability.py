"""Observability helpers for reproducible benchmark runs."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .schemas import BenchmarkConfig


LOGGER = logging.getLogger(__name__)
SAFE_DETAIL_KEYS = frozenset({
    "duration_seconds",
    "error_code",
    "error_type",
    "evidence_count",
    "record_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "agent_steps",
    "tool_calls",
    "status_code",
    "stop_reason",
})


def _config_value(config: BenchmarkConfig | Mapping[str, Any], key: str, default: Any) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def config_hash(config: BenchmarkConfig | Mapping[str, Any] | None = None) -> str:
    """Return a stable digest for a benchmark configuration."""
    normalized = config_snapshot(config)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def config_snapshot(config: BenchmarkConfig | Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = config if config is not None else BenchmarkConfig()
    judge = _config_value(payload, "judge", {"method": "normalized_exact_match"})
    if not isinstance(judge, Mapping):
        raise ValueError("judge configuration must be a mapping")
    return {
        "configuration_version": _config_value(payload, "configuration_version", 1),
        "llm_model": _config_value(payload, "llm_model", "mock-model"),
        "embedding_model": _config_value(payload, "embedding_model", "mock-embedding"),
        "chunk_size": _config_value(payload, "chunk_size", 512),
        "chunk_overlap": _config_value(payload, "chunk_overlap", 64),
        "top_k": _config_value(payload, "top_k", 3),
        "temperature": _config_value(payload, "temperature", 0.0),
        "max_agent_steps": _config_value(payload, "max_agent_steps", 3),
        "context_limit": _config_value(payload, "context_limit", 8192),
        "judge": dict(judge),
    }


def build_run_metadata(
    pipeline: str,
    question_id: str | None = None,
    config: BenchmarkConfig | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a reproducible run record for a single benchmark execution."""
    run_id = f"{pipeline}-{uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "configuration_id": config_hash(config),
        "configuration_version": config_snapshot(config)["configuration_version"],
        "pipeline": pipeline,
        "question_id": question_id,
    }


def log_benchmark_event(
    event: str,
    *,
    pipeline: str,
    question_id: str | None = None,
    config: BenchmarkConfig | Mapping[str, Any] | None = None,
    run_id: str | None = None,
    timestamp: str | None = None,
    level: int = logging.INFO,
    **details: Any,
) -> dict[str, Any]:
    """Emit structured run metadata and allowlisted details, never input text."""
    payload = build_run_metadata(pipeline, question_id, config)
    if run_id is not None:
        payload["run_id"] = run_id
    if timestamp is not None:
        payload["timestamp"] = timestamp
    payload["event"] = event
    payload["details"] = {key: value for key, value in details.items() if key in SAFE_DETAIL_KEYS}
    LOGGER.log(level, "benchmark_event", extra=payload)
    return payload
