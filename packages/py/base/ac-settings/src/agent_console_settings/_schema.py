"""JSON Schema에서 위치별 주석(`x-merge`, `x-widen` 등)을 찾는다.

`properties`·`additionalProperties`·`items`·`prefixItems`를 따라 내려가고, `$ref`(같은 문서 안
`#/...`)와 `anyOf`·`oneOf`·`allOf`를 펼친다(Pydantic이 만드는 `Optional[Model]` 형태 포함).
필드 이름은 코드에 없다 — 스키마가 데이터다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_settings._pointer import get_at, split_pointer

__all__ = ["schema_annotation"]

_COMBINATORS = ("anyOf", "oneOf", "allOf")
_MAX_DEPTH = 32


def _expand(node: Any, root: Mapping[str, Any], seen: frozenset[str], depth: int) -> list[Any]:
    """`node`와, `$ref`·조합자로 닿는 하위 스키마들(앞에서부터 가까운 순)."""
    if not isinstance(node, Mapping) or depth > _MAX_DEPTH:
        return []
    out: list[Any] = [node]
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#") and ref not in seen:
        target = get_at(root, ref[1:], None)
        out.extend(_expand(target, root, seen | {ref}, depth + 1))
    for key in _COMBINATORS:
        branches = node.get(key)
        if isinstance(branches, list):
            for branch in branches:
                out.extend(_expand(branch, root, seen, depth + 1))
    return out


def _step(nodes: list[Any], token: str, root: Mapping[str, Any]) -> list[Any]:
    out: list[Any] = []
    for node in nodes:
        for sub in _expand(node, root, frozenset(), 0):
            props = sub.get("properties")
            if isinstance(props, Mapping) and token in props:
                out.append(props[token])
                continue
            extra = sub.get("additionalProperties")
            if isinstance(extra, Mapping):
                out.append(extra)
            if token.isdigit():
                prefix = sub.get("prefixItems")
                if isinstance(prefix, list) and int(token) < len(prefix):
                    out.append(prefix[int(token)])
                elif isinstance(sub.get("items"), Mapping):
                    out.append(sub["items"])
    return out


def schema_annotation(schema: Mapping[str, Any] | None, pointer: str, key: str) -> Any:
    """`schema`에서 값 위치 `pointer`에 해당하는 하위 스키마의 주석 `key` 값. 없으면 `None`.

    속성 자리의 스키마(예: `{"anyOf": [...], "x-merge": "intersect"}`)를 먼저 보고, 그다음
    `$ref`·조합자로 닿는 스키마(예: `$defs/Limits`의 주석)를 본다.
    """
    if not schema:
        return None
    nodes: list[Any] = [schema]
    for token in split_pointer(pointer):
        nodes = _step(nodes, token, schema)
        if not nodes:
            return None
    for node in nodes:
        for sub in _expand(node, schema, frozenset(), 0):
            if key in sub:
                return sub[key]
    return None
