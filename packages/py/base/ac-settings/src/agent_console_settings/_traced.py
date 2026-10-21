"""출처가 붙은 값 트리(`TracedValue`). 병합 전략이 주고받는 단위다."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_settings._pointer import join_pointer

__all__ = ["TracedValue"]


@dataclass(frozen=True, slots=True, eq=False)
class TracedValue:
    """값 하나와 그 값을 정한 층 id. 객체·목록이면 자식마다 다시 `TracedValue`가 있다.

    - `source`: 이 값(컨테이너면 컨테이너 자체)을 마지막으로 정한 층 id.
      여러 층이 합쳐 만든 컨테이너(객체 병합, 목록 이어 붙이기 등)는 마지막으로 기여한 층이다.
    - `children`: 객체면 `{키: TracedValue}`, 목록이면 `(TracedValue, ...)`, 스칼라면 `None`.

    직접 만들기보다 `stamp`·`object`·`array`를 쓴다(값과 자식이 어긋나지 않게).
    """

    value: Any
    source: str
    children: Mapping[str, TracedValue] | tuple[TracedValue, ...] | None = None

    @classmethod
    def stamp(cls, value: Any, source: str) -> TracedValue:
        """`value` 전체(모든 하위 값 포함)가 한 층 `source`에서 왔다고 표시한다. 값은 복사한다."""
        if isinstance(value, Mapping):
            return cls.object({str(k): cls.stamp(v, source) for k, v in value.items()}, source)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return cls.array([cls.stamp(v, source) for v in value], source)
        return cls(copy.deepcopy(value), source, None)

    @classmethod
    def object(cls, children: Mapping[str, TracedValue], source: str) -> TracedValue:
        """자식들로 객체 값을 만든다. 값은 자식 값에서 계산한다."""
        kids = dict(children)
        return cls({k: c.value for k, c in kids.items()}, source, kids)

    @classmethod
    def array(cls, items: Sequence[TracedValue], source: str) -> TracedValue:
        """원소들로 목록 값을 만든다. 값은 원소 값에서 계산한다."""
        kids = tuple(items)
        return cls([c.value for c in kids], source, kids)

    @property
    def is_object(self) -> bool:
        """객체(자식이 키로 묶임)인가."""
        return isinstance(self.children, Mapping)

    @property
    def is_array(self) -> bool:
        """목록인가."""
        return isinstance(self.children, tuple)

    def child(self, key: str) -> TracedValue | None:
        """객체 자식 하나. 객체가 아니거나 키가 없으면 `None`."""
        if isinstance(self.children, Mapping):
            return self.children.get(key)
        return None

    def items(self) -> tuple[TracedValue, ...]:
        """목록 원소들. 목록이 아니면 빈 튜플."""
        return self.children if isinstance(self.children, tuple) else ()

    def provenance(self, prefix: str = "") -> dict[str, str]:
        """`{JSON Pointer: 층 id}` — 자신(`prefix`)과 모든 하위 위치."""
        out: dict[str, str] = {prefix: self.source}
        if isinstance(self.children, Mapping):
            for key, kid in self.children.items():
                out.update(kid.provenance(join_pointer(prefix, key)))
        elif isinstance(self.children, tuple):
            for index, kid in enumerate(self.children):
                out.update(kid.provenance(join_pointer(prefix, index)))
        return out
