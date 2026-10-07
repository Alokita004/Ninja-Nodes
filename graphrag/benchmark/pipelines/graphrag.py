"""Deterministic Hybrid GraphRAG over vector and verified document retrieval."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import evidence_id, validate_evidence_set
from benchmark.pipelines.rag import AnswerGenerator, QueryEmbeddingModel, SourceDocument, cosine_similarity


class DocumentGraphProvider(Protocol):
    def list_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class HybridMetrics:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    vector_results: int
    graph_results: int
    evidence_count: int
    graph_queries: int
    retrieval_latency_seconds: float
    generation_latency_seconds: float
    total_latency_seconds: float


@dataclass(frozen=True)
class HybridResult:
    answer: str
    evidence: EvidenceSet
    citations: tuple[str, ...]
    metrics: HybridMetrics
    insufficient_evidence: bool


class HybridGraphRAG:
    def __init__(self, model: QueryEmbeddingModel, generator: AnswerGenerator, documents: Sequence[SourceDocument], graph: DocumentGraphProvider, *, vector_top_k: int = 3, candidate_limit: int = 20, min_score: float = 0.0):
        if vector_top_k < 1 or candidate_limit < 1:
            raise ValueError("vector_top_k and candidate_limit must be positive")
        self.model = model
        self.generator = generator
        self.documents = tuple(documents)
        self.graph = graph
        self.vector_top_k = vector_top_k
        self.candidate_limit = candidate_limit
        self.min_score = min_score
        self._vectors = model.embed_documents([doc.text for doc in self.documents])
        if len(self._vectors) != len(self.documents):
            raise ValueError("embedding model returned an unexpected document count")

    def query(self, question: str, qtype: str) -> HybridResult:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        if not isinstance(qtype, str) or not qtype.strip():
            raise ValueError("qtype must be a non-empty string")
        started = time.perf_counter()
        retrieval_started = time.perf_counter()
        query_vector = self.model.embed_query(question)
        ranked = sorted(
            ((cosine_similarity(query_vector, vector), document) for document, vector in zip(self.documents, self._vectors)),
            key=lambda item: (-item[0], item[1].document_id),
        )
        vector_selected = [(score, document) for score, document in ranked[: self.vector_top_k] if score >= self.min_score]
        graph_limit = self.candidate_limit if qtype in {"aggregation", "superlative", "temporal"} else min(self.candidate_limit, self.vector_top_k)
        graph_rows = self.graph.list_documents(graph_limit)
        graph_documents = [self._source_document(row) for row in graph_rows]
        merged: dict[str, Evidence] = {}
        for score, document in vector_selected:
            merged[document.document_id] = Evidence(
                evidence_id=evidence_id(document.document_id, document.text, "vector"), document_id=document.document_id, text=document.text,
                retrieval_method="vector", relevance_score=float(score), metadata=document.metadata,
            )
        for document in graph_documents:
            merged.setdefault(document.document_id, Evidence(
                evidence_id=evidence_id(document.document_id, document.text, "graph_document"), document_id=document.document_id, text=document.text,
                retrieval_method="graph_document", metadata=document.metadata,
            ))
        evidence = EvidenceSet.from_items(list(merged.values()))
        validate_evidence_set(evidence)
        retrieval_latency = time.perf_counter() - retrieval_started
        if not evidence.items:
            answer = "INSUFFICIENT_EVIDENCE"
            generation_latency = 0.0
            insufficient = True
        else:
            context = "\n\n".join(f"[{item.document_id}] {item.text}" for item in evidence.items)
            prompt = "Use only the supplied evidence. Do not use external knowledge. If evidence is insufficient, say so.\n\nQuestion: " + question + "\n\nEvidence:\n" + context
            generation_started = time.perf_counter()
            answer = self.generator.generate(prompt)
            generation_latency = time.perf_counter() - generation_started
            insufficient = False
        input_tokens = len(question.split()) + sum(len(item.text.split()) for item in evidence.items)
        output_tokens = len(answer.split())
        metrics = HybridMetrics(input_tokens, output_tokens, input_tokens + output_tokens, len(vector_selected), len(graph_documents), len(evidence.items), 1, retrieval_latency, generation_latency, time.perf_counter() - started)
        return HybridResult(answer, evidence, tuple(item.document_id for item in evidence.items), metrics, insufficient)

    @staticmethod
    def _source_document(row: dict[str, Any]) -> SourceDocument:
        document_id = str(row.get("doc_id") or row.get("v_id") or row.get("id"))
        return SourceDocument(document_id, str(row.get("text", "")), {key: value for key, value in row.items() if key not in {"text", "doc_id", "v_id", "id"}})