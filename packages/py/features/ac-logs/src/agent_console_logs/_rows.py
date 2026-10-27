"""목록 이벤트를 모델 없이 JSON 행(dict)으로 읽기(design §5.5R.10 `[5.5R.36]`).

`LogIndex.query_events`는 쪽마다 이벤트를 계약 모델(`LogEvent`)로 만든다. 범위 전체를 읽어 판정·
집계만 하는 쪽(예: 구조도)은 모델이 필요 없고, 모델을 만드는 비용(JSON 해석 + 검증 + 다시 덤프)이
가장 크다. 여기 API는 같은 쪽을 **행**으로 준다.

- 행(`LogEventRow`) = 같은 쪽의 `LogEvent`를 `model_dump(mode="json", by_alias=True)`한 것과 같은
  dict다(키는 계약 별칭 — `from` 등, 목록이라 `detail`·`raw`는 None). 차등 테스트가 지킨다.
- 색인 구현은 선택 능력 `LogEventRowReader.query_event_rows`로 빠른 길을 낸다(SQLite는 저장된 본문
  JSON에 기본값만 채운다). 능력이 없는 색인은 `query_event_rows`가 `query_events` 결과를 덤프한다
  (결과는 같고 느리다).
- 행은 읽기 전용으로 쓴다(값 목록·객체는 새로 만들지만 고쳐 쓰는 것을 전제하지 않는다).
"""

from __future__ import annotations

import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, Union, get_args, get_origin, runtime_checkable

from pydantic import BaseModel, TypeAdapter

from agent_console_contracts.logs import LogEvent

from ._filter import LogFilter, QueryContext
from ._index import LogIndex

__all__ = [
    "LogEventRow",
    "LogEventRowPage",
    "LogEventRowReader",
    "PageCallback",
    "complete_event_row",
    "event_row",
    "iter_event_rows",
    "page_rows",
    "query_event_rows",
]

type LogEventRow = dict[str, Any]
"""목록 이벤트 하나의 JSON 행(`LogEvent.model_dump(mode="json", by_alias=True)`와 같은 dict)."""


@dataclass(frozen=True, slots=True)
class LogEventRowPage:
    """`query_events`의 행 판(키셋 쪽, 전체 수 없음).

    Attributes:
        rows: 이 쪽의 행(필터 순서).
        next_cursor: 다음 쪽 커서(`LogEventPage.next_cursor`와 같다). None = 끝.
    """

    rows: list[LogEventRow] = field(default_factory=list)
    next_cursor: str | None = None


type PageCallback = Callable[[int], None]
"""쪽을 하나 읽을 때마다 그 쪽의 행 수로 부르는 함수(측정·진행 표시용)."""


@runtime_checkable
class LogEventRowReader(Protocol):
    """색인의 선택 능력: 목록 쪽을 모델 없이 행으로 준다.

    `query_event_rows(flt, ctx)`의 결과는 같은 인자의 `query_events(flt, ctx)`를 행으로 바꾼 것과
    같아야 한다(행 수·순서·값·커서). `iter_event_rows`는 `flt.cursor`부터 끝까지 같은 행을 차례로
    낸다.
    """

    def query_event_rows(self, flt: LogFilter, ctx: QueryContext) -> LogEventRowPage:
        """목록 쪽(행)."""
        ...

    def iter_event_rows(
        self, flt: LogFilter, ctx: QueryContext, *, on_page: PageCallback | None = None
    ) -> Iterator[LogEventRow]:
        """`flt.cursor`부터 끝까지 행을 하나씩(`flt.limit`개씩 읽는다). 구현은 쪽의 행을 한꺼번에
        만들지 않아도 된다(큰 범위에서 메모리·GC 부담을 줄인다)."""
        ...


def event_row(event: LogEvent) -> LogEventRow:
    """이벤트 → 행(목록 모양: `detail`·`raw`는 None)."""
    row = event.model_dump(mode="json", by_alias=True)
    row["detail"] = None
    row["raw"] = None
    return row


# ---------------------------------------------------------------- 기본값 채우기


def _nested_model(annotation: Any) -> tuple[type[BaseModel], bool] | None:
    """필드 형식이 모델(또는 모델 목록)이면 (모델, 목록인지). 아니면 None."""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        found = [a for a in get_args(annotation) if a is not type(None)]
        return _nested_model(found[0]) if len(found) == 1 else None
    if origin is list:
        args = get_args(annotation)
        inner = _nested_model(args[0]) if args else None
        return (inner[0], True) if inner is not None and not inner[1] else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation, False
    return None


