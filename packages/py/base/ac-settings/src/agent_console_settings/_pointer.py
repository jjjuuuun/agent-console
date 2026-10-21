"""JSON Pointer(RFC 6901) 도우미와 층 편집(`set_at`·`unset_at`).

층 값은 JSON 형태(dict·list·스칼라)라고 가정한다. 편집 함수는 입력을 바꾸지 않고 새 값을 돌려준다.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, Final

__all__ = [
    "MISSING",
    "PointerError",
    "escape_token",
    "get_at",
    "join_pointer",
    "set_at",
    "split_pointer",
    "unescape_token",
    "unset_at",
]


class _Missing:
    """값이 없음 표식(`None`은 "null로 지정함"이라 구분한다). 인스턴스는 `MISSING` 하나."""

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()
"""`get_at`이 값을 찾지 못했을 때 돌려주는 표식."""


class PointerError(ValueError):
    """잘못된 JSON Pointer이거나, 경로 중간이 컨테이너가 아니어서 따라갈 수 없을 때."""


def escape_token(token: str) -> str:
    """키 하나를 포인터 조각으로 바꾼다(`~` → `~0`, `/` → `~1`)."""
    return token.replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    """포인터 조각 하나를 키로 되돌린다(`~1` → `/`, `~0` → `~`)."""
    return token.replace("~1", "/").replace("~0", "~")


def split_pointer(pointer: str) -> list[str]:
    """`"/a/b~1c"` → `["a", "b/c"]`. 빈 문자열은 루트(`[]`).

    Raises:
        PointerError: 비어 있지 않은데 `/`로 시작하지 않을 때.
    """
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PointerError(f"JSON Pointer는 '/'로 시작해야 합니다: {pointer!r}")
    return [unescape_token(t) for t in pointer[1:].split("/")]


def join_pointer(base: str, *tokens: str | int) -> str:
    """`join_pointer("/a", "b/c", 0)` → `"/a/b~1c/0"`."""
    return base + "".join("/" + escape_token(str(t)) for t in tokens)


def _list_index(token: str, size: int, *, allow_end: bool) -> int:
    if allow_end and token == "-":
        return size
    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
        raise PointerError(f"목록 위치가 아닙니다: {token!r}")
    index = int(token)
    if index > size or (index == size and not allow_end):
        raise PointerError(f"목록 범위를 벗어났습니다: {token!r}")
    return index


def get_at(doc: Any, pointer: str, default: Any = MISSING) -> Any:
    """`doc`에서 `pointer` 위치의 값을 꺼낸다. 없으면 `default`(기본 `MISSING`)."""
    node = doc
    for token in split_pointer(pointer):
        if isinstance(node, Mapping):
            if token not in node:
                return default
            node = node[token]
        elif isinstance(node, Sequence) and not isinstance(node, str | bytes):
            if not token.isdigit() or int(token) >= len(node):
                return default
            node = node[int(token)]
        else:
            return default
    return node


def set_at(doc: Mapping[str, Any] | None, pointer: str, value: Any) -> Any:
    """`doc` 복사본의 `pointer` 위치에 `value`를 넣어 돌려준다("이 층에서 덮어쓰기").

    중간 객체가 없으면 빈 객체를 만든다. 목록 안은 기존 위치 또는 `-`(끝에 추가)만 허용한다.
    루트(`""`)를 지정하면 `value` 복사본을 그대로 돌려준다.

    Raises:
        PointerError: 경로 중간이 객체·목록이 아니거나 목록 위치가 잘못됐을 때.
    """
    tokens = split_pointer(pointer)
    if not tokens:
        return copy.deepcopy(value)
    root: Any = copy.deepcopy(dict(doc)) if doc is not None else {}
    node = root
    for depth, token in enumerate(tokens):
        last = depth == len(tokens) - 1
        if isinstance(node, dict):
            if last:
                node[token] = copy.deepcopy(value)
            else:
                if token not in node:
                    node[token] = {}
                node = node[token]
        elif isinstance(node, list):
            index = _list_index(token, len(node), allow_end=last)
            if last:
                if index == len(node):
                    node.append(copy.deepcopy(value))
                else:
                    node[index] = copy.deepcopy(value)
            else:
                node = node[index]
        else:
            where = join_pointer("", *tokens[:depth])
            raise PointerError(f"{where or '루트'} 위치가 객체·목록이 아니어서 따라갈 수 없습니다")
    return root


def unset_at(doc: Mapping[str, Any] | None, pointer: str, *, prune: bool = True) -> dict[str, Any]:
    """`doc` 복사본에서 `pointer` 위치를 지워 돌려준다("상속으로 되돌리기").

    값이 없으면 변경 없이 복사본을 돌려준다(여러 번 불러도 같다).
    `prune=True`(기본)이면 이 삭제로 비게 된 상위 객체도 지운다 — 빈 객체가 남으면 그 층이
    "빈 값으로 지정함"이 되어, 교체 규칙에서는 위 층 값을 지워 버리기 때문이다.

    Raises:
        PointerError: 루트를 지우려 할 때, 또는 포인터 형식이 틀렸을 때.
    """
    tokens = split_pointer(pointer)
    if not tokens:
        raise PointerError("루트는 지울 수 없습니다(층 전체를 비우려면 빈 객체를 쓰세요)")
    root: dict[str, Any] = copy.deepcopy(dict(doc)) if doc is not None else {}
    path: list[tuple[Any, str]] = []
    node: Any = root
    for token in tokens[:-1]:
        if isinstance(node, dict) and token in node:
            path.append((node, token))
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            path.append((node, token))
            node = node[int(token)]
        else:
            return root
    last = tokens[-1]
    if isinstance(node, dict) and last in node:
        del node[last]
    elif isinstance(node, list) and last.isdigit() and int(last) < len(node):
        del node[int(last)]
    else:
        return root
    if prune:
        for parent, token in reversed(path):
            child = parent[token] if isinstance(parent, dict) else parent[int(token)]
            if isinstance(child, dict) and not child and isinstance(parent, dict):
                del parent[token]
            else:
                break
    return root
