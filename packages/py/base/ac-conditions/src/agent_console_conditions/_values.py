"""JSON 값 도구: 경로 해석(RFC 6901), 형식 이름, 엄격한 같음 비교."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, final


@final
class _Missing:
    """경로에 값이 없음을 뜻하는 표식(싱글턴). JSON 값이 아니다."""

    _instance: _Missing | None = None

    def __new__(cls) -> _Missing:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()
"""경로에 값이 없을 때 연산자가 받는 실제 값. 존재를 묻는 연산자가 아니면 거짓으로 다룬다."""


def resolve_pointer(document: Any, pointer: str) -> Any:
    """JSON Pointer(RFC 6901)로 값을 꺼낸다. 없으면 `MISSING`.

    Args:
        document: JSON 호환 값(dict·list·스칼라).
        pointer: `""`(문서 전체) 또는 `/`로 시작하는 경로. `~1` = `/`, `~0` = `~`.

    Returns:
        찾은 값 또는 `MISSING`(경로 형식이 틀렸거나 중간에 값이 없음).
    """
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        return MISSING
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                return MISSING
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                return MISSING
            index = int(token)
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def json_type(value: Any) -> str | None:
    """JSON 형식 이름(null·boolean·integer·number·string·array·object). JSON 값이 아니면 None.

    정수는 `integer`(정수이면서 `number`이기도 하다 — 비교는 `is_number`로).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return "array"
    return None


def is_number(value: Any) -> bool:
    """참거짓을 뺀 숫자(int·float)인지."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def json_equal(a: Any, b: Any) -> bool:
    """JSON 의미의 같음. 숫자는 값으로(1 == 1.0), 참거짓은 숫자와 다르다, 목록·객체는 재귀."""
    if is_number(a) and is_number(b):
        return bool(a == b)
    ta, tb = json_type(a), json_type(b)
    if ta is None or tb is None or ta != tb:
        return False
    if ta == "array":
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b, strict=True))
    if ta == "object":
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return bool(a == b)