class _RowShape:
    """모델 하나의 JSON 행 모양: 기본값(바꿀 수 없는 값·새로 만들 값)과 안쪽 모델."""

    def __init__(self, model: type[BaseModel]) -> None:
        self.template: dict[str, Any] = {}
        known: set[str] = set()
        lists: list[str] = []
        dicts: list[str] = []
        other: list[tuple[str, Any]] = []
        nested: list[tuple[str, _RowShape, bool]] = []
        for name, info in model.model_fields.items():
            key = info.serialization_alias or info.alias or name
            known.add(key)
            inner = _nested_model(info.annotation)
            if inner is not None:
                nested.append((key, _RowShape(inner[0]), inner[1]))
            if info.is_required():
                continue
            default = info.get_default(call_default_factory=True)
            # 모델이 덤프하는 것과 같은 JSON 값(필드 형식으로 덤프)
            value = TypeAdapter(info.annotation or Any).dump_python(default, mode="json")
            self.template[key] = value
            if value == [] and type(value) is list:
                lists.append(key)
            elif value == {} and type(value) is dict:
                dicts.append(key)
            elif isinstance(value, list | dict):
                other.append((key, value))
        self.known = frozenset(known)
        self.lists = tuple(lists)
        self.dicts = tuple(dicts)
        self.other = tuple(other)
        self.nested = tuple(nested)

    def fill(self, data: dict[str, Any]) -> dict[str, Any]:
        """기본값을 뺀 JSON(`exclude_defaults`) → 모든 필드가 있는 JSON. 모르는 키는 버린다."""
        row = self.template.copy()
        row.update(data)
        # 기본 목록·객체는 행마다 새것(행끼리 같은 객체를 나눠 쓰지 않는다)
        for key in self.lists:
            if key not in data:
                row[key] = []
        for key in self.dicts:
            if key not in data:
                row[key] = {}
        for key, value in self.other:
            if key not in data:
                row[key] = _deep(value)
        if not data.keys() <= self.known:
            for key in data.keys() - self.known:
                del row[key]
        for key, shape, many in self.nested:
            value = row.get(key)
            if not value:
                continue
            if many and type(value) is list:
                row[key] = [shape.fill(v) if type(v) is dict else v for v in value]
            elif not many and type(value) is dict:
                row[key] = shape.fill(value)
        return row


def _deep(value: Any) -> Any:
    if isinstance(value, list):
        return [_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: _deep(v) for k, v in value.items()}
    return value


_EVENT_SHAPE = _RowShape(LogEvent)


def complete_event_row(data: dict[str, Any], *, seq: int | None = None) -> LogEventRow:
    """기본값을 뺀 이벤트 JSON(`model_dump_json(by_alias=True, exclude_defaults=True)`) → 행.

    빠진 필드에 기본값을 채우고(안쪽 모델 포함) 모르는 키를 버린다. 형식 검증은 하지 않는다 —
    `LogEvent`가 쓴 JSON을 읽을 때만 쓴다(그때 결과는 `event_row(LogEvent.model_validate(data))`와
    같다). 필수 필드가 빠졌으면 그 키는 행에 없다.

    Args:
        data: 이벤트 JSON 객체(그대로 고치지 않는다).
        seq: 주면 `seq`를 이 값으로 둔다(색인은 본문 밖에 순번을 둔다).
    """
    row = _EVENT_SHAPE.fill(data)
    if seq is not None:
        row["seq"] = seq
    return row


# ---------------------------------------------------------------- 읽기


def query_event_rows(index: LogIndex, flt: LogFilter, ctx: QueryContext) -> LogEventRowPage:
    """목록 쪽 하나를 행으로 읽는다(능력이 있으면 빠른 길, 없으면 `query_events` + 덤프).

    Args:
        index: 로그 색인(아무 구현).
        flt: 필터(`limit`·`cursor`·`order` 포함).
        ctx: 질의 맥락(`query_events`와 같음).

    Raises:
        LogQueryError: `query_events`와 같은 경우.
    """
    if isinstance(index, LogEventRowReader):
        return index.query_event_rows(flt, ctx)
    page = index.query_events(flt, ctx)
    return LogEventRowPage(rows=[event_row(e) for e in page.items], next_cursor=page.next_cursor)


def iter_event_rows(
    index: LogIndex,
    flt: LogFilter,
    ctx: QueryContext,
    *,
    on_page: PageCallback | None = None,
) -> Iterator[LogEventRow]:
    """필터 결과를 `flt.cursor`부터 끝까지 행으로 읽는다(`flt.limit`개씩 쪽 넘김).

    능력(`LogEventRowReader`)이 있으면 색인의 것을 쓴다(SQLite는 쪽의 본문만 읽어 두고 행은 하나씩
    만든다). 없으면 `query_event_rows`로 쪽마다 읽는다.

    Args:
        index: 로그 색인(아무 구현).
        flt: 필터.
        ctx: 질의 맥락.
        on_page: 쪽을 읽을 때마다 그 쪽의 행 수로 부른다.

    Raises:
        LogQueryError: `query_events`와 같은 경우.
    """
    if isinstance(index, LogEventRowReader):
        yield from index.iter_event_rows(flt, ctx, on_page=on_page)
        return
    yield from page_rows(lambda f: query_event_rows(index, f, ctx), flt, on_page=on_page)


def page_rows(
    read: Callable[[LogFilter], LogEventRowPage],
    flt: LogFilter,
    *,
    on_page: PageCallback | None = None,
) -> Iterator[LogEventRow]:
    """쪽 읽기 함수로 `flt.cursor`부터 끝까지 행을 낸다(색인 구현이 `iter_event_rows`를 쪽 읽기로
    만들 때 쓴다).

    Args:
        read: 필터(커서 포함) → 행 쪽.
        flt: 필터.
        on_page: 쪽을 읽을 때마다 그 쪽의 행 수로 부른다.
    """
    cursor = flt.cursor
    while True:
        page = read(flt.with_(cursor=cursor))
        if on_page is not None:
            on_page(len(page.rows))
        yield from page.rows
        if page.next_cursor is None or not page.rows:
            return
        cursor = page.next_cursor
