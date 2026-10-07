from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.dataset.validator import DatasetValidationError, validate_datasets, validate_jsonl


def test_repository_datasets_satisfy_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    assert validate_datasets(root) == {"corpus": 2951, "eval_public": 100, "eval_hidden": 50}


@pytest.mark.parametrize(
    ("dataset_name", "record", "message"),
    [
        ("corpus", {"doc_id": "d1"}, "missing required fields"),
        ("corpus", {"doc_id": "d1", "title": "t", "url": "u", "wikidata_qid": "q", "wikipedia_pageid": "bad", "approx_tokens": 1, "text": "x"}, "must be int"),
        ("eval_public", {"qid": "q1", "question": "q", "qtype": "lookup", "answer_named_in_question": False, "guess_baseline": 0, "gold_doc_ids": [1], "answer_verified": True, "answer": ["x"]}, "must be string_list"),
        ("eval_hidden", {"qid": "q1", "question": "q", "qtype": "lookup", "answer": ["leaked"]}, "unknown fields"),
    ],
)
def test_invalid_records_fail(dataset_name: str, record: dict, message: str, tmp_path: Path) -> None:
    path = tmp_path / f"{dataset_name}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match=message):
        validate_jsonl(path, dataset_name, corpus_ids={"d1"})


def test_validator_detects_malformed_json_duplicates_and_broken_references(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"doc_id":"d1","title":"t","url":"u","wikidata_qid":"q","wikipedia_pageid":1,"approx_tokens":1,"text":"x"}\n'
        '{"doc_id":"d1","title":"t","url":"u","wikidata_qid":"q","wikipedia_pageid":1,"approx_tokens":1,"text":"x"}\n'
        '{bad}\n',
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError) as error:
        validate_jsonl(corpus, "corpus")
    text = str(error.value)
    assert "duplicate doc_id" in text
    assert "duplicate complete document" in text
    assert "malformed JSON" in text

    public = tmp_path / "eval_public.jsonl"
    public.write_text(
        json.dumps(
            {
                "qid": "p1",
                "question": "q",
                "qtype": "lookup",
                "answer_named_in_question": False,
                "guess_baseline": 0.0,
                "gold_doc_ids": ["missing"],
                "answer_verified": True,
                "answer": ["x"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="unknown document"):
        validate_jsonl(public, "eval_public", corpus_ids={"d1"})