"""설정 스키마(패키지 데이터 `data/*.schema.json`) 읽기. 기본값은 스키마 안의 데이터다."""

from __future__ import annotations

import copy
import json
from functools import cache
from importlib import resources
from typing import Any

__all__ = ["classifier_config_schema", "source_config_schema"]


@cache
def _load(name: str) -> dict[str, Any]:
    text = resources.files(__package__).joinpath("data", name).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):  # pragma: no cover - 패키지 데이터 손상
        raise ValueError(f"{name}: JSON 객체가 아닙니다")
    return value


def source_config_schema() -> dict[str, Any]:
    """`claude-code-jsonl` 출처 설정 스키마(JSON Schema, 기본값 포함)."""
    return copy.deepcopy(_load("source_config.schema.json"))


def classifier_config_schema() -> dict[str, Any]:
    """`claude-code` 분류기 설정 스키마(JSON Schema, 기본값 포함)."""
    return copy.deepcopy(_load("classifier_config.schema.json"))
