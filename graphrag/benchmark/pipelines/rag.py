"""Provider-neutral Vector RAG baseline."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import evidence_id, validate_evidence_set


class QueryEmbeddingModel(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class AnswerGenerator(Protocol):
    def generate(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class RAGMetrics:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    retrieval_latency_seconds: float
    generation_latency_seconds: float
    total_latency_seconds: float
    retrieved_chunks: int


@dataclass(frozen=True)
class RAGResult:
    answer: str
    evidence: EvidenceSet
    citations: tuple[str, ...]
    metrics: RAGMetrics
    insufficient_evidence: bool


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    text: str
    metadata: dict[str, Any]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have equal non-zero dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class VectorRAG:
    def __init__(self, model: QueryEmbeddingModel, generator: AnswerGenerator, documents: Sequence[SourceDocument], *, top_k: int = 3, min_score: float = 0.0):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.model = model
        self.generator = generator
        self.documents = tuple(documents)
        self.top_k = top_k
        self.min_score = min_score
        self._document_vectors = model.embed_documents([doc.text for doc in self.documents])
        if len(self._document_vectors) != len(self.documents):
            raise ValueError("embedding model returned an unexpected document count")

    def query(self, question: str) -> RAGResult:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        started = time.perf_counter()
        retrieval_started = time.perf_counter()
        query_vector = self.model.embed_query(question)
        ranked = sorted(
            ((cosine_similarity(query_vector, vector), document) for document, vector in zip(self.documents, self._document_vectors)),
            key=lambda item: (-item[0], item[1].document_id),
        )
        selected = [(score, document) for score, document in ranked[: self.top_k] if score >= self.min_score]
        retrieval_latency = time.perf_counter() - retrieval_started
        evidence = EvidenceSet.from_items(
            [
                Evidence(
                    evidence_id=evidence_id(document.document_id, document.text, "vector", None),
                    document_id=document.document_id,
                    text=document.text,
                    retrieval_method="vector",
                    relevance_score=float(score),
                    metadata=document.metadata,
                )
                for score, document in selected
            ]
        )
        validate_evidence_set(evidence)
        if not evidence.items:
            answer = "INSUFFICIENT_EVIDENCE"
            generation_latency = 0.0
            insufficient = True
        else:
            prompt = self._grounded_prompt(question, evidence)
            generation_started = time.perf_counter()
            answer = self.generator.generate(prompt)
            generation_latency = time.perf_counter() - generation_started
            insufficient = False
        input_tokens = len(question.split()) + sum(len(item.text.split()) for item in evidence.items)
        output_tokens = len(answer.split())
        metrics = RAGMetrics(input_tokens, output_tokens, input_tokens + output_tokens, retrieval_latency, generation_latency, time.perf_counter() - started, len(evidence.items))
        return RAGResult(answer, evidence, tuple(item.document_id for item in evidence.items), metrics, insufficient)

    @staticmethod
    def _grounded_prompt(question: str, evidence: EvidenceSet) -> str:
        context = "\n\n".join(f"[{item.document_id}] {item.text}" for item in evidence.items)
        return "Use only the supplied evidence. Do not use external knowledge. If evidence is insufficient, say so.\n\nQuestion: " + question + "\n\nEvidence:\n" + context