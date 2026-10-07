"""Atomic JSON checkpoint storage for resumable ingestion."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Checkpoint:
    source_path: str
    next_line: int = 1
    processed: int = 0
    loaded: int = 0
    failed: int = 0


class CheckpointStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, source_path: str) -> Checkpoint:
        if not self.path.exists():
            return Checkpoint(source_path=source_path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        checkpoint = Checkpoint(**data)
        if checkpoint.source_path != source_path:
            raise ValueError("checkpoint source_path does not match requested corpus")
        return checkpoint

    def save(self, checkpoint: Checkpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(checkpoint), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)