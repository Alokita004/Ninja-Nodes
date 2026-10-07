from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .judge import judge_answer
from .metrics import summarize
from .reports import write_report
from .runner import (
    iter_public_questions,
    run_hidden_benchmark,
    run_public_benchmark as _run_public_benchmark,
)
from .schemas import BenchmarkConfig, BenchmarkRecord


def run_public_benchmark(
    path: str | Path,
    pipeline: str,
    query: Callable[[str, str], Any],
    *,
    output_dir: str | Path | None = None,
    config: BenchmarkConfig | None = None,
) -> dict[str, Any]:
    result = _run_public_benchmark(path, pipeline, query, output_dir=output_dir, config=config)
    records = [
        BenchmarkRecord(
            **{
                **record,
                "citations": tuple(record.get("citations", ())),
                "retrieval_methods": tuple(record.get("retrieval_methods", ())),
            }
        )
        for record in result["records"]
    ]
    return summarize(records)
