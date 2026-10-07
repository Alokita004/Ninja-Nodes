from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from benchmark.evaluation.observability import build_run_metadata
from benchmark.evaluation.observability import build_run_metadata, log_benchmark_event
from benchmark.evaluation.schemas import BenchmarkConfig
from benchmark.runtime import build_configured_pipelines


LOGGER = logging.getLogger(__name__)
PIPELINE_NAMES = ("rag", "graphrag", "agentic")
PipelineHandler = Callable[[str, str | None], Any]


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=20_000)
    qtype: str | None = None
    question_id: str | None = Field(default=None, max_length=128)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question cannot be empty")
        return cleaned


class QueryResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    evidence: list[Any] = Field(default_factory=list)
    pipeline: str
    tokens: int = 0
    latency: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)
    steps: int = 0
    trace: list[Any] = Field(default_factory=list)
    stop_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    run_id: str
    timestamp: str
    configuration_id: str
    configuration_version: int
    question_id: str | None = None


class CompareRequest(BaseModel):
    questions: list[str] = Field(default_factory=list, max_length=50)
    pipelines: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("questions")
    @classmethod
    def validate_questions(cls, values: list[str]) -> list[str]:
        cleaned = [question.strip() for question in values]
        if any(not question for question in cleaned):
            raise ValueError("questions cannot contain empty values")
        return cleaned

    @field_validator("pipelines")
    @classmethod
    def validate_pipelines(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(pipeline.strip().lower() for pipeline in values))
        if any(pipeline not in PIPELINE_NAMES for pipeline in cleaned):
            raise ValueError("pipelines must be rag, graphrag, or agentic")
        return cleaned


class AnalysisRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=20_000)
    qtype: str | None = None

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question cannot be empty")
        return cleaned


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _serializable_result(
    pipeline: str,
    raw_result: Any,
    *,
    elapsed: float,
    metadata: dict[str, Any],
) -> QueryResponse:
    metrics = _value(raw_result, "metrics", {}) or {}
    evidence_container = _value(raw_result, "evidence", []) or []
    evidence_items = _value(evidence_container, "items", evidence_container)
    steps = _value(raw_result, "steps", []) or []
    trace = _value(raw_result, "trace", steps) or []
    insufficient = bool(_value(raw_result, "insufficient_evidence", False))
    answer = _value(raw_result, "answer")
    if not isinstance(answer, str):
        raise ValueError("pipeline result must contain an answer string")

    metric_payload = jsonable_encoder(metrics)
    if not isinstance(metric_payload, dict):
        metric_payload = {}
    token_count = _value(raw_result, "tokens", _value(metrics, "total_tokens", 0))
    latency = _value(raw_result, "latency", _value(metrics, "total_latency_seconds", elapsed))
    step_count = steps if isinstance(steps, int) else len(steps)
    stop_reason = _value(raw_result, "stop_reason")
    if stop_reason is None:
        stop_reason = "insufficient_evidence" if insufficient else "completed"

    payload = {
        "answer": answer,
        "citations": jsonable_encoder(_value(raw_result, "citations", []) or []),
        "evidence": jsonable_encoder(list(evidence_items)),
        "pipeline": pipeline,
        "tokens": int(token_count or 0),
        "latency": float(latency or 0.0),
        "metrics": metric_payload,
        "steps": step_count,
        "trace": jsonable_encoder(list(trace) if not isinstance(trace, int) else []),
        "stop_reason": stop_reason,
        "errors": [],
        **metadata,
    }
    return QueryResponse.model_validate(payload)


