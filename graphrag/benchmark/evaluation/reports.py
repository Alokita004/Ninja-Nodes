"""JSON report writer for benchmark outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metrics import summarize
from .schemas import BenchmarkRecord


def write_report(path: str | Path, records: list[BenchmarkRecord]) -> dict[str, Any]:
    report = summarize(records)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report