"""Deterministic public-answer judge."""

from __future__ import annotations

import re
from collections.abc import Sequence


def normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def judge_answer(answer: str, expected: Sequence[str]) -> bool:
    actual = normalize_answer(answer)
    return any(actual == normalize_answer(item) for item in expected)