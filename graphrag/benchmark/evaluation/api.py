from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class BenchmarkConfig:
    llm_model: str = "mock-model"
    embedding_model: str = "mock-embedding"
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 3
    temperature: float = 0.0
    max_agent_steps: int = 3
    context_limit: int = 8192


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    pipeline: str
    answer: str
    citations: list[str] = []
    evidence: list[str] = []
    tokens: int = 0
    latency: float = 0.0
    steps: int = 0
    trace: list[dict[str, Any]] = []
    stop_reason: str | None = None
    errors: list[str] = []


def create_app() -> FastAPI:
    app = FastAPI(title="Benchmark evaluation API", version="1.0")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "pipeline": "benchmark"}

    @app.post("/api/query/rag", response_model=QueryResponse)
    def query_rag(payload: QueryRequest) -> dict[str, Any]:
        return {
            "pipeline": "rag",
            "answer": f"RAG answer for: {payload.question}",
            "citations": [],
            "evidence": [],
            "tokens": 0,
            "latency": 0.0,
            "steps": 0,
            "trace": [],
            "stop_reason": "completed",
            "errors": [],
        }

    return app
