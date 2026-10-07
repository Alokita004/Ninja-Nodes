from __future__ import annotations

import pytest

from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import evidence_id
from benchmark.evaluation.citations import CitationValidationError, extract_citations, validate_answer_citations


def make_evidence(document_id: str) -> Evidence:
    text = f"Evidence for {document_id}"
    return Evidence(evidence_id(document_id, text, "test"), document_id, text, "test")


def test_citations_resolve_and_metrics_are_computed() -> None:
    evidence = EvidenceSet.from_items([make_evidence("d1"), make_evidence("d2")])
    metrics = validate_answer_citations("Supported claim [d1].", evidence, corpus_document_ids={"d1", "d2"})
    assert extract_citations("A [d1] and [d1] reference.") == ("d1",)
    assert metrics.citation_precision == 1.0
    assert metrics.citation_recall == 0.5
    assert metrics.evidence_coverage == 0.5
    assert metrics.unsupported_claim_rate == 0.0


def test_fabricated_citation_fails() -> None:
    evidence = EvidenceSet.from_items([make_evidence("d1")])
    with pytest.raises(CitationValidationError, match="do not resolve"):
        validate_answer_citations("Claim [missing].", evidence)


def test_uncited_claim_is_measured() -> None:
    evidence = EvidenceSet.from_items([make_evidence("d1")])
    metrics = validate_answer_citations("Supported [d1]. Uncited claim.", evidence)
    assert metrics.unsupported_claim_rate == 0.5