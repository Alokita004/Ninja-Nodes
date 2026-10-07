"""Common benchmark result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BenchmarkConfig:
    configuration_version: int = 1
    llm_model: str = "mock-model"
    embedding_model: str = "mock-embedding"
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 3
    temperature: float = 0.0
    max_agent_steps: int = 3
    context_limit: int = 8192
    judge: dict[str, Any] = field(default_factory=lambda: {"method": "normalized_exact_match"})

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BenchmarkConfig":
        config_path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / "FINAL_BENCHMARK_CONFIG.yaml"
        if not config_path.is_file():
            if path is not None:
                raise FileNotFoundError(config_path)
            return cls()
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("benchmark config must be a YAML mapping")
        if not isinstance(payload.get("judge", {"method": "normalized_exact_match"}), dict):
            raise ValueError("benchmark judge config must be a YAML mapping")
        return cls(**payload)


@dataclass(frozen=True)
class BenchmarkRecord:
    qid: str
    pipeline: str
    answer: str
    citations: tuple[str, ...]
    evidence_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_seconds: float
    correct: bool | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    completeness: float | None = None
    grounding: float | None = None
    retrieval_precision: float | None = None
    retrieval_recall: float | None = None
    reciprocal_rank: float | None = None
    citation_precision: float | None = None
    citation_recall: float | None = None
    evidence_coverage: float | None = None
    unsupported_claim_rate: float | None = None
    retrieval_latency_seconds: float = 0.0
    generation_latency_seconds: float = 0.0
    agent_steps: int = 0
    tool_calls: int = 0
    strategy_changes: int = 0
    retrieval_methods: tuple[str, ...] = ()
    stop_reason: str | None = None
    empty_retrieval: bool = False
    run_id: str = ""
    timestamp: str = ""
    configuration_id: str = ""
    configuration_version: int = 1
    question_id: str = ""