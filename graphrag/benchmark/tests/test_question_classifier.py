from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.dataset.question_classifier import classify_public_file, classify_question


def test_repository_public_taxonomy_matches_observed_dataset() -> None:
    root = Path(__file__).resolve().parents[3]
    result = classify_public_file(root / "eval_public.jsonl")
    assert result["record_count"] == 100
    assert result["observed_qtypes"] == {
        "aggregation": 21,
        "lookup": 19,
        "multi_hop": 28,
        "superlative": 10,
        "temporal": 22,
    }
    assert all(item["graph_traversal_requirement"] == "not_confirmed" for item in result["analyses"])


@pytest.mark.parametrize(
    ("qtype", "complexity", "scope", "vector_sufficiency"),
    [
        ("lookup", "direct_lookup", "single_document", "potentially_sufficient"),
        ("multi_hop", "multi_hop_reasoning", "single_document_with_internal_links", "potentially_sufficient"),
        ("temporal", "temporal_reasoning", "multiple_documents", "not_sufficient_alone"),
        ("aggregation", "set_aggregation", "multiple_documents", "not_sufficient_alone"),
        ("superlative", "set_ranking", "multiple_documents", "not_sufficient_alone"),
    ],
)
def test_observed_question_types_have_explicit_profiles(qtype: str, complexity: str, scope: str, vector_sufficiency: str) -> None:
    analysis = classify_question(
        {"qid": "test", "question": "According to the provided corpus, what happened?", "qtype": qtype, "gold_doc_ids": ["d1"]}
    )
    assert analysis.complexity == complexity
    assert analysis.expected_evidence_scope == scope
    assert analysis.vector_retrieval_sufficiency == vector_sufficiency


def test_classifier_rejects_unobserved_or_malformed_records() -> None:
    with pytest.raises(ValueError, match="Unobserved question type"):
        classify_question({"qid": "x", "question": "q", "qtype": "reasoning", "gold_doc_ids": []})
    with pytest.raises(ValueError, match="gold_doc_ids"):
        classify_question({"qid": "x", "question": "q", "qtype": "lookup", "gold_doc_ids": [1]})


def test_public_classifier_does_not_read_hidden_file(tmp_path: Path) -> None:
    public = tmp_path / "public.jsonl"
    public.write_text(json.dumps({"qid": "p1", "question": "q", "qtype": "lookup", "gold_doc_ids": ["d1"]}) + "\n", encoding="utf-8")
    result = classify_public_file(public)
    assert result["record_count"] == 1
    assert "eval_hidden" not in json.dumps(result)