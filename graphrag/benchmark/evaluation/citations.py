"""Deterministic answer citation and evidence-chain validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from benchmark.evidence.models import EvidenceSet
from benchmark.evidence.validator import validate_evidence_set


_CITATION_RE = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")


class CitationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CitationMetrics:
    citation_precision: float
    citation_recall: float
    evidence_coverage: float
    unsupported_claim_rate: float
    cited_document_ids: tuple[str, ...]
    invalid_document_ids: tuple[str, ...]


def extract_citations(answer: str) -> tuple[str, ...]:
    if not isinstance(answer, str):
        raise CitationValidationError("answer must be a string")
    return tuple(dict.fromkeys(_CITATION_RE.findall(answer)))


def _claim_sentences(answer: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()) if sentence.strip()]


def validate_answer_citations(answer: str, evidence: EvidenceSet, *, corpus_document_ids: Iterable[str] | None = None) -> CitationMetrics:
    validate_evidence_set(evidence)
    citations = extract_citations(answer)
    evidence_ids = evidence.document_ids()
    corpus_ids = set(corpus_document_ids) if corpus_document_ids is not None else None
    invalid = tuple(document_id for document_id in citations if document_id not in evidence_ids or (corpus_ids is not None and document_id not in corpus_ids))
    cited_valid = tuple(document_id for document_id in citations if document_id not in invalid)
    cited_set = set(cited_valid)
    precision = len(cited_set) / len(citations) if citations else 0.0
    recall = len(cited_set & evidence_ids) / len(evidence_ids) if evidence_ids else 0.0
    coverage = recall
    sentences = _claim_sentences(answer)
    unsupported = sum(1 for sentence in sentences if not extract_citations(sentence)) / len(sentences) if sentences else 0.0
    if invalid:
        raise CitationValidationError(f"citations do not resolve to supplied evidence: {list(invalid)}")
    return CitationMetrics(precision, recall, coverage, unsupported, cited_valid, invalid)