from __future__ import annotations

import math

import pytest

from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import EvidenceValidationError, evidence_id, validate_evidence, validate_evidence_set


def make_evidence(**overrides) -> Evidence:
    values = {
        "evidence_id": evidence_id("d1", "text", "document_lookup"),
        "document_id": "d1",
        "text": "text",
        "retrieval_method": "document_lookup",
    }
    values.update(overrides)
    return Evidence(**values)


def test_evidence_validates_and_has_deterministic_identity() -> None:
    first = make_evidence()
    second = make_evidence()
    assert first == second
    assert validate_evidence(first) == first
    assert validate_evidence_set(EvidenceSet.from_items([first])).document_ids() == {"d1"}


@pytest.mark.parametrize(
    "item",
    [
        make_evidence(document_id=""),
        make_evidence(text=""),
        make_evidence(relevance_score=math.nan),
        make_evidence(graph_path=["ok", ""]),
        make_evidence(metadata=[]),
    ],
)
def test_invalid_evidence_is_rejected(item: Evidence) -> None:
    with pytest.raises(EvidenceValidationError):
        validate_evidence(item)


def test_duplicate_evidence_ids_are_rejected() -> None:
    item = make_evidence()
    with pytest.raises(EvidenceValidationError, match="duplicate"):
        validate_evidence_set(EvidenceSet.from_items([item, item]))