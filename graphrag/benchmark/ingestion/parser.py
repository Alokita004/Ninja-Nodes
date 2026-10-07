"""Streaming corpus parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .validator import validate_document_record


def iter_documents(path: str | Path, *, start_line: int = 1) -> Iterator[tuple[int, dict[str, Any]]]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            if line_number < start_line:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(f"{file_path}:{line_number}: malformed JSON: {error.msg}") from error
            try:
                yield line_number, validate_document_record(record)
            except ValueError as error:
                raise ValueError(f"{file_path}:{line_number}: {error}") from error