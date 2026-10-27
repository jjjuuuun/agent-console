"""관측 탭 이벤트 접두어 표(5.5R.13, 패키지 기본 데이터 + 설치자 옵션).

실행 상세 [관측] 탭이 모을 실행 이벤트 ``type`` 접두어(예: ``hook.``·``mcp.``)는 **데이터**다.
기본은 ``data/observe_event_prefixes.json``이고, 설치자 옵션
``modules.options.mod-runs.observe_event_prefixes``로 바꾸거나(목록) 끈다(빈 목록). 실행·이벤트
저장은 이 표를 쓰지 않는다 — 표는 화면이 받을 응답(``GET /observe-event-prefixes``)에만 실린다.

    >>> DEFAULT_OBSERVE_EVENT_PREFIXES
    ('hook.', 'mcp.')
    >>> load_observe_event_prefixes('{"prefixes": ["otel.", "otel.", " "]}')
    ('otel.',)
    >>> observe_event_prefixes_of(None)
    ('hook.', 'mcp.')
    >>> observe_event_prefixes_of([])
    ()
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from importlib.resources import files
from typing import Any

__all__ = [
    "DEFAULT_OBSERVE_EVENT_PREFIXES",
    "load_observe_event_prefixes",
    "observe_event_prefixes_of",
]


def _clean(values: Iterable[Any]) -> tuple[str, ...]:
    """문자열만, 앞뒤 공백 없이, 빈 값·중복 없이(처음 나온 순서)."""
    seen: dict[str, None] = {}
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"관측 이벤트 접두어는 문자열이어야 합니다: {value!r}")
        text = value.strip()
        if text:
            seen.setdefault(text, None)
    return tuple(seen)


def load_observe_event_prefixes(text: str) -> tuple[str, ...]:
    """JSON ``{"prefixes": [...]}`` → 접두어 목록.

    Args:
        text: 표 파일 내용.

    Returns:
        접두어(공백·중복 제거, 순서 유지). ``prefixes``가 없거나 비면 빈 튜플(관측 탭 끔).

    Raises:
        ValueError: JSON이 아니거나(``json.JSONDecodeError``) 모양이 맞지 않을 때.
    """
    data = json.loads(text)
    if not isinstance(data, Mapping):
        raise ValueError("관측 이벤트 접두어 표는 객체여야 합니다")
    prefixes = data.get("prefixes", [])
    if not isinstance(prefixes, list):
        raise ValueError("관측 이벤트 접두어 표의 prefixes는 목록이어야 합니다")
    return _clean(prefixes)


DEFAULT_OBSERVE_EVENT_PREFIXES: tuple[str, ...] = load_observe_event_prefixes(
    files("agent_console_mod_runs")
    .joinpath("data/observe_event_prefixes.json")
    .read_text(encoding="utf-8")
)
"""패키지 기본 데이터(``data/observe_event_prefixes.json``)."""


def observe_event_prefixes_of(option: Iterable[str] | None) -> tuple[str, ...]:
    """설치자 옵션 ``observe_event_prefixes`` → 지금 접두어 목록.

    Args:
        option: None = 패키지 기본(``DEFAULT_OBSERVE_EVENT_PREFIXES``), 목록 = 그 목록
            (빈 목록 = 관측 탭 끔).

    Returns:
        접두어(공백·중복 제거, 순서 유지).
    """
    if option is None:
        return DEFAULT_OBSERVE_EVENT_PREFIXES
    return _clean(option)
