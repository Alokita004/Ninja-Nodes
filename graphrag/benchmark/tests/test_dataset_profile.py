from __future__ import annotations

import json
from pathlib import Path

from benchmark.dataset.profile import build_profile, profile_file


def test_profile_detects_structure_duplicates_and_malformed_records(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"doc_id":"d1","title":"One","text":"alpha beta"}\n'
        '{"doc_id":"d1","title":"One","text":"alpha beta"}\n'
        '{bad json}\n',
        encoding="utf-8",
    )
    result = profile_file(corpus, "corpus")
    assert result["record_count"] == 2
    assert len(result["malformed_records"]) == 1
    assert result["duplicate_id_count"] == 1
    assert result["duplicate_document_count"] == 1
    assert result["field_summary"]["title"]["required_by_observation"] is True


def test_build_profile_redacts_hidden_values_and_checks_public_references(tmp_path: Path) -> None:
    (tmp_path / "corpus.jsonl").write_text(
        '{"doc_id":"d1","title":"One","url":"u","wikidata_qid":"q","wikipedia_pageid":1,"approx_tokens":2,"text":"alpha"}\n',
        encoding="utf-8",
    )
    (tmp_path / "eval_public.jsonl").write_text(
        '{"qid":"p1","question":"What?","qtype":"lookup","answer":["one"],"gold_doc_ids":["d1"],"answer_verified":true}\n',
        encoding="utf-8",
    )
    (tmp_path / "eval_hidden.jsonl").write_text(
        '{"qid":"h1","question":"Hidden?","qtype":"lookup"}\n',
        encoding="utf-8",
    )
    result = build_profile(tmp_path)
    assert result["datasets"]["eval_public"]["gold_document_references_missing_from_corpus"] == 0
    hidden = result["datasets"]["eval_hidden"]
    assert hidden["hidden_values_redacted"] is True
    assert hidden["representative_records"] == [{"fields": ["qid", "qtype", "question"]}]
    assert "answer" not in json.dumps(hidden)


def test_repository_datasets_match_phase_zero_profile() -> None:
    workspace_root = Path(__file__).resolve().parents[3]
    profile = build_profile(workspace_root)
    datasets = profile["datasets"]
    assert datasets["corpus"]["record_count"] == 2951
    assert datasets["eval_public"]["record_count"] == 100
    assert datasets["eval_hidden"]["record_count"] == 50
    assert datasets["corpus"]["malformed_records"] == []
    assert datasets["eval_public"]["gold_document_references_missing_from_corpus"] == 0
    assert "answer" not in datasets["eval_hidden"]