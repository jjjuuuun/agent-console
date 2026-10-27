"""테스트 공용 픽스처: 작은 프로필 데이터·이벤트와 빈 레지스트리 묶음."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest

from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_contracts.logs import LogEvent
from agent_console_modkit import ExtensionRegistries

FLOW: dict[str, Any] = {
    "title": "흐름",
    "cells": {
        "ask": {
            "label": "질문",
            "x": 100,
            "y": 60,
            "when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]},
        },
        "work": {
            "label": "작업",
            "x": 400,
            "y": 60,
            "when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]},
            "metrics": ["count", "errors"],
        },
    },
    "edges": [{"id": "hand", "from": "ask", "to": "work", "kind": "structural"}],
    "error_when": {"all": [{"path": "/status", "op": "eq", "value": "failed"}]},
}
"""칸 2개·연결 1개 프로필(문제 0건)."""

BROKEN_REFS: dict[str, Any] = {
    "title": "문제 있음",
    "cells": {"a": {"when": {"all": [{"path": "/x", "op": "no_such_op", "value": 1}]}}},
    "edges": [{"id": "e", "from": "a", "to": "ghost"}],
}
"""형식은 맞지만 검사 문제가 있는 프로필(모르는 연산자, 없는 칸)."""

EVENTS: list[dict[str, Any]] = [
    {"uid": "u1", "seq": 1, "source": "s", "observed_at": 0, "category": "input"},
    {"uid": "u2", "seq": 2, "source": "s", "observed_at": 0, "category": "tool"},
    {
        "uid": "u3",
        "seq": 3,
        "source": "s",
        "observed_at": 0,
        "category": "tool",
        "status": "failed",
    },
    {"uid": "u4", "seq": 4, "source": "s", "observed_at": 0, "category": "note"},
]
"""``EVENTS``를 ``FLOW``로 투영하면 ask 1·work 2(오류 1)·분류 안 됨 1."""


@pytest.fixture
def flow() -> dict[str, Any]:
    """``FLOW`` 사본."""
    return copy.deepcopy(FLOW)


@pytest.fixture
def broken() -> dict[str, Any]:
    """``BROKEN_REFS`` 사본."""
    return copy.deepcopy(BROKEN_REFS)


@pytest.fixture
def event_rows() -> list[dict[str, Any]]:
    """``EVENTS`` 사본(JSON 본문용)."""
    return copy.deepcopy(EVENTS)


@pytest.fixture
def events() -> list[LogEvent]:
    """``EVENTS``를 계약 모델로."""
    return [LogEvent.model_validate(row) for row in EVENTS]


@pytest.fixture
def as_profile() -> Callable[[dict[str, Any]], ArchitectureProfile]:
    """프로필 데이터 → 계약 모델."""
    return ArchitectureProfile.model_validate


@pytest.fixture
def registries() -> ExtensionRegistries:
    """빈 레지스트리 묶음(호스트 기본 묶음과 같은 모양)."""
    return ExtensionRegistries()
