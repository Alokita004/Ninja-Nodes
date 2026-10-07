from __future__ import annotations

import asyncio

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from benchmark.api import create_app
from benchmark.evaluation.judge import judge_answer
from benchmark.evaluation.metrics import summarize
from benchmark.evaluation.observability import build_run_metadata, config_hash, log_benchmark_event
from benchmark.evaluation.reports import write_report
from benchmark.evaluation.runner import run_hidden_benchmark, run_public, run_public_benchmark
from benchmark.evaluation.schemas import BenchmarkConfig
from benchmark.evidence.models import Evidence, EvidenceSet


def result(answer="5"):
    evidence = SimpleNamespace(items=[1])
    metrics = SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3, total_latency_seconds=0.01)
    return SimpleNamespace(answer=answer, evidence=evidence, citations=("d1",), metrics=metrics)


def test_runner_judges_public_records_and_reports(tmp_path: Path) -> None:
    dataset = tmp_path / "public.jsonl"
    dataset.write_text("\n".join(json.dumps({"qid": f"q{i}", "question": "q", "qtype": "lookup", "answer": ["5"]}) for i in range(2)) + "\n", encoding="utf-8")
    records = run_public(dataset, "fake", lambda question, qtype: result())
    assert len(records) == 2
    assert all(record.correct for record in records)
    report = write_report(tmp_path / "report.json", records)
    assert report["record_count"] == 2
    assert report["accuracy"] == 1.0


def test_runner_records_pipeline_failures() -> None:
    dataset = Path(__file__).parent / "failure-case.jsonl"
    dataset.write_text(json.dumps({"qid": "q1", "question": "q", "qtype": "lookup", "answer": ["5"]}) + "\n", encoding="utf-8")
    try:
        records = run_public(dataset, "fake", lambda *_: (_ for _ in ()).throw(TimeoutError("late")))
    finally:
        dataset.unlink(missing_ok=True)
    assert records[0].error == "TimeoutError: late"
    assert records[0].empty_retrieval is True


def test_judge_and_summary() -> None:
    assert judge_answer(" Chen Ding ", ["Chen Ding"])
    summary = summarize([])
    assert summary["record_count"] == 0


def test_runner_collects_shared_quality_retrieval_and_agent_metrics(tmp_path: Path) -> None:
    dataset = tmp_path / "public.jsonl"
    dataset.write_text(json.dumps({"qid": "q1", "question": "q", "qtype": "lookup", "answer": ["5", "five"], "gold_doc_ids": ["d1", "d2"]}) + "\n", encoding="utf-8")
    evidence = EvidenceSet.from_items([
        Evidence("e1", "d1", "text", "vector"),
        Evidence("e2", "other", "text", "graph_document"),
    ])
    trace = [
        SimpleNamespace(tool="vector", tokens=2, latency_seconds=0.01),
        SimpleNamespace(tool="graph", tokens=1, latency_seconds=0.02),
    ]
    response = SimpleNamespace(
        answer="5",
        evidence=evidence,
        citations=("d1",),
        metrics=SimpleNamespace(input_tokens=4, output_tokens=2, total_tokens=6, retrieval_latency_seconds=0.03, generation_latency_seconds=0.04, total_latency_seconds=0.07),
        steps=trace,
        tool_calls=("vector", "graph"),
        stop_reason="synthesized",
    )
    records = run_public(dataset, "agentic", lambda *_: response)
    row = records[0]
    assert row.correct is True
    assert row.completeness == 0.5
    assert row.retrieval_precision == 0.5
    assert row.retrieval_recall == 0.5
    assert row.reciprocal_rank == 1.0
    assert row.citation_precision == 1.0
    assert row.agent_steps == 2
    assert row.tool_calls == 2
    assert row.strategy_changes == 1
    assert row.retrieval_methods == ("vector", "graph_document")
    summary = summarize(records)
    assert summary["mrr"] == 1.0
    assert summary["average_retrieval_latency_seconds"] == 0.03