def create_app(
    pipelines: Mapping[str, PipelineHandler] | None = None,
    *,
    pipeline_factory: Callable[[], Mapping[str, PipelineHandler]] | None = build_configured_pipelines,
    config: BenchmarkConfig | None = None,
    pipeline_timeout_seconds: float = 60.0,
    cors_origins: Sequence[str] = ("http://localhost:5173", "http://127.0.0.1:5173"),
) -> FastAPI:
    if pipeline_timeout_seconds <= 0:
        raise ValueError("pipeline_timeout_seconds must be positive")
    registered = dict(pipelines or {})
    if set(registered) - set(PIPELINE_NAMES):
        raise ValueError(f"pipeline keys must be selected from {PIPELINE_NAMES}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if pipelines is None and pipeline_factory is not None:
            try:
                configured = await run_in_threadpool(pipeline_factory)
                if not isinstance(configured, Mapping) or set(configured) - set(PIPELINE_NAMES):
                    raise ValueError("pipeline factory returned an invalid registry")
                app.state.pipelines = dict(configured)
            except Exception as error:
                app.state.startup_error = type(error).__name__
                log_benchmark_event(
                    "runtime_initialization_failed",
                    pipeline="benchmark",
                    config=app.state.config,
                    level=logging.ERROR,
                    error_type=type(error).__name__,
                )
        yield

    app = FastAPI(title="GraphMind Benchmark API", version="1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.runs = {}
    app.state.pipelines = registered
    app.state.config = config if config is not None else BenchmarkConfig.load()
    app.state.startup_error = None

    async def execute(pipeline: str, payload: QueryRequest) -> QueryResponse:
        handler = app.state.pipelines.get(pipeline)
        if handler is None:
            error_code = "runtime_not_ready" if app.state.startup_error else "pipeline_unavailable"
            raise HTTPException(status_code=503, detail={"code": error_code, "pipeline": pipeline})

        metadata = build_run_metadata(pipeline, payload.question_id, app.state.config)
        log_benchmark_event(
            "query_started",
            pipeline=pipeline,
            question_id=payload.question_id,
            config=app.state.config,
            run_id=metadata["run_id"],
            timestamp=metadata["timestamp"],
        )
        started = time.perf_counter()
        try:
            if inspect.iscoroutinefunction(handler) or inspect.iscoroutinefunction(getattr(handler, "__call__", None)):
                raw_result = await asyncio.wait_for(
                    handler(payload.question, payload.qtype), timeout=pipeline_timeout_seconds
                )
            else:
                raw_result = await asyncio.wait_for(
                    run_in_threadpool(handler, payload.question, payload.qtype),
                    timeout=pipeline_timeout_seconds,
                )
            result = _serializable_result(
                pipeline,
                raw_result,
                elapsed=time.perf_counter() - started,
                metadata=metadata,
            )
        except asyncio.TimeoutError as error:
            log_benchmark_event(
                "query_timeout", pipeline=pipeline, question_id=payload.question_id,
                config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                level=logging.WARNING, error_type=type(error).__name__,
            )
            raise HTTPException(status_code=504, detail={"code": "pipeline_timeout", "pipeline": pipeline}) from error
        except HTTPException as error:
            log_benchmark_event(
                "query_failed", pipeline=pipeline, question_id=payload.question_id,
                config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                level=logging.WARNING, error_type=type(error).__name__,
            )
            raise HTTPException(status_code=502, detail={"code": "pipeline_failed", "pipeline": pipeline}) from error
        except (ValidationError, TypeError, ValueError) as error:
            log_benchmark_event(
                "query_invalid_result", pipeline=pipeline, question_id=payload.question_id,
                config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                level=logging.WARNING, error_type=type(error).__name__,
            )
            raise HTTPException(status_code=502, detail={"code": "invalid_pipeline_result", "pipeline": pipeline}) from error
        except Exception as error:
            log_benchmark_event(
                "query_failed", pipeline=pipeline, question_id=payload.question_id,
                config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                level=logging.WARNING, error_type=type(error).__name__,
            )
            raise HTTPException(status_code=502, detail={"code": "pipeline_failed", "pipeline": pipeline}) from error

        app.state.runs[result.run_id] = result.model_dump(mode="json")
        log_benchmark_event(
            "query_completed",
            pipeline=pipeline,
            question_id=result.question_id,
            config=app.state.config,
            run_id=result.run_id,
            timestamp=result.timestamp,
            duration_seconds=result.latency,
            evidence_count=len(result.evidence),
            total_tokens=result.tokens,
            agent_steps=result.steps,
            stop_reason=result.stop_reason or "",
        )
        return result

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "benchmark",
            "ready": bool(app.state.pipelines),
            "configured_pipelines": sorted(app.state.pipelines),
            "available_pipelines": list(PIPELINE_NAMES),
            "startup_error": app.state.startup_error,
        }

    @app.post("/api/query/rag", response_model=QueryResponse)
    async def query_rag(payload: QueryRequest) -> QueryResponse:
        return await execute("rag", payload)

    @app.post("/api/query/graphrag", response_model=QueryResponse)
    async def query_graphrag(payload: QueryRequest) -> QueryResponse:
        return await execute("graphrag", payload)

    @app.post("/api/query/agentic", response_model=QueryResponse)
    async def query_agentic(payload: QueryRequest) -> QueryResponse:
        return await execute("agentic", payload)

    @app.post("/api/compare")
    async def compare(payload: CompareRequest) -> dict[str, Any]:
        pipelines_to_run = payload.pipelines or list(PIPELINE_NAMES)
        results: list[dict[str, Any]] = []
        for question in payload.questions:
            for pipeline in pipelines_to_run:
                request = QueryRequest(question=question)
                try:
                    result = await execute(pipeline, request)
                    results.append({"question": question, "pipeline": pipeline, "status": "ok", "result": result})
                except HTTPException as error:
                    detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
                    results.append({"question": question, "pipeline": pipeline, "status": "error", "errors": [detail]})
        return {"question_count": len(payload.questions), "pipelines": pipelines_to_run, "results": results}

    @app.post("/api/analyze")
    def analyze(payload: AnalysisRequest) -> dict[str, Any]:
        observed_types = {"aggregation", "lookup", "multi_hop", "superlative", "temporal"}
        if payload.qtype is not None and payload.qtype not in observed_types:
            raise HTTPException(status_code=422, detail="qtype is not in the observed dataset taxonomy")
        return {
            "question": payload.question,
            "classification": payload.qtype,
            "pipeline": "rag",
            "needs_graph": payload.qtype in {"aggregation", "multi_hop", "superlative", "temporal"}
            if payload.qtype is not None
            else None,
        }

    @app.get("/api/runs/{run_id}", response_model=QueryResponse)
    def get_run(run_id: str) -> dict[str, Any]:
        run = app.state.runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    def replay_agentic(run_id: str) -> StreamingResponse:
        run = app.state.runs.get(run_id)
        if run is None or run["pipeline"] != "agentic":
            raise HTTPException(status_code=404, detail="agentic run not found")

        async def replay_events():
            for step in run["trace"]:
                yield f"event: step\ndata: {json.dumps(step, ensure_ascii=False)}\n\n"
            yield f"event: result\ndata: {json.dumps(run, ensure_ascii=False)}\n\n"

        return StreamingResponse(replay_events(), media_type="text/event-stream")

    @app.get("/api/stream/agentic")
    def stream_agentic_replay(run_id: str) -> StreamingResponse:
        return replay_agentic(run_id)

    @app.post("/api/stream/agentic")
    async def stream_agentic_live(request: QueryRequest) -> StreamingResponse:
        handler = app.state.pipelines.get("agentic")
        stream_handler = getattr(handler, "stream", None)
        if not callable(stream_handler):
            raise HTTPException(
                status_code=503,
                detail={"code": "live_stream_unavailable", "pipeline": "agentic"},
            )

        metadata = build_run_metadata("agentic", request.question_id, app.state.config)
        started = time.perf_counter()
        log_benchmark_event(
            "agentic_stream_started",
            pipeline="agentic",
            question_id=request.question_id,
            config=app.state.config,
            run_id=metadata["run_id"],
            timestamp=metadata["timestamp"],
        )

        async def live_events():
            iterator = iter(stream_handler(request.question, request.qtype or "lookup"))
            final_emitted = False

            def next_event():
                try:
                    return next(iterator)
                except StopIteration:
                    return None

            while True:
                try:
                    item = await asyncio.wait_for(
                        run_in_threadpool(next_event), timeout=pipeline_timeout_seconds
                    )
                except asyncio.TimeoutError:
                    log_benchmark_event(
                        "agentic_stream_timeout", pipeline="agentic", question_id=request.question_id,
                        config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                        level=logging.WARNING,
                    )
                    yield f"event: error\ndata: {{\"code\":\"pipeline_timeout\"}}\n\n"
                    return
                except Exception:
                    log_benchmark_event(
                        "agentic_stream_failed", pipeline="agentic", question_id=request.question_id,
                        config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                        level=logging.WARNING,
                    )
                    yield f"event: error\ndata: {{\"code\":\"pipeline_failed\"}}\n\n"
                    return

                if item is None:
                    break
                event_name, event_payload = item
                if event_name == "step":
                    encoded = json.dumps(jsonable_encoder(event_payload), ensure_ascii=False)
                    yield f"event: step\ndata: {encoded}\n\n"
                elif event_name == "result":
                    try:
                        result = _serializable_result(
                            "agentic",
                            event_payload,
                            elapsed=time.perf_counter() - started,
                            metadata=metadata,
                        )
                    except Exception:
                        log_benchmark_event(
                            "agentic_stream_invalid_result",
                            pipeline="agentic",
                            question_id=request.question_id,
                            config=app.state.config,
                            run_id=metadata["run_id"],
                            timestamp=metadata["timestamp"],
                            level=logging.WARNING,
                        )
                        yield f"event: error\ndata: {{\"code\":\"invalid_pipeline_result\"}}\n\n"
                        return
                    app.state.runs[result.run_id] = result.model_dump(mode="json")
                    log_benchmark_event(
                        "agentic_stream_completed",
                        pipeline="agentic",
                        question_id=result.question_id,
                        config=app.state.config,
                        run_id=result.run_id,
                        timestamp=result.timestamp,
                        duration_seconds=result.latency,
                        evidence_count=len(result.evidence),
                        total_tokens=result.tokens,
                        agent_steps=result.steps,
                        stop_reason=result.stop_reason or "",
                    )
                    encoded = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: result\ndata: {encoded}\n\n"
                    final_emitted = True
                    break
                else:
                    log_benchmark_event(
                        "agentic_stream_invalid_event", pipeline="agentic", question_id=request.question_id,
                        config=app.state.config, run_id=metadata["run_id"], timestamp=metadata["timestamp"],
                        level=logging.WARNING,
                    )
                    yield f"event: error\ndata: {{\"code\":\"invalid_stream_event\"}}\n\n"
                    return

            if not final_emitted:
                yield f"event: error\ndata: {{\"code\":\"missing_final_result\"}}\n\n"

        return StreamingResponse(live_events(), media_type="text/event-stream")

    return app


app = create_app()
