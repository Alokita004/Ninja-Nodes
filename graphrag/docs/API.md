# FastAPI Service

The benchmark API is defined in `benchmark/api.py`. It provides health, per-pipeline query, comparison, question analysis, run lookup, and completed agentic trace streaming endpoints. Docker is not required.

## Pipeline Registration

By default, the FastAPI lifespan builds handlers from `SERVER_CONFIG`: it authenticates to the configured TigerGraph graph, loads a bounded snapshot of `Document` vertices, and creates the configured embedding and completion services. Provider embedding and generation calls are deferred until a query; the first vector query computes and caches the document vectors in process. The current runtime caps the graph snapshot at 1,000 documents and fails readiness rather than silently using a partial corpus.

The API does not invent provider configuration or silently return placeholder answers. Tests and alternate deployments can supply configured pipeline handlers to `create_app`. Each handler receives `(question, qtype)` and must return a result with an `answer`; pipeline evidence, citations, metrics, steps, and stop reason are included when available. The agentic handler may also expose `stream(question, qtype)`, yielding `("step", trace_step)` events followed by `("result", final_result)` for live server-sent events.

```python
from benchmark.api import create_app

app = create_app(
    {
        "rag": lambda question, qtype: rag_pipeline.query(question),
        "graphrag": lambda question, qtype: graph_pipeline.query(question, qtype or "lookup"),
        "agentic": lambda question, qtype: agentic_pipeline.investigate(question, qtype or "lookup"),
    }
)
```

Run the service from the GraphMind repository directory with `uvicorn benchmark.api:app --reload`. The module-level app loads the configured pipeline factory during startup. If configuration, dependencies, graph access, or the required graph data are unavailable, `/api/health` reports `ready: false` and query calls return a sanitized `503`.
Run the service without Docker from the GraphMind repository directory with `uvicorn benchmark.api:app --reload`. If runtime initialization fails, `/api/health` reports `ready: false`; query calls return a sanitized `503` response. Supply explicit handlers with `create_app(pipelines=...)` to override automatic configuration.

The local Vite origins `http://localhost:5173` and `http://127.0.0.1:5173` are enabled by default. Set `cors_origins` explicitly when creating the app for other deployments. Pipeline execution has a 60-second default timeout; configure `pipeline_timeout_seconds` as needed.

## Endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/health` | Reports the service and configured pipeline names. |
| `POST` | `/api/query/rag` | Executes the registered Vector RAG handler. |
| `POST` | `/api/query/graphrag` | Executes the registered Hybrid GraphRAG handler. |
| `POST` | `/api/query/agentic` | Executes the registered agentic handler. |
| `POST` | `/api/compare` | Runs each requested question against each selected pipeline and records per-pipeline errors. |
| `POST` | `/api/analyze` | Validates a supplied type against the observed dataset taxonomy; it does not guess a type. |
| `GET` | `/api/runs/{run_id}` | Returns a completed run or `404`. |
| `GET` | `/api/stream/agentic?run_id=...` | Streams the saved steps and result of a completed agentic run as server-sent events. |
| `POST` | `/api/stream/agentic` | Starts an investigation from a JSON query body and streams live steps followed by its result as server-sent events. |
| `GET` | `/api/stream/agentic?run_id=...` | Replays a completed agentic run's steps and result. |

Unavailable handlers return `503`; handler timeouts return `504`; execution or invalid result failures return sanitized `502` responses. Unknown run IDs return `404`. Raw provider exception messages and question text are not written to application logs.