def test_public_benchmark_bundle_writes_public_outputs(tmp_path: Path) -> None:
    dataset = tmp_path / "public.jsonl"
    dataset.write_text(
        "\n".join(
            json.dumps({"qid": f"q{i}", "question": "q", "qtype": "lookup", "answer": ["5"]}) for i in range(2)
        )
        + "\n",
        encoding="utf-8",
    )
    public_dir = tmp_path / "results" / "public"
    config = BenchmarkConfig(
        llm_model="mock-model",
        embedding_model="mock-embedding",
        chunk_size=512,
        chunk_overlap=64,
        top_k=3,
        temperature=0.0,
        max_agent_steps=3,
        context_limit=8192,
    )
    bundle = None
    for pipeline in ("rag", "graphrag", "agentic"):
        bundle = run_public_benchmark(dataset, pipeline, lambda question, qtype: result(), output_dir=public_dir, config=config)
    assert bundle["record_count"] == 2
    assert bundle["run_id"].startswith("agentic-")
    assert bundle["configuration_id"] == config_hash(config)
    assert bundle["configuration_version"] == config.configuration_version
    assert bundle["config"]["judge"] == config.judge
    assert all(record["run_id"] == bundle["run_id"] for record in bundle["records"])
    assert all(record["question_id"] == record["qid"] for record in bundle["records"])
    assert all(record["configuration_id"] == bundle["configuration_id"] for record in bundle["records"])
    assert (public_dir / "rag_results.json").exists()
    assert (public_dir / "comparison.json").exists()
    assert (public_dir / "metrics.json").exists()
    comparison = json.loads((public_dir / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["question_ids_match"] is True
    assert comparison["configuration_match"] is True
    assert set(comparison["pipelines"]) == {"rag", "graphrag", "agentic"}


def test_legacy_benchmark_wrapper_preserves_run_metadata(tmp_path: Path) -> None:
    from benchmark.evaluation.benchmark import run_public_benchmark as legacy_run

    dataset = tmp_path / "public.jsonl"
    dataset.write_text(
        json.dumps({"qid": "q-legacy", "question": "q", "qtype": "lookup", "answer": ["5"]}) + "\n",
        encoding="utf-8",
    )
    summary = legacy_run(dataset, "rag", lambda *_: result(), config=BenchmarkConfig())
    record = summary["records"][0]
    assert record["question_id"] == "q-legacy"
    assert record["run_id"].startswith("rag-")
    assert record["configuration_id"] == config_hash(BenchmarkConfig())
    assert record["configuration_version"] == 1


def test_comparison_rejects_different_pipeline_configurations(tmp_path: Path) -> None:
    dataset = tmp_path / "public.jsonl"
    dataset.write_text(json.dumps({"qid": "q1", "question": "q", "qtype": "lookup", "answer": ["5"]}) + "\n", encoding="utf-8")
    output_dir = tmp_path / "results"
    run_public_benchmark(dataset, "rag", lambda *_: result(), output_dir=output_dir, config=BenchmarkConfig())
    with pytest.raises(ValueError, match="configurations differ"):
        run_public_benchmark(dataset, "agentic", lambda *_: result(), output_dir=output_dir, config=BenchmarkConfig(llm_model="different-model"))


def test_hidden_benchmark_creates_submission_records(tmp_path: Path) -> None:
    dataset = tmp_path / "hidden.jsonl"
    dataset.write_text(
        "\n".join(json.dumps({"qid": "eval-001", "question": "Who won?", "qtype": "lookup"}) for _ in range(2)) + "\n",
        encoding="utf-8",
    )
    output = run_hidden_benchmark(
        dataset,
        "agentic",
        lambda question, qtype: result(answer="No answer"),
        output_dir=tmp_path,
    )
    assert output["record_count"] == 2
    assert output["configuration_id"]
    assert output["configuration_version"] == 1
    assert all("qid" in payload for payload in output["records"])
    assert all("answer" in payload for payload in output["records"])
    assert all(payload["question_id"] == payload["qid"] for payload in output["records"])
    assert all(payload["run_id"] == output["run_id"] for payload in output["records"])


def test_run_metadata_includes_configuration_and_timestamps() -> None:
    config = BenchmarkConfig(
        llm_model="gemini-1.5-flash",
        embedding_model="text-embedding-004",
        chunk_size=512,
        chunk_overlap=64,
        top_k=3,
        temperature=0.0,
        max_agent_steps=4,
        context_limit=8192,
    )
    metadata = build_run_metadata("rag", "q-001", config)
    assert metadata["pipeline"] == "rag"
    assert metadata["question_id"] == "q-001"
    assert metadata["run_id"].startswith("rag-")
    assert metadata["configuration_id"] == config_hash(config)
    assert metadata["configuration_version"] == config.configuration_version
    assert "T" in metadata["timestamp"]
    assert metadata["timestamp"].endswith("Z")


def test_config_hash_changes_when_version_or_judge_changes() -> None:
    baseline = BenchmarkConfig()
    assert config_hash(baseline) != config_hash(BenchmarkConfig(configuration_version=2))
    assert config_hash(baseline) != config_hash(BenchmarkConfig(judge={"method": "other"}))


def test_structured_event_logging_excludes_unapproved_details(caplog: pytest.LogCaptureFixture) -> None:
    config = BenchmarkConfig()
    with caplog.at_level(logging.INFO, logger="benchmark.evaluation.observability"):
        payload = log_benchmark_event(
            "query_completed",
            pipeline="rag",
            question_id="q-1",
            config=config,
            run_id="rag-fixed-run",
            question_text="private question content",
            credential_value="private credential",
            total_tokens=5,
            error_type="RuntimeError",
        )

    record = next(record for record in caplog.records if record.getMessage() == "benchmark_event")
    assert record.run_id == "rag-fixed-run"
    assert record.configuration_id == payload["configuration_id"]
    assert record.configuration_version == 1
    assert record.event == "query_completed"
    assert record.details == {"total_tokens": 5, "error_type": "RuntimeError"}
    assert "private question content" not in caplog.text
    assert "private credential" not in caplog.text


def test_api_executes_registered_pipeline_and_retrieves_runs(caplog: pytest.LogCaptureFixture) -> None:
    def rag_handler(question: str, qtype: str | None) -> SimpleNamespace:
        assert question == "what is the answer?"
        assert qtype is None
        return SimpleNamespace(
            answer="The answer is 5.",
            citations=("doc-1",),
            evidence=EvidenceSet.from_items([Evidence("ev-1", "doc-1", "The answer is 5.", "vector")]),
            metrics=SimpleNamespace(total_tokens=7, total_latency_seconds=0.02),
            steps=(),
        )

    client = TestClient(create_app({"rag": rag_handler}))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["configured_pipelines"] == ["rag"]

    with caplog.at_level(logging.INFO, logger="benchmark.evaluation.observability"):
        response = client.post("/api/query/rag", json={"question": " what is the answer? ", "question_id": "q-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline"] == "rag"
    assert payload["answer"] == "The answer is 5."
    assert payload["citations"] == ["doc-1"]
    assert payload["evidence"][0]["document_id"] == "doc-1"
    assert payload["tokens"] == 7
    assert payload["question_id"] == "q-1"
    assert payload["run_id"].startswith("rag-")
    assert payload["configuration_id"]
    assert payload["configuration_version"] == 1
    assert payload["timestamp"].endswith("Z")
    completion_log = next(
        record for record in caplog.records
        if getattr(record, "event", None) == "query_completed" and record.run_id == payload["run_id"]
    )
    assert completion_log.configuration_id == payload["configuration_id"]
    assert completion_log.question_id == "q-1"
    assert "what is the answer?" not in caplog.text
    assert client.get(f"/api/runs/{payload['run_id']}").json() == payload
    assert client.get("/api/runs/unknown-run").status_code == 404

    invalid = client.post("/api/query/rag", json={"question": "   "})
    assert invalid.status_code == 422

    compare = client.post("/api/compare", json={"questions": ["what is the answer?"], "pipelines": ["rag", "graphrag"]})
    assert compare.status_code == 200
    body = compare.json()
    assert body["question_count"] == 1
    assert body["results"][0]["status"] == "ok"
    assert body["results"][1]["status"] == "error"
    assert body["results"][1]["errors"][0]["code"] == "pipeline_unavailable"


def test_api_pipeline_factory_registers_handlers_on_startup() -> None:
    def rag_handler(question: str, qtype: str | None) -> SimpleNamespace:
        return SimpleNamespace(answer="configured answer")

    client = TestClient(create_app(pipeline_factory=lambda: {"rag": rag_handler}))
    with client:
        health = client.get("/api/health").json()
        assert health["ready"] is True
        assert health["configured_pipelines"] == ["rag"]
        response = client.post("/api/query/rag", json={"question": "test?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "configured answer"


def test_api_reports_pipeline_failure_without_leaking_exception() -> None:
    def failing_handler(question: str, qtype: str | None) -> None:
        raise RuntimeError("private provider detail")

    client = TestClient(create_app({"rag": failing_handler}))
    response = client.post("/api/query/rag", json={"question": "test?"})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "pipeline_failed"
    assert "private provider detail" not in response.text


def test_api_timeout_and_malformed_input() -> None:
    async def slow_handler(question: str, qtype: str | None) -> SimpleNamespace:
        await asyncio.sleep(0.05)
        return SimpleNamespace(answer="late result")

    client = TestClient(create_app({"rag": slow_handler}, pipeline_timeout_seconds=0.001))
    timed_out = client.post("/api/query/rag", json={"question": "test?"})
    assert timed_out.status_code == 504
    assert timed_out.json()["detail"]["code"] == "pipeline_timeout"
    assert client.post("/api/query/rag", json={"question": 42}).status_code == 422


def test_api_preserves_insufficient_evidence_result() -> None:
    def empty_handler(question: str, qtype: str | None) -> SimpleNamespace:
        return SimpleNamespace(answer="INSUFFICIENT_EVIDENCE", evidence=EvidenceSet.from_items([]), citations=(), insufficient_evidence=True)

    client = TestClient(create_app({"rag": empty_handler}))
    response = client.post("/api/query/rag", json={"question": "unsupported?"})
    assert response.status_code == 200
    assert response.json()["answer"] == "INSUFFICIENT_EVIDENCE"
    assert response.json()["stop_reason"] == "insufficient_evidence"
    assert response.json()["evidence"] == []


def test_api_streams_agentic_trace_for_completed_run() -> None:
    trace = [{"step_id": 1, "tool": "vector"}]

    def agentic_handler(question: str, qtype: str | None) -> SimpleNamespace:
        return SimpleNamespace(answer="Grounded answer", citations=["doc-1"], evidence=[], steps=trace, stop_reason="synthesized")

    client = TestClient(create_app({"agentic": agentic_handler}))
    query = client.post("/api/query/agentic", json={"question": "test?"})
    run_id = query.json()["run_id"]
    stream = client.get("/api/stream/agentic", params={"run_id": run_id})
    assert stream.status_code == 200
    assert "event: step" in stream.text
    assert '"tool": "vector"' in stream.text
    assert "event: result" in stream.text
    assert client.get("/api/stream/agentic", params={"run_id": "missing"}).status_code == 404


def test_api_streams_live_agentic_steps_and_final_result() -> None:
    class StreamingAgent:
        def __call__(self, question: str, qtype: str | None) -> SimpleNamespace:
            return SimpleNamespace(answer="Grounded answer")

        def stream(self, question: str, qtype: str):
            assert question == "live question"
            assert qtype == "lookup"
            yield "step", {"step_id": 1, "tool": "vector"}
            yield "result", SimpleNamespace(
                answer="Grounded answer",
                evidence=[],
                citations=["doc-1"],
                steps=[{"step_id": 1, "tool": "vector"}],
                stop_reason="synthesized",
            )

    client = TestClient(create_app({"agentic": StreamingAgent()}))
    stream = client.post("/api/stream/agentic", json={"question": "live question"})
    assert stream.status_code == 200
    assert "event: step" in stream.text
    assert '"tool": "vector"' in stream.text
    assert "event: result" in stream.text
    assert "Grounded answer" in stream.text