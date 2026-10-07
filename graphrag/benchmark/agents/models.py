"""Typed state and trace records for bounded investigations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from benchmark.evidence.models import Evidence


@dataclass(frozen=True)
class TraceStep:
    step_id: int
    agent: str
    action: str
    reason: str
    tool: str
    input_summary: str
    output_summary: str
    evidence_added: int
    tokens: int
    latency_seconds: float


class InvestigationState(TypedDict):
    question: str
    question_type: str
    evidence: list[Evidence]
    unresolved_information: list[str]
    steps: list[TraceStep]
    tool_calls: list[str]
    answer: str
    citations: list[str]
    stop_reason: str
    current_tool: str