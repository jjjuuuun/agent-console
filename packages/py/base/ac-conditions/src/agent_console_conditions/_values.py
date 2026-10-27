"""JSON 값 도구: 경로 해석(RFC 6901), 형식 이름, 엄격한 같음 비교."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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


type _Token = tuple[str, int | None]
"""경로 토큰 하나: (`~` 풀어 쓴 키, 목록 위치로 쓸 수 있으면 그 정수 아니면 None)."""


def _parse_pointer(pointer: str) -> tuple[_Token, ...] | None:
    """`"/a/0"` → 토큰들. `""`(문서 전체) = 빈 튜플, `/`로 시작하지 않으면 None(항상 `MISSING`)."""
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        return None
    tokens: list[_Token] = []
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        index = None
        if token.isdigit() and not (len(token) > 1 and token.startswith("0")):
            try:
                index = int(token)
            except ValueError:  # isdigit()가 참인 위첨자 숫자 등("²") — 목록 위치가 아니다
                index = None
        tokens.append((token, index))
    return tuple(tokens)


def _walk(document: Any, tokens: tuple[_Token, ...]) -> Any:
    current = document
    for token, index in tokens:
        # 흔한 경우(JSON 객체 dict)는 ABC 검사(isinstance Mapping) 없이 먼저 본다
        if type(current) is dict or isinstance(current, Mapping):
            if token not in current:
                return MISSING
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            if index is None or index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def resolve_pointer(document: Any, pointer: str) -> Any:
    """JSON Pointer(RFC 6901)로 값을 꺼낸다. 없으면 `MISSING`.

    Args:
        document: JSON 호환 값(dict·list·스칼라).
        pointer: `""`(문서 전체) 또는 `/`로 시작하는 경로. `~1` = `/`, `~0` = `~`.

    Returns:
        찾은 값 또는 `MISSING`(경로 형식이 틀렸거나 중간에 값이 없음).
    """
    tokens = _parse_pointer(pointer)
    return MISSING if tokens is None else _walk(document, tokens)


def compile_pointer(pointer: str) -> Callable[[Any], Any]:
    """경로를 한 번만 해석해 `document → 값 또는 MISSING` 함수를 만든다(`resolve_pointer`와 같음).

    같은 경로로 많은 문서를 볼 때 쓴다(경로 나누기·`~` 풀기를 문서마다 하지 않는다).

    Args:
        pointer: `resolve_pointer`와 같은 형식.

    Returns:
        문서를 받아 값(없으면 `MISSING`)을 돌려주는 함수.
    """
    tokens = _parse_pointer(pointer)
    if tokens is None:
        return lambda _document: MISSING
    if not tokens:
        return lambda document: document
    if len(tokens) == 1:
        ((token, _index),) = tokens
        whole = tokens

        def one(document: Any) -> Any:
            if type(document) is dict:
                return document.get(token, MISSING)
            return _walk(document, whole)

        return one
    return lambda document: _walk(document, tokens)


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
