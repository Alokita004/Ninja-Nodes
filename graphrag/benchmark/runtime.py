"""Runtime composition for configured TigerGraph-backed benchmark pipelines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import Lock
from typing import Any

from benchmark.agents.controller import AgenticGraphRAG, InvestigationResult
from benchmark.evidence.models import EvidenceSet
from benchmark.graph.client import GraphClientConfig, TigerGraphClient
from benchmark.pipelines.graphrag import HybridGraphRAG
from benchmark.pipelines.rag import RAGResult, SourceDocument, VectorRAG


MAX_RUNTIME_DOCUMENTS = 1000


class _ConfiguredGenerator:
    def __init__(self, service: Any):
        self.service = service

    def generate(self, prompt: str) -> str:
        model = getattr(self.service, "llm", None)
        if model is None:
            raise RuntimeError("configured completion service has no model")
        response = model.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, Mapping) else str(item)
                for item in content
            )
        if not isinstance(content, str):
            raise TypeError("completion service returned non-text content")
        return content


class _CachedEmbeddingModel:
    def __init__(self, model: Any):
        self.model = model
        self._lock = Lock()
        self._document_texts: tuple[str, ...] | None = None
        self._document_vectors: list[list[float]] | None = None

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        key = tuple(texts)
        with self._lock:
            if self._document_texts != key:
                self._document_vectors = self.model.embed_documents(list(key))
                self._document_texts = key
            return [list(vector) for vector in self._document_vectors or []]

    def embed_query(self, text: str) -> list[float]:
        return self.model.embed_query(text)


class _GraphDocuments:
    def __init__(self, documents: Sequence[SourceDocument]):
        self.documents = tuple(documents)

    def list_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {"id": document.document_id, "text": document.text, **document.metadata}
            for document in self.documents[:limit]
        ]


class _LazyVectorHandler:
    def __init__(self, model: _CachedEmbeddingModel, generator: _ConfiguredGenerator, documents: Sequence[SourceDocument]):
        self.model = model
        self.generator = generator
        self.documents = tuple(documents)
        self._pipeline: VectorRAG | None = None
        self._lock = Lock()

    def _get_pipeline(self) -> VectorRAG:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = VectorRAG(self.model, self.generator, self.documents)
            return self._pipeline

    def __call__(self, question: str, qtype: str | None) -> RAGResult:
        return self._get_pipeline().query(question)

    def query(self, question: str) -> RAGResult:
        return self._get_pipeline().query(question)


class _LazyHybridHandler:
    def __init__(
        self,
        model: _CachedEmbeddingModel,
        generator: _ConfiguredGenerator,
        documents: Sequence[SourceDocument],
        graph: _GraphDocuments,
    ):
        self.model = model
        self.generator = generator
        self.documents = tuple(documents)
        self.graph = graph
        self._pipeline: HybridGraphRAG | None = None
        self._lock = Lock()

    def _get_pipeline(self) -> HybridGraphRAG:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = HybridGraphRAG(self.model, self.generator, self.documents, self.graph)
            return self._pipeline

    def __call__(self, question: str, qtype: str | None) -> Any:
        return self._get_pipeline().query(question, qtype or "lookup")

    def query(self, question: str, qtype: str) -> Any:
        return self._get_pipeline().query(question, qtype)


class _PipelineEvidenceTool:
    def __init__(self, name: str, pipeline: Any):
        self.name = name
        self.pipeline = pipeline

    def run(self, question: str, question_type: str) -> EvidenceSet:
        result = self.pipeline(question, question_type)
        return result.evidence


class _AgenticHandler:
    def __init__(self, agent: AgenticGraphRAG):
        self.agent = agent

    def __call__(self, question: str, qtype: str | None) -> InvestigationResult:
        return self.agent.investigate(question, qtype or "lookup")

    def stream(self, question: str, qtype: str):
        return self.agent.stream(question, qtype)


def _source_document(row: Mapping[str, Any]) -> SourceDocument:
    attributes = row.get("attributes")
    values = dict(attributes) if isinstance(attributes, Mapping) else {}
    values.update({key: value for key, value in row.items() if key not in {"attributes", "v_type"}})
    document_id = values.get("doc_id") or values.get("v_id") or values.get("id")
    text = values.get("text")
    if not isinstance(document_id, str) or not document_id or not isinstance(text, str):
        raise ValueError("TigerGraph Document records must include an identifier and text")
    metadata = {
        key: value
        for key, value in values.items()
        if key not in {"doc_id", "v_id", "id", "text"}
    }
    return SourceDocument(document_id, text, metadata)


def build_configured_pipelines() -> dict[str, Any]:
    """Create query handlers from the configured TigerGraph and model services.

    Embedding/generation calls are deferred until a pipeline is queried. The
    bounded document snapshot is read from TigerGraph during app startup.
    """
    from pyTigerGraph import TigerGraphConnection

    from common.config import (
        db_config,
        get_completion_config,
        get_embedding_service,
        get_llm_service,
        validate_graphname,
    )

    hostname = db_config.get("hostname")
    graph_name = validate_graphname(str(db_config.get("graph_name") or db_config.get("graphname") or ""))
    if not hostname or not graph_name:
        raise ValueError("TigerGraph hostname and graph name must be configured")

    connection = TigerGraphConnection(
        host=hostname,
        graphname=graph_name,
        gsqlSecret=db_config.get("secret", ""),
        username=db_config.get("username", "tigergraph"),
        tgCloud=True,
        restppPort=db_config.get("restppPort", "9000"),
        gsPort=db_config.get("gsPort", "14240"),
    )
    if not connection.getToken():
        raise ConnectionError("TigerGraph authentication failed")
    connection.gsql("USE GRAPH " + graph_name)

    graph_client = TigerGraphClient(
        connection,
        GraphClientConfig(timeout_seconds=int(db_config.get("default_timeout", 30))),
    )
    document_count = graph_client.document_count()
    if document_count > MAX_RUNTIME_DOCUMENTS:
        raise ValueError(f"configured graph has more than {MAX_RUNTIME_DOCUMENTS} benchmark documents")
    rows = graph_client.list_documents(document_count) if document_count else []
    documents = tuple(_source_document(row) for row in rows)
    if len(documents) != document_count:
        raise ValueError("TigerGraph returned an incomplete Document snapshot")

    model = _CachedEmbeddingModel(get_embedding_service())
    generator = _ConfiguredGenerator(get_llm_service(get_completion_config(graph_name)))
    graph_documents = _GraphDocuments(documents)
    rag = _LazyVectorHandler(model, generator, documents)
    graphrag = _LazyHybridHandler(model, generator, documents, graph_documents)
    agentic = AgenticGraphRAG(
        [
            _PipelineEvidenceTool("vector", rag),
            _PipelineEvidenceTool("graph", graphrag),
        ],
        generator,
    )
    return {"rag": rag, "graphrag": graphrag, "agentic": _AgenticHandler(agentic)}