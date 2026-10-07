from __future__ import annotations

import pytest

from benchmark.pipelines.rag import SourceDocument, VectorRAG, cosine_similarity


class FakeModel:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


class FakeGenerator:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return "Answer grounded in evidence."


def test_cosine_similarity_rejects_invalid_dimensions() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 0.0])


def test_vector_rag_returns_evidence_citations_and_metrics() -> None:
    generator = FakeGenerator()
    pipeline = VectorRAG(
        FakeModel(),
        generator,
        [SourceDocument("d1", "short text", {"title": "One"}), SourceDocument("d2", "a much longer source", {"title": "Two"})],
        top_k=1,
    )
    result = pipeline.query("short text")
    assert result.answer == "Answer grounded in evidence."
    assert len(result.evidence.items) == 1
    assert result.citations == (result.evidence.items[0].document_id,)
    assert result.metrics.total_tokens == result.metrics.input_tokens + result.metrics.output_tokens
    assert "Use only the supplied evidence" in generator.prompts[0]


def test_vector_rag_returns_explicit_insufficient_evidence() -> None:
    pipeline = VectorRAG(FakeModel(), FakeGenerator(), [SourceDocument("d1", "text", {})], min_score=2.0)
    result = pipeline.query("question")
    assert result.insufficient_evidence is True
    assert result.answer == "INSUFFICIENT_EVIDENCE"
    assert result.evidence.items == ()