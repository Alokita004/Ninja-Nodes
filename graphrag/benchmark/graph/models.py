"""Typed outputs for the verified Document graph surface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    url: str
    wikidata_qid: str
    wikipedia_pageid: int
    approx_tokens: int
    text: str


@dataclass(frozen=True)
class DocumentCount:
    count: int


@dataclass(frozen=True)
class QueryError:
    operation: str
    message: str