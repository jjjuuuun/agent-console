"""아래 층이 위 층보다 권한·범위를 넓혔는지 찾는다("넓힘" 경고).

어느 위치를 어떻게 비교할지는 데이터다: `checks={포인터: 규칙}` 인자 또는 스키마 주석 `x-widen`.
규칙은 비교기 이름 문자열이거나 `{"kind": 이름, ...매개변수}` 객체다.
기본 비교기:
- `subset`: 목록. 아래 층 유효 목록에 위 층에 없던 원소가 생기면 넓힘.
- `path_subset`: 경로 목록. 새 경로가 위 층 경로와 같거나 그 아래가 아니면 넓힘
  (`\\`는 `/`로, `..`은 정규화해서 비교).
- `order`: 스칼라. `{"kind": "order", "order": [좁음, ..., 넓음]}`에서 뒤쪽으로 가면 넓힘
  (목록에 없는 값은 넓힘으로 본다 — 경고일 뿐이므로 보수적으로).
"""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_settings._pointer import MISSING, get_at, join_pointer
from agent_console_settings._resolve import Layer, Resolved, resolve_layers
from agent_console_settings._schema import schema_annotation
from agent_console_settings._strategies import DEFAULT_STRATEGIES, MergeStrategy

__all__ = [
    "DEFAULT_WIDEN_CHECKS",
    "WIDEN_ANNOTATION",
    "WidenCheck",
    "Widening",
    "find_widenings",
]

WIDEN_ANNOTATION = "x-widen"
"""스키마에서 "넓힘" 비교 규칙을 적는 주석 키."""

WidenCheck = Callable[[Any, Any, Mapping[str, Any]], Sequence[Any]]
"""`(위 층 유효 값, 이 층 적용 후 유효 값, 규칙 매개변수) -> 넓어진 항목들`(비면 넓힘 아님)."""


@dataclass(frozen=True, slots=True)
class Widening:
    """넓힘 하나. 경고용이며 병합 결과는 바꾸지 않는다."""

    pointer: str
    layer: str
    """넓힌 층 id."""
    upper_layer: str | None
    """비교 대상(위 층 유효 값)을 정한 층 id."""
    check: str
    """쓴 비교기 이름."""
    added: tuple[Any, ...]
    """넓어진 항목(새 원소 또는 새 값)."""


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def _subset(upper: Any, lower: Any, params: Mapping[str, Any]) -> Sequence[Any]:
    if not (_is_list(upper) and _is_list(lower)):
        return ()
    return tuple(v for v in lower if v not in upper)


def _norm_path(path: str) -> str:
    text = path.replace("\\", "/")
    normed = posixpath.normpath(text) if text else text
    return normed.rstrip("/") or normed


def _path_subset(upper: Any, lower: Any, params: Mapping[str, Any]) -> Sequence[Any]:
    if not (_is_list(upper) and _is_list(lower)):
        return ()
    bases = [_norm_path(str(u)) for u in upper]
    out = []
    for value in lower:
        path = _norm_path(str(value))
        if not any(path == b or path.startswith(b.rstrip("/") + "/") for b in bases):
            out.append(value)
    return tuple(out)


def _order(upper: Any, lower: Any, params: Mapping[str, Any]) -> Sequence[Any]:
    raw = params.get("order")
    if not isinstance(raw, list | tuple) or upper == lower:
        return ()
    order = list(raw)
    if upper not in order:
        return ()
    if lower not in order or order.index(lower) > order.index(upper):
        return (lower,)
    return ()


DEFAULT_WIDEN_CHECKS: Mapping[str, WidenCheck] = {
    "subset": _subset,
    "path_subset": _path_subset,
    "order": _order,
}
"""기본 비교기 표. 더하려면 새 dict를 만들어 `find_widenings(..., comparators=)`로 넘긴다."""


def _object_pointers(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, kid in value.items():
            at = join_pointer(prefix, str(key))
            yield at
            yield from _object_pointers(kid, at)


def _parse_rule(rule: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(rule, str):
        return rule, {}
    if isinstance(rule, Mapping) and isinstance(rule.get("kind"), str):
        return rule["kind"], rule
    raise ValueError(f"넓힘 규칙 형식이 틀렸습니다: {rule!r}")


def find_widenings(
    layers: Iterable[Layer],
    *,
    checks: Mapping[str, Any] | None = None,
    schema: Mapping[str, Any] | None = None,
    rules: Mapping[str, str] | None = None,
    strategies: Mapping[str, MergeStrategy] = DEFAULT_STRATEGIES,
    comparators: Mapping[str, WidenCheck] = DEFAULT_WIDEN_CHECKS,
) -> list[Widening]:
    """층마다 "그 위 층들의 유효 값"과 "이 층까지 적용한 유효 값"을 비교해 넓힘을 찾는다.

    병합 규칙(`schema`·`rules`·`strategies`)은 `resolve_layers`와 같다 — 교집합 규칙이면 넓어질
    수 없으므로 경고도 나오지 않는다. 위·아래 한쪽이라도 값이 없거나 `null`이면 비교하지 않는다
    (그 경우의 실제 범위는 실행 쪽 안전 기본값이 정한다).

    Args:
        checks: `{JSON Pointer: 규칙}`. 스키마 `x-widen`보다 우선.

    Raises:
        ValueError: 규칙 형식이 틀렸거나 비교기 이름을 모를 때.
    """
    layer_list = list(layers)
    found: list[Widening] = []
    previous: Resolved | None = None
    for index in range(len(layer_list)):
        current = resolve_layers(
            layer_list[: index + 1], schema=schema, rules=rules, strategies=strategies
        )
        layer = layer_list[index]
        if previous is not None and layer.value is not None:
            for pointer in _object_pointers(current.value):
                rule = (checks or {}).get(pointer)
                if rule is None:
                    rule = schema_annotation(schema, pointer, WIDEN_ANNOTATION)
                if rule is None or layer.id not in current.layers_under(pointer):
                    continue
                name, params = _parse_rule(rule)
                comparator = comparators.get(name)
                if comparator is None:
                    raise ValueError(f"모르는 넓힘 비교기입니다: {name!r} ({pointer})")
                before = get_at(previous.value, pointer)
                after = get_at(current.value, pointer)
                if before is MISSING or before is None or after is None:
                    continue
                added = tuple(comparator(before, after, params))
                if added:
                    found.append(
                        Widening(pointer, layer.id, previous.source_of(pointer), name, added)
                    )
        previous = current
    return found
