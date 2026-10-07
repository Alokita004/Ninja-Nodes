from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from benchmark.runtime import build_configured_pipelines


def test_configured_factory_registers_pipelines_and_defers_model_calls(monkeypatch) -> None:
    calls = {"document_embeddings": 0, "query_embeddings": 0, "generation": 0}

    class FakeConnection:
        def __init__(self, **kwargs):
            self.options = kwargs

        def getToken(self):
            return "test-token"

        def gsql(self, query):
            assert query == "USE GRAPH TestGraph"
            return {"ok": True}

        def getVertexCount(self, vertex_type, realtime=True):
            assert vertex_type == "Document"
            return 1

        def getVertices(self, vertex_type, **kwargs):
            assert vertex_type == "Document"
            return [
                {
                    "v_id": "doc-1",
                    "v_type": "Document",
                    "attributes": {"text": "verified evidence", "title": "Test document"},
                }
            ]

    class FakeEmbedding:
        def embed_documents(self, texts):
            calls["document_embeddings"] += 1
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text):
            calls["query_embeddings"] += 1
            return [1.0, 0.0]

    class FakeLanguageModel:
        def invoke(self, prompt):
            calls["generation"] += 1
            return SimpleNamespace(content="Answer grounded in evidence.")

    fake_tigergraph = ModuleType("pyTigerGraph")
    fake_tigergraph.TigerGraphConnection = FakeConnection
    monkeypatch.setitem(sys.modules, "pyTigerGraph", fake_tigergraph)

    fake_config = ModuleType("common.config")
    fake_config.db_config = {
        "hostname": "https://tigergraph.invalid",
        "graph_name": "TestGraph",
        "secret": "not-a-real-secret",
        "default_timeout": 5,
    }
    fake_config.get_completion_config = lambda graph_name: {"graphname": graph_name}
    fake_config.get_embedding_service = lambda: FakeEmbedding()
    fake_config.get_llm_service = lambda config: SimpleNamespace(llm=FakeLanguageModel())
    fake_config.validate_graphname = lambda graph_name: graph_name
    monkeypatch.setitem(sys.modules, "common.config", fake_config)

    pipelines = build_configured_pipelines()
    assert set(pipelines) == {"rag", "graphrag", "agentic"}
    assert calls == {"document_embeddings": 0, "query_embeddings": 0, "generation": 0}

    rag_result = pipelines["rag"]("What is verified?", "lookup")
    assert rag_result.answer == "Answer grounded in evidence."
    assert rag_result.citations == ("doc-1",)
    assert calls["document_embeddings"] == 1

    agentic_events = list(pipelines["agentic"].stream("What is verified?", "lookup"))
    assert [event for event, _ in agentic_events] == ["step", "result"]
    assert agentic_events[-1][1].answer == "Answer grounded in evidence."