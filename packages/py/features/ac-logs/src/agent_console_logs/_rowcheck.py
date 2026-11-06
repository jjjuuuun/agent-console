"""확장 판정의 행 기준 미리 거르기(선택 능력, 6R.9 M-1).

확장 판정 함수(`EventPredicate`, X28)는 `LogEvent`를 받는다. 색인이 후보 행마다 본문을 읽어
`LogEvent`를 만들면 맞는 행이 드문 범위에서 느리다. 판정 함수가 **색인 열 값만으로** 답할 수 있는
경우가 있으면(예: 이미 판정해 둔 `seq`·`uid`, `source` 값), 이 모듈의 선택 능력을 함께 가진다.

- `row_fields`: 미리 거르기에 쓸 열 이름(`EVENT_ROW_FIELDS` 중에서). `seq`는 늘 들어간다.
  모르는 이름은 매핑에 없다.
- `check_row(row)`: 열 값 매핑 → `True`(맞음 확정), `False`(안 맞음 확정), `None`(모름 — 색인이
  `LogEvent`를 만들어 판정 함수를 부른다).

규칙: `check_row`가 `True`·`False`로 답하면 그 값은 같은 이벤트에 대한 판정 함수 값과 같아야 한다
(결과가 경로에 따라 달라지지 않게). 색인 구현은 이 능력을 쓰지 않아도 된다(메모리 색인은 늘
판정 함수를 부른다). 예외를 내지 않아야 한다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts.logs import LogEvent

__all__ = [
    "EVENT_ROW_FIELDS",
    "EventRow",
    "RowCheck",
    "RowCheckedPredicate",
    "RowPredicate",
    "row_check_of",
]

EVENT_ROW_FIELDS: frozenset[str] = frozenset(
    {
        "seq",
        "uid",
        "source",
        "ref",
        "thread",
        "actor",
        "tool",
        "call_id",
        "stage",
        "category",
        "via",
        "status",
        "session",
        "cwd",
        "repo_root",
        "model",
        "run_id",
        "message_id",
        "time",
        "observed_at",
    }
)
"""미리 거르기에 넘길 수 있는 열 이름. 값은 같은 이름의 `LogEvent` 필드 값과 같다."""

type EventRow = Mapping[str, Any]
"""열 이름 → 값(요청한 `row_fields`와 `seq`만)."""

type RowCheck = Callable[[EventRow], bool | None]
"""열 값 → 맞음(True)·안 맞음(False)·모름(None)."""


@runtime_checkable
class RowPredicate(Protocol):
    """행 기준 미리 거르기를 가진 판정 함수(`EventPredicate`이면서 아래 둘을 가진다)."""

    def __call__(self, event: LogEvent) -> bool: ...

    @property
    def row_fields(self) -> Collection[str]: ...

    def check_row(self, row: EventRow) -> bool | None: ...


@dataclass(frozen=True, slots=True)
class RowCheckedPredicate:
    """판정 함수 + 미리 거르기 묶음(확장 구현이 감싸 쓰는 기본 구현).

    Args:
        event: 이벤트 판정 함수(늘 쓸 수 있는 원래 판정).
        row: 열 값 미리 거르기. `event`와 어긋나지 않아야 한다.
        fields: `row`가 읽는 열 이름(`EVENT_ROW_FIELDS` 중에서).

    Example:
        >>> from agent_console_logs import RowCheckedPredicate
        >>> only = RowCheckedPredicate(
        ...     lambda e: e.source == "a",
        ...     lambda row: row.get("source") == "a",
        ...     frozenset({"source"}),
        ... )
        >>> only.check_row({"seq": 1, "source": "b"})
        False
    """

    event: Callable[[LogEvent], bool]
    row: RowCheck
    fields: frozenset[str]

    def __call__(self, event: LogEvent) -> bool:
        return self.event(event)

    @property
    def row_fields(self) -> Collection[str]:
        return self.fields

    def check_row(self, row: EventRow) -> bool | None:
        return self.row(row)


def row_check_of(predicate: object) -> tuple[frozenset[str], RowCheck] | None:
    """판정 함수의 미리 거르기(열 이름, 함수). 능력이 없으면 None.

    열 이름은 `EVENT_ROW_FIELDS`로 줄이고 `seq`를 더한다.
    """
    check = getattr(predicate, "check_row", None)
    fields = getattr(predicate, "row_fields", None)
    if not callable(check) or fields is None:
        return None
    wanted: Iterable[str] = fields
    return (frozenset(wanted) & EVENT_ROW_FIELDS) | {"seq"}, check
