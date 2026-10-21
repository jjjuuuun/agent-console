"""병합 전략 인터페이스와 이름 붙은 전략 표.

전략은 "위 층까지 합친 값(`base`) + 이 층 값(`incoming`) → 새 값"을 만드는 함수다. 어느 필드에
어느 전략을 쓸지는 코드가 아니라 데이터(스키마 `x-merge`, 사용자 설정 `settings_merge`)가 정한다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agent_console_settings._traced import TracedValue

__all__ = [
    "DEFAULT_STRATEGIES",
    "MergeContext",
    "MergeIssue",
    "MergeStrategy",
    "StrategyTable",
    "append",
    "default_strategies",
    "intersect",
    "merge",
    "replace",
    "union",
]


@dataclass(frozen=True, slots=True)
class MergeIssue:
    """병합 중 발견한 문제. 병합은 멈추지 않고 대체 동작으로 계속한다.

    - `code`: `unknown_strategy`(표에 없는 전략 이름 → 기본 규칙으로 대체),
      `type_mismatch`(전략이 기대한 형태가 아님 → 교체로 대체) 또는 사용자 전략이 정한 코드.
    """

    code: str
    pointer: str
    layer: str
    message: str


@dataclass(frozen=True, slots=True)
class MergeContext:
    """전략에 넘기는 맥락. 하위 값 병합과 문제 보고를 여기로 한다."""

    layer: str
    """이 층 id."""
    pointer: str
    """병합 중인 위치(JSON Pointer)."""
    _merge_child: Callable[[str, TracedValue | None, Any], TracedValue]
    _report: Callable[[MergeIssue], None]

    def merge_child(self, key: str, base: TracedValue | None, incoming: Any) -> TracedValue:
        """하위 위치 `key`를 그 위치의 규칙(설정·스키마·기본)으로 병합한다."""
        return self._merge_child(key, base, incoming)

    def report(self, code: str, message: str) -> None:
        """문제 하나를 결과의 `issues`에 남긴다."""
        self._report(MergeIssue(code, self.pointer, self.layer, message))


class MergeStrategy(Protocol):
    """병합 전략. `base`는 위 층까지의 값(아직 아무 층도 정하지 않았으면 `None`)."""

    def __call__(
        self, base: TracedValue | None, incoming: Any, ctx: MergeContext, /
    ) -> TracedValue: ...


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def replace(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """교체: 이 층 값이 위 층 값을 통째로 바꾼다(`null`·빈 목록도 그대로 지정)."""
    return TracedValue.stamp(incoming, ctx.layer)


def merge(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """객체 병합: 키별로 재귀 병합한다. 하위 키마다 자기 규칙을 다시 찾는다.

    이 층 값이 객체가 아니면(예: `null`) 교체한다. 위 층 값이 객체가 아니면 빈 객체에서 시작한다.
    """
    if not isinstance(incoming, Mapping):
        return replace(base, incoming, ctx)
    kids: dict[str, TracedValue] = (
        dict(base.children) if base is not None and isinstance(base.children, Mapping) else {}
    )
    for key, value in incoming.items():
        kids[str(key)] = ctx.merge_child(str(key), kids.get(str(key)), value)
    return TracedValue.object(kids, ctx.layer)


def _list_inputs(
    base: TracedValue | None, incoming: Any, ctx: MergeContext, name: str
) -> tuple[tuple[TracedValue, ...] | None, list[Any] | None]:
    """(위 층 목록 원소 또는 None, 이 층 목록 또는 None=교체로 대체)."""
    if not _is_list(incoming):
        if incoming is not None:
            ctx.report("type_mismatch", f"'{name}' 전략은 목록이 필요해 교체로 대체했습니다")
        return None, None
    base_items = base.items() if base is not None and base.is_array else None
    return base_items, list(incoming)


def append(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """이어 붙이기: 위 층 목록 뒤에 이 층 목록을 붙인다(중복 허용). 원소마다 출처가 남는다."""
    base_items, items = _list_inputs(base, incoming, ctx, "append")
    if items is None:
        return replace(base, incoming, ctx)
    new = [TracedValue.stamp(v, ctx.layer) for v in items]
    return TracedValue.array([*(base_items or ()), *new], ctx.layer)


def union(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """합집합: 이어 붙이되 이미 있는 값(==)은 건너뛴다. 기존 원소는 처음 넣은 층 출처를 유지한다."""
    base_items, items = _list_inputs(base, incoming, ctx, "union")
    if items is None:
        return replace(base, incoming, ctx)
    out = list(base_items or ())
    seen = [t.value for t in out]
    for value in items:
        if value not in seen:
            seen.append(value)
            out.append(TracedValue.stamp(value, ctx.layer))
    return TracedValue.array(out, ctx.layer)


def intersect(base: TracedValue | None, incoming: Any, ctx: MergeContext, /) -> TracedValue:
    """교집합: 위 층 목록 중 이 층 목록에도 있는 값만 남긴다(위 층 순서·출처 유지).

    위 층에 목록이 없으면(처음 지정) 이 층 목록을 그대로 쓴다.
    """
    base_items, items = _list_inputs(base, incoming, ctx, "intersect")
    if items is None or base_items is None:
        return replace(base, incoming, ctx)
    return TracedValue.array([t for t in base_items if t.value in items], ctx.layer)


class StrategyTable(Mapping[str, MergeStrategy]):
    """이름 → 전략 표. `register`로 더하고, `freeze()` 뒤에는 바꿀 수 없다.

    모듈 전역 `DEFAULT_STRATEGIES`는 얼어 있다. 전략을 더하려면 `default_strategies()`나
    `copy()`로 새 표를 만들어 등록한 뒤 `resolve_layers(..., strategies=표)`로 넘긴다.
    """

    def __init__(self, strategies: Mapping[str, MergeStrategy] | None = None) -> None:
        self._items: dict[str, MergeStrategy] = dict(strategies or {})
        self._frozen = False

    def register(self, name: str, strategy: MergeStrategy, *, replace: bool = False) -> None:
        """전략 `name`을 등록한다.

        Raises:
            ValueError: 이름이 비었거나, 이미 있는데 `replace=False`일 때.
            RuntimeError: 얼린 표일 때.
        """
        if self._frozen:
            raise RuntimeError("얼린 전략 표에는 등록할 수 없습니다. copy()로 새 표를 만드세요")
        if not name:
            raise ValueError("전략 이름이 비었습니다")
        if name in self._items and not replace:
            raise ValueError(f"이미 등록된 전략입니다: {name!r}")
        self._items[name] = strategy

    def freeze(self) -> StrategyTable:
        """이후 등록을 막고 자신을 돌려준다."""
        self._frozen = True
        return self

    def copy(self) -> StrategyTable:
        """같은 내용의 새(얼지 않은) 표."""
        return StrategyTable(self._items)

    def __getitem__(self, name: str) -> MergeStrategy:
        return self._items[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def default_strategies() -> StrategyTable:
    """기본 전략 5개(`replace`·`merge`·`append`·`union`·`intersect`)가 든 새 표."""
    return StrategyTable(
        {
            "replace": replace,
            "merge": merge,
            "append": append,
            "union": union,
            "intersect": intersect,
        }
    )


DEFAULT_STRATEGIES: Mapping[str, MergeStrategy] = default_strategies().freeze()
"""기본 전략 표(얼어 있음)."""
