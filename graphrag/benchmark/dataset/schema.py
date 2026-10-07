"""Dataset contract models derived from the observed GraphMind JSONL files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


Answer: TypeAlias = list[str]


@dataclass(frozen=True)
class Metadata:
    """Confirmed document metadata fields, represented flat in the JSONL input."""

    title: str
    url: str
    wikidata_qid: str
    wikipedia_pageid: int
    approx_tokens: int


@dataclass(frozen=True)
class Citation:
    """A public evaluation document reference from ``gold_doc_ids``."""

    document_id: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    url: str
    wikidata_qid: str
    wikipedia_pageid: int
    approx_tokens: int
    text: str

    @property
    def metadata(self) -> Metadata:
        return Metadata(
            title=self.title,
            url=self.url,
            wikidata_qid=self.wikidata_qid,
            wikipedia_pageid=self.wikipedia_pageid,
            approx_tokens=self.approx_tokens,
        )


@dataclass(frozen=True)
class Question:
    qid: str
    question: str
    qtype: str


@dataclass(frozen=True)
class EvaluationRecord:
    qid: str
    question: str
    qtype: str
    answer_named_in_question: bool
    guess_baseline: float
    gold_doc_ids: list[str]
    answer_verified: bool
    answer: Answer

    @property
    def citations(self) -> list[Citation]:
        return [Citation(document_id=document_id) for document_id in self.gold_doc_ids]