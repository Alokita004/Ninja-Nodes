"""Streaming public benchmark runner."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from .judge import judge_answer, normalize_answer
from .metrics import summarize
from .observability import build_run_metadata, config_snapshot, log_benchmark_event
from .schemas import BenchmarkConfig, BenchmarkRecord


def _items(value: Any) -> tuple[Any, ...]:
    value = getattr(value, "items", value)
    try:
        return tuple(value) if value is not None else ()
    except TypeError:
        return ()


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return (str(value),)


def _unsupported_claim_rate(answer: str) -> float:
    claims = [part.strip() for part in re.split(r"(?<=[.!?])\s+", answer.strip()) if part.strip()]
    if not claims:
        return 0.0
    unsupported = sum(not re.search(r"\[[A-Za-z0-9_.:-]+\]", claim) for claim in claims)
    return unsupported / len(claims)


def iter_public_questions(path: str | Path) -> Iterator[dict[str, Any]]:
    dataset_path = Path(path)
    if not dataset_path.exists() or dataset_path.is_dir() or dataset_path.suffix.lower() != ".jsonl":
        return
    with dataset_path.open("r", encoding="utf-8-sig") as handle:
        for line, raw in enumerate(handle, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if not isinstance(record, dict):
                raise ValueError(f"{dataset_path}:{line}: question must be an object")
            yield record


def run_public(
    path: str | Path,
    pipeline: str,
    query: Callable[[str, str], Any],
    *,
    config: BenchmarkConfig | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> list[BenchmarkRecord]:
    effective_config = config if config is not None else BenchmarkConfig.load()
    run_context = run_metadata or build_run_metadata(pipeline, config=effective_config)
    started = time.perf_counter()
    log_benchmark_event(
        "benchmark_started",
        pipeline=pipeline,
        config=effective_config,
        run_id=run_context["run_id"],
        timestamp=run_context["timestamp"],
    )
    results: list[BenchmarkRecord] = []
    for record in iter_public_questions(path):
        qid = str(record["qid"])
        record_metadata = {
            "run_id": run_context["run_id"],
            "timestamp": run_context["timestamp"],
            "configuration_id": run_context["configuration_id"],
            "configuration_version": run_context["configuration_version"],
            "question_id": qid,
        }
        try:
            result = query(str(record["question"]), str(record["qtype"]))
            answer = str(result.answer)
            evidence = _items(getattr(result, "evidence", ()))
            evidence_ids = tuple(str(item.document_id) for item in evidence if getattr(item, "document_id", None))
            citations = _strings(getattr(result, "citations", ()))
            metrics = getattr(result, "metrics", None)
            steps = _items(getattr(result, "steps", ()))
            tool_calls = _strings(getattr(result, "tool_calls", ()))
            trace_tools = tuple(str(getattr(step, "tool", "")) for step in steps if getattr(step, "tool", ""))
            gold_ids = set(_strings(record.get("gold_doc_ids", ())))
            retrieved_set = set(evidence_ids)
            cited_set = set(citations)
            valid_citations = cited_set & retrieved_set
            expected = _strings(record.get("answer", ()))
            normalized_answer = normalize_answer(answer)
            completeness = sum(normalize_answer(value) in normalized_answer for value in expected) / len(expected) if expected else 0.0
            retrieval_precision = len(retrieved_set & gold_ids) / len(evidence_ids) if evidence_ids else 0.0
            retrieval_recall = len(retrieved_set & gold_ids) / len(gold_ids) if gold_ids else 0.0
            reciprocal_rank = next((1.0 / rank for rank, document_id in enumerate(evidence_ids, 1) if document_id in gold_ids), 0.0) if gold_ids else 0.0
            citation_precision = len(valid_citations) / len(citations) if citations else 0.0
            citation_recall = len(valid_citations) / len(retrieved_set) if retrieved_set else 0.0
            step_latencies = [float(getattr(step, "latency_seconds", 0.0)) for step in steps]
            retrieval_latency = float(getattr(metrics, "retrieval_latency_seconds", sum(step_latencies)))
            generation_latency = float(getattr(metrics, "generation_latency_seconds", 0.0))
            total_latency = float(getattr(metrics, "total_latency_seconds", retrieval_latency + generation_latency))
            input_tokens = int(getattr(metrics, "input_tokens", sum(int(getattr(step, "tokens", 0)) for step in steps)))
            output_tokens = int(getattr(metrics, "output_tokens", len(answer.split())))
            total_tokens = int(getattr(metrics, "total_tokens", input_tokens + output_tokens))
            evidence_count = len(evidence) if evidence else int(getattr(metrics, "retrieved_chunks", 0))
            results.append(BenchmarkRecord(
                qid=qid,
                pipeline=pipeline,
                answer=answer,
                citations=citations,
                evidence_count=evidence_count,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_seconds=total_latency,
                correct=judge_answer(answer, expected),
                completeness=completeness,
                grounding=citation_precision,
                retrieval_precision=retrieval_precision,
                retrieval_recall=retrieval_recall,
                reciprocal_rank=reciprocal_rank,
                citation_precision=citation_precision,
                citation_recall=citation_recall,
                evidence_coverage=citation_recall,
                unsupported_claim_rate=_unsupported_claim_rate(answer),
                retrieval_latency_seconds=retrieval_latency,
                generation_latency_seconds=generation_latency,
                agent_steps=len(steps),
                tool_calls=len(tool_calls) if tool_calls else len(trace_tools),
                strategy_changes=sum(left != right for left, right in zip(trace_tools, trace_tools[1:])),
                retrieval_methods=tuple(dict.fromkeys(str(getattr(item, "retrieval_method", "")) for item in evidence if getattr(item, "retrieval_method", ""))),
                stop_reason=getattr(result, "stop_reason", None),
                empty_retrieval=evidence_count == 0,
                **record_metadata,
            ))
        except Exception as error:
            results.append(BenchmarkRecord(
                qid, pipeline, "", (), 0, 0, 0, 0, 0.0, False,
                f"{type(error).__name__}: {error}", empty_retrieval=True,
                **record_metadata,
            ))
            log_benchmark_event(
                "question_failed",
                pipeline=pipeline,
                question_id=qid,
                config=effective_config,
                run_id=run_context["run_id"],
                timestamp=run_context["timestamp"],
                level=logging.WARNING,
                error_type=type(error).__name__,
            )
        else:
            log_benchmark_event(
                "question_completed",
                pipeline=pipeline,
                question_id=qid,
                config=effective_config,
                run_id=run_context["run_id"],
                timestamp=run_context["timestamp"],
                total_tokens=results[-1].total_tokens,
                evidence_count=results[-1].evidence_count,
                agent_steps=results[-1].agent_steps,
            )
    log_benchmark_event(
        "benchmark_completed",
        pipeline=pipeline,
        config=effective_config,
        run_id=run_context["run_id"],
        timestamp=run_context["timestamp"],
        level=logging.INFO,
        record_count=len(results),
        duration_seconds=time.perf_counter() - started,
    )
    return results


def run_public_benchmark(
    path: str | Path,
    pipeline: str,
    query: Callable[[str, str], Any],
    *,
    output_dir: str | Path | None = None,
    config: BenchmarkConfig | None = None,
) -> dict[str, Any]:
    config = config if config is not None else BenchmarkConfig.load()
    run_metadata = build_run_metadata(pipeline, config=config)
    records = run_public(path, pipeline, query, config=config, run_metadata=run_metadata)
    summary = {
        "record_count": len(records),
        "pipeline": pipeline,
        **run_metadata,
        "config": config_snapshot(config),
        "records": [record.__dict__ for record in records],
    }
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{pipeline}_results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_comparison_reports(out_dir)
    return summary


def _write_comparison_reports(output_dir: Path) -> None:
    pipeline_records: dict[str, list[BenchmarkRecord]] = {}
    shared_config: dict[str, Any] | None = None
    question_ids: tuple[str, ...] | None = None
    for result_path in sorted(output_dir.glob("*_results.json")):
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        config = payload.get("config")
        if not isinstance(config, dict):
            raise ValueError(f"{result_path}: benchmark result is missing its configuration")
        if shared_config is None:
            shared_config = config
        elif config != shared_config:
            raise ValueError("pipeline result configurations differ; fair comparison is not possible")
        pipeline = str(payload.get("pipeline", result_path.name.removesuffix("_results.json")))
        normalized_records = []
        for item in payload.get("records", []):
            values = dict(item)
            values["citations"] = tuple(values.get("citations", ()))
            values["retrieval_methods"] = tuple(values.get("retrieval_methods", ()))
            normalized_records.append(BenchmarkRecord(**values))
        current_ids = tuple(record.qid for record in normalized_records)
        if question_ids is None:
            question_ids = current_ids
        elif current_ids != question_ids:
            raise ValueError("pipeline result question IDs differ; fair comparison is not possible")
        pipeline_records[pipeline] = normalized_records

    summaries = {name: summarize(records) for name, records in sorted(pipeline_records.items())}
    comparison = {
        "record_count": len(question_ids or ()),
        "question_ids_match": True,
        "configuration_match": True,
        "config": shared_config,
        "pipelines": summaries,
    }
    metrics = {
        "record_count": len(question_ids or ()),
        "config": shared_config,
        "pipelines": {
            name: {key: value for key, value in summary.items() if key != "records"}
            for name, summary in summaries.items()
        },
    }
    (output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_hidden_benchmark(
    path: str | Path,
    pipeline: str,
    query: Callable[[str, str], Any],
    *,
    output_dir: str | Path | None = None,
    config: BenchmarkConfig | None = None,
) -> dict[str, Any]:
    config = config if config is not None else BenchmarkConfig.load()
    run_metadata = build_run_metadata(pipeline, config=config)
    started = time.perf_counter()
    log_benchmark_event(
        "hidden_benchmark_started",
        pipeline=pipeline,
        config=config,
        run_id=run_metadata["run_id"],
        timestamp=run_metadata["timestamp"],
    )
    records: list[dict[str, Any]] = []
    for record in iter_public_questions(path):
        qid = str(record["qid"])
        response = query(str(record["question"]), str(record.get("qtype", "lookup")))
        payload = {
            "qid": qid,
            "question_id": qid,
            "pipeline": pipeline,
            "run_id": run_metadata["run_id"],
            "timestamp": run_metadata["timestamp"],
            "configuration_id": run_metadata["configuration_id"],
            "configuration_version": run_metadata["configuration_version"],
            "answer": str(response.answer),
            "citations": list(getattr(response, "citations", ())),
            "tokens": int(getattr(getattr(response, "metrics", None), "total_tokens", 0)),
            "latency": float(getattr(getattr(response, "metrics", None), "total_latency_seconds", 0.0)),
        }
        records.append(payload)
        log_benchmark_event(
            "hidden_question_completed",
            pipeline=pipeline,
            question_id=qid,
            config=config,
            run_id=run_metadata["run_id"],
            timestamp=run_metadata["timestamp"],
            total_tokens=payload["tokens"],
        )
    log_benchmark_event(
        "hidden_benchmark_completed",
        pipeline=pipeline,
        config=config,
        run_id=run_metadata["run_id"],
        timestamp=run_metadata["timestamp"],
        record_count=len(records),
        duration_seconds=time.perf_counter() - started,
    )
    output = {
        "record_count": len(records),
        **run_metadata,
        "config": config_snapshot(config),
        "records": records,
    }
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{pipeline}_hidden_submission.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output