from __future__ import annotations

from benchmark.pipelines.graphrag import HybridGraphRAG
from benchmark.pipelines.rag import SourceDocument


class FakeModel:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


class FakeGenerator:
    def generate(self, prompt):
        return "hybrid answer"


class FakeGraph:
    def __init__(self):
        self.limits = []

    def list_documents(self, limit=20):
        self.limits.append(limit)
        return [{"doc_id": "g1", "text": "graph evidence", "title": "Graph"}]


def test_hybrid_merges_vector_and_graph_evidence() -> None:
    graph = FakeGraph()
    pipeline = HybridGraphRAG(FakeModel(), FakeGenerator(), [SourceDocument("v1", "vector evidence", {})], graph, vector_top_k=1, candidate_limit=10)
    result = pipeline.query("vector evidence", "lookup")
    assert result.answer == "hybrid answer"
    assert {item.retrieval_method for item in result.evidence.items} == {"vector", "graph_document"}
    assert result.metrics.vector_results == 1
    assert result.metrics.graph_results == 1
    assert graph.limits == [1]


def test_set_questions_request_broader_graph_candidates() -> None:
    graph = FakeGraph()
    pipeline = HybridGraphRAG(FakeModel(), FakeGenerator(), [SourceDocument("v1", "text", {})], graph, candidate_limit=25)
    pipeline.query("which event had the highest number", "superlative")
    assert graph.limits == [25]