"""Deterministic taxonomy analysis for public evaluation questions."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


OBSERVED_QTYPES = frozenset({"aggregation", "lookup", "multi_hop", "superlative", "temporal"})


@dataclass(frozen=True)
class QuestionAnalysis:
    qid: str
    qtype: str
    complexity: str
    retrieval_requirement: str
    expected_evidence_scope: str
    graph_traversal_requirement: str
    vector_retrieval_sufficiency: str
    question_length_characters: int
    public_gold_document_count: int


def _iter_public(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line, raw in enumerate(handle, 1):
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line}: public record must be an object")
            yield record


def classify_question(record: dict[str, Any]) -> QuestionAnalysis:
    """Classify a public record using its observed dataset label.

    Public gold document counts are reported as analysis metadata; they are not
    used to choose a retrieval algorithm or to inspect hidden evaluation data.
    """
    qtype = record.get("qtype")
    if qtype not in OBSERVED_QTYPES:
        raise ValueError(f"Unobserved question type: {qtype!r}")
    question = record.get("question")
    if not isinstance(question, str):
        raise ValueError("question must be a string")
    gold_documents = record.get("gold_doc_ids")
    if not isinstance(gold_documents, list) or not all(isinstance(item, str) for item in gold_documents):
        raise ValueError("public gold_doc_ids must be an array of strings")

    profiles = {
        "lookup": ("direct_lookup", "single_document", "not_confirmed", "potentially_sufficient"),
        "multi_hop": ("multi_hop_reasoning", "single_document_with_internal_links", "not_confirmed", "potentially_sufficient"),
        "temporal": ("temporal_reasoning", "multiple_documents", "not_confirmed", "not_sufficient_alone"),
        "aggregation": ("set_aggregation", "multiple_documents", "not_confirmed", "not_sufficient_alone"),
        "superlative": ("set_ranking", "multiple_documents", "not_confirmed", "not_sufficient_alone"),
    }
    complexity, scope, graph_requirement, vector_sufficiency = profiles[qtype]
    retrieval = {
        "lookup": "retrieve the document matching the event described in the question",
        "multi_hop": "retrieve the event document and resolve the location/date clues within it",
        "temporal": "resolve the referenced Olympic edition, then retrieve the event document",
        "aggregation": "retrieve the complete candidate event set before counting the threshold matches",
        "superlative": "retrieve the complete candidate event set before ranking the competitor counts",
    }[qtype]
    return QuestionAnalysis(
        qid=str(record.get("qid", "")),
        qtype=qtype,
        complexity=complexity,
        retrieval_requirement=retrieval,
        expected_evidence_scope=scope,
        graph_traversal_requirement=graph_requirement,
        vector_retrieval_sufficiency=vector_sufficiency,
        question_length_characters=len(question),
        public_gold_document_count=len(gold_documents),
    )


def classify_public_file(path: str | Path) -> dict[str, Any]:
    analyses = [classify_question(record) for record in _iter_public(path)]
    return {
        "source": str(path),
        "record_count": len(analyses),
        "observed_qtypes": dict(sorted(Counter(item.qtype for item in analyses).items())),
        "complexity_counts": dict(sorted(Counter(item.complexity for item in analyses).items())),
        "analyses": [asdict(item) for item in analyses],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify public GraphMind evaluation questions")
    parser.add_argument("--input", type=Path, default=Path("eval_public.jsonl"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    payload = json.dumps(classify_public_file(args.input), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()