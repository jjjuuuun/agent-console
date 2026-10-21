"""프리셋 항목 문서 훑기(쓰지 않는다): 항목이 가리키는 값 모으기.

예: 프리셋이 쓰는 실행 백엔드 이름(`backend` 키 값)을 모아 화면 배지를 계산한다(5.2R.6). 키의 뜻은
이 패키지가 모른다 — 호출자가 키 이름을 넘긴다.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from ._apply import PresetItem


def _walk(value: Any, key: str) -> Iterator[str]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == key and isinstance(v, str) and v:
                yield v
            else:
                yield from _walk(v, key)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v, key)


def collect_values(items: Iterable[PresetItem], key: str) -> list[str]:
    """항목 문서 어디에서든 `key`의 문자열 값을 모은다(처음 나온 순서, 중복 없음).

    Args:
        items: `load_items`가 읽은 항목.
        key: 찾을 키 이름(예: ``"backend"``). 값이 문자열이 아니면 그 아래를 계속 훑는다.

    Returns:
        값 목록. 없으면 빈 목록.
    """
    seen: dict[str, None] = {}
    for item in items:
        for value in _walk(item.document, key):
            seen.setdefault(value, None)
    return list(seen)


__all__ = ["collect_values"]
