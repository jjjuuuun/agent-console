"""값 다루기: 시각 해석, 문자열화, 크기 제한(`bounded`), JSON 포인터.

agent_bench `log_events.timestamp`·`text`·`bounded`를 옮겨 한도를 인자로 받게 정리했다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel

__all__ = [
    "BOUNDED_DROP_KEYS",
    "BOUNDED_MAX_CHARS",
    "BOUNDED_MAX_ITEMS",
    "BOUNDED_NOTE",
    "JsonValue",
    "bounded",
    "dirty_surrogates",
    "json_pointer",
    "scrub_surrogates",
    "text",
    "timestamp",
]

type JsonValue = Any
"""JSON으로 표현되는 값(dict·list·str·int·float·bool·None). 형식 검사는 하지 않는다."""

BOUNDED_MAX_CHARS = 80_000
"""`bounded` 기본 문자열 한도(agent_bench 그대로)."""

BOUNDED_MAX_ITEMS = 200
"""`bounded` 기본 목록 항목 한도(agent_bench 그대로)."""

BOUNDED_DROP_KEYS: frozenset[str] = frozenset({"encrypted_content", "encryptedContent"})
"""`bounded`가 기본으로 지우는 키(암호화된 추론 본문 등, agent_bench 그대로)."""

BOUNDED_NOTE = "\n[표시용 기록 축약: 원시 로그에 전체 내용 보존]"
"""잘린 문자열 끝에 붙이는 표시(agent_bench 그대로)."""


def timestamp(value: JsonValue) -> float | None:
    """원본 시각을 Unix epoch 초로 바꾼다.

    Args:
        value: 숫자(그대로) 또는 ISO 8601 문자열(`Z` 허용).

    Returns:
        epoch 초. 해석하지 못하면 None(값을 지어내지 않는다). bool은 시각으로 보지 않는다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp()


def text(value: JsonValue) -> str:
    """문자열이면 그대로, 아니면 JSON 문자열(비 ASCII 유지)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def bounded(
    value: JsonValue,
    *,
    max_chars: int = BOUNDED_MAX_CHARS,
    max_items: int = BOUNDED_MAX_ITEMS,
    drop_keys: Collection[str] = BOUNDED_DROP_KEYS,
    note: str = BOUNDED_NOTE,
) -> JsonValue:
    """표시·색인용으로 값 크기를 제한한 사본을 만든다(원본은 바꾸지 않는다).

    - 객체: `drop_keys`의 키를 빼고 값마다 재귀한다.
    - 목록: 앞 `max_items`개만 남긴다.
    - 문자열: `max_chars`자를 넘으면 자르고 `note`를 붙인다.

    Returns:
        제한한 새 값. 스칼라는 그대로.
    """
    if isinstance(value, Mapping):
        return {
            str(k): bounded(
                v, max_chars=max_chars, max_items=max_items, drop_keys=drop_keys, note=note
            )
            for k, v in value.items()
            if k not in drop_keys
        }
    if isinstance(value, list | tuple):
        return [
            bounded(v, max_chars=max_chars, max_items=max_items, drop_keys=drop_keys, note=note)
            for v in list(value)[:max_items]
        ]
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + note
    return value


_MISSING = object()


def json_pointer(document: JsonValue, pointer: str, default: JsonValue = None) -> JsonValue:
    """RFC 6901 JSON 포인터로 값을 꺼낸다(`""` = 문서 전체, `~0`=`~`, `~1`=`/`).

    Args:
        document: 대상 값.
        pointer: `/a/0/b` 형식. `/`로 시작하지 않으면 `default`.
        default: 경로가 없을 때 돌려줄 값.

    Returns:
        찾은 값 또는 `default`. 예외를 내지 않는다.
    """
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        return default
    current: Any = document
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else _MISSING
        else:
            return default
        if current is _MISSING:
            return default
    return current


_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
"""외톨이 서로게이트(U+D800~U+DFFF). Python 문자열 안에서는 짝이 맞아도 따로 남는다."""

REPLACEMENT_CHAR = "\ufffd"
"""외톨이 서로게이트를 바꿀 문자(U+FFFD)."""


_SCALAR_TYPES: frozenset[type] = frozenset({int, float, bool, type(None)})


def _dirty(value: Any) -> bool:
    """값 안에 외톨이 서로게이트가 있는가(새 객체를 만들지 않는 빠른 검사).

    흔한 정확한 타입(str·dict·list·tuple·스칼라)을 먼저 보고, ASCII 문자열은 정규식 없이 넘긴다.
    """
    t = type(value)
    if t is str:
        return not value.isascii() and _LONE_SURROGATE.search(value) is not None
    if t is dict:
        for k, v in value.items():  # noqa: SIM110 - any(제너레이터)보다 빠르다(뜨거운 경로)
            if _dirty(k) or _dirty(v):
                return True
        return False
    if t is list or t is tuple:
        for v in value:  # noqa: SIM110 - 위와 같음
            if _dirty(v):
                return True
        return False
    if t in _SCALAR_TYPES:
        return False
    if isinstance(value, str):
        return _LONE_SURROGATE.search(value) is not None
    if isinstance(value, Mapping):
        return any(_dirty(k) or _dirty(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_dirty(v) for v in value)
    if isinstance(value, BaseModel):
        extra = value.__pydantic_extra__
        return _dirty(value.__dict__) or (extra is not None and _dirty(extra))
    return False


def _scrub(value: Any) -> Any:
    """서로게이트가 있는 값의 정리한 사본(검사는 호출자가 했다)."""
    if isinstance(value, str):
        return _LONE_SURROGATE.sub(REPLACEMENT_CHAR, value)
    if isinstance(value, Mapping):
        return {scrub_surrogates(k): scrub_surrogates(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        out = [scrub_surrogates(v) for v in value]
        return tuple(out) if isinstance(value, tuple) else out
    if isinstance(value, BaseModel):
        return type(value).model_validate(_scrub(value.model_dump(by_alias=True)))
    return value


def scrub_surrogates(value: Any) -> Any:
    """값 안 모든 문자열(객체 키·목록·튜플·pydantic 모델)의 외톨이 서로게이트를 U+FFFD로 바꾼다.

    깨진 UTF-16 원문 등에서 온 서로게이트는 UTF-8로 인코딩되지 않아 JSON 직렬화·SQLite 쓰기·응답
    인코딩이 실패한다. 바꿀 것이 없으면 같은 객체를 돌려준다(원본은 바꾸지 않는다). 먼저 할당 없는
    검사를 하고, 서로게이트가 있는 값만 새로 만든다(정상 데이터의 비용은 훑기 한 번).
    """
    return _scrub(value) if _dirty(value) else value


def dirty_surrogates(value: Any) -> bool:
    """값 안에 외톨이 서로게이트가 있는가(새 객체를 만들지 않는 검사)."""
    return _dirty(value)
