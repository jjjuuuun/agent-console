"""질의 확장(X27·X28) 예제 구현이자 테스트용 가짜.

- `TableScopeKind`: 값 → (세션, run_id) 표로 범위를 푼다(표에 없는 값은 `ValueError`).
- `FieldFilter`: 필터 이름 하나의 값과 이벤트 필드(`thread`·`tool` 등 문자열 속성) 하나를 비교한다.
  값 `!`로 시작하면 "그 값이 아님"이다. 본문 판정 예로 `detail_key`를 주면 `detail`에 그 키가
  있는 이벤트만 맞는다. `row_check=True`면 판정 함수가 행 기준 미리 거르기(`RowPredicate`, 6R.9)도
  가진다(본문 판정이 없을 때만 — 비교 필드가 색인 열이므로 열 값만으로 답한다).

등록은 포트(`logs.scope_kinds`·`logs.filter_predicates`)나 `LogQueryExtensions.collect`로 한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from agent_console_contracts.logs import LogEvent, LogFilterFieldInfo
from agent_console_logs._extend import LogFilterContext
from agent_console_logs._filter import EventPredicate, LogScope
from agent_console_logs._rowcheck import EVENT_ROW_FIELDS, EventRow, RowCheckedPredicate

__all__ = ["FieldFilter", "TableScopeKind"]


@dataclass(frozen=True, slots=True)
class TableScopeKind:
    """표 기반 범위 종류(`scope=<id>:<값>`).

    Args:
        id: 종류 이름.
        table: 값 → (세션들, run_id들).
    """

    id: str
    table: Mapping[str, tuple[Iterable[str], Iterable[str]]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def resolve(self, value: str) -> LogScope:
        self.calls.append(value)
        if value not in self.table:
            raise ValueError(f"모르는 값: {value}")
        sessions, run_ids = self.table[value]
        return LogScope.of(sessions, run_ids)


@dataclass(frozen=True, slots=True)
class FieldFilter:
    """이벤트 필드 비교 필터(이름 `name`, 선택 `detail_key`).

    Args:
        name: 필터 이름.
        attribute: 비교할 `LogEvent` 문자열 속성 이름.
        detail_key: 주면 이름 `<name>_has`도 받는다(값 `1` = `detail`에 이 키가 있음).
        row_check: 참이면 행 기준 미리 거르기를 함께 준다(`attribute`가 `EVENT_ROW_FIELDS`이고
            본문 판정을 쓰지 않을 때).
    """

    name: str
    attribute: str
    detail_key: str | None = None
    row_check: bool = False

    @property
    def fields(self) -> Sequence[LogFilterFieldInfo]:
        out = [LogFilterFieldInfo(id=self.name, title=self.name, multi=True)]
        if self.detail_key is not None:
            out.append(LogFilterFieldInfo(id=f"{self.name}_has", title=f"{self.name} 본문"))
        return out

    def build(
        self, values: Mapping[str, tuple[str, ...]], context: LogFilterContext
    ) -> EventPredicate:
        del context
        wanted = values.get(self.name, ())
        keep = frozenset(v for v in wanted if not v.startswith("!"))
        drop = frozenset(v[1:] for v in wanted if v.startswith("!"))
        has = values.get(f"{self.name}_has", ())
        if has and has != ("1",):
            raise ValueError("값은 1만 받습니다")
        key = self.detail_key if has else None
        attribute = self.attribute

        def same(value: str) -> bool:
            return not (keep and value not in keep) and value not in drop

        def check(event: LogEvent) -> bool:
            if not same(str(getattr(event, attribute, "") or "")):
                return False
            if key is not None:
                return isinstance(event.detail, dict) and key in event.detail
            return True

        if not self.row_check or key is not None or attribute not in EVENT_ROW_FIELDS:
            return check

        def check_row(row: EventRow) -> bool | None:
            return same(str(row.get(attribute) or ""))

        return RowCheckedPredicate(check, check_row, frozenset({attribute}))
