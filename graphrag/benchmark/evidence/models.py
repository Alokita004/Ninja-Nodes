"""Common evidence objects shared by all retrieval pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    document_id: str
    text: str
    retrieval_method: str
    chunk_id: str | None = None
    relevance_score: float | None = None
    graph_path: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceSet:
    items: tuple[Evidence, ...]

    @classmethod
    def from_items(cls, items: list[Evidence]) -> "EvidenceSet":
        return cls(tuple(items))

    def document_ids(self) -> set[str]:
        return {item.document_id for item in self.items}