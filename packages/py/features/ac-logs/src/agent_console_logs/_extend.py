"""로그 질의 확장 지점: 범위 종류(X27)·필터 확장(X28) (design §5.5R.5).

- 범위 종류(`LogScopeKind`): 필터 `scope=<종류>:<값>`을 세션·run_id 합집합(`LogScope`)으로 푼다.
  예: `run`·`run-tree`(실행 기록 연동이 등록).
- 필터 확장(`LogFilterExtension`): 필터 이름 묶음(`fields`)의 값으로 이벤트 판정 함수를 만든다.
  예: `arch`·`arch_group`·`arch_sources`(구조도 연동이 등록).

`LogQueryExtensions`가 등록 묶음을 들고 필터 읽기(`parse`)·풀기(`refine`)·스키마(`fields`)를 한다.
등록이 하나도 없으면 질의는 지금과 같다(풀 것이 없으면 맥락을 바꾸지 않는다). 색인 구현은 풀린
맥락(`QueryContext.scope`·`predicates`)만 보고 이 모듈을 모른다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable

from agent_console_contracts.logs import LogFilterFieldInfo, LogQuerySchema

from ._filter import (
    FILTER_FIELDS,
    EventPredicate,
    LogFilter,
    LogQueryError,
    LogScope,
    QueryContext,
    parse_log_filter,
    query_schema,
)
from ._values import JsonValue

__all__ = [
    "LogFilterContext",
    "LogFilterExtension",
    "LogQueryExtensions",
    "LogScopeKind",
]

_BUILTIN_NAMES = frozenset(f.id for f in FILTER_FIELDS)


@runtime_checkable
class LogScopeKind(Protocol):
    """범위 종류 하나(X27, 포트 `logs.scope_kinds`).

    Attributes:
        id: 종류 이름(`scope=<id>:<값>`의 앞부분, `:`를 넣지 않는다).
    """

    @property
    def id(self) -> str: ...

    def resolve(self, value: str) -> LogScope:
        """값 → 세션·run_id 합집합. 값이 틀리면 `ValueError`(422로 바뀐다)."""
        ...


@dataclass(frozen=True, slots=True)
class LogFilterContext:
    """판정 함수를 만들 때 넘기는 맥락: 질의 필터 전체와 질의 맥락(오류 범주 등)."""

    filter: LogFilter
    query: QueryContext


@runtime_checkable
class LogFilterExtension(Protocol):
    """필터 확장 하나(X28, 포트 `logs.filter_predicates`).

    Attributes:
        fields: 이 확장이 받는 필터 이름과 표시 정보(`GET /logs/schema`의 filters에 실린다).
    """

    @property
    def fields(self) -> Sequence[LogFilterFieldInfo]: ...

    def build(
        self, values: Mapping[str, tuple[str, ...]], context: LogFilterContext
    ) -> EventPredicate:
        """필터에 온 자기 이름들의 값(하나 이상) → 이벤트 판정 함수. 값이 틀리면 `ValueError`."""
        ...


@dataclass(frozen=True, slots=True)
class LogQueryExtensions:
    """등록된 범위 종류·필터 확장 묶음.

    `collect`로 만들면 겹치는 이름을 앞의 것만 남기고 `skipped`에 사유를 남긴다.
    """

    scope_kinds: Mapping[str, LogScopeKind] = field(default_factory=dict)
    filters: tuple[LogFilterExtension, ...] = ()
    skipped: tuple[str, ...] = ()

    @classmethod
    def collect(
        cls,
        scope_kinds: Iterable[LogScopeKind] = (),
        filters: Iterable[LogFilterExtension] = (),
    ) -> LogQueryExtensions:
        """등록 목록 → 묶음. 같은 종류 id·필터 이름은 먼저 온 것이 이기고, 기본 필터 이름과 겹치는
        확장은 뺀다(사유는 `skipped`)."""
        kinds: dict[str, LogScopeKind] = {}
        skipped: list[str] = []
        for kind in scope_kinds:
            kid = str(kind.id)
            if not kid or ":" in kid:
                skipped.append(f"범위 종류 id가 틀렸습니다: {kid!r}")
            elif kid in kinds:
                skipped.append(f"범위 종류 {kid}가 이미 등록됐습니다")
            else:
                kinds[kid] = kind
        taken: set[str] = set(_BUILTIN_NAMES)
        kept: list[LogFilterExtension] = []
        for ext in filters:
            names = [f.id for f in ext.fields]
            clash = sorted(taken.intersection(names))
            if not names or clash:
                skipped.append(f"필터 확장 이름이 비었거나 겹칩니다: {', '.join(clash) or '-'}")
                continue
            taken.update(names)
            kept.append(ext)
        return cls(scope_kinds=kinds, filters=tuple(kept), skipped=tuple(skipped))

    @property
    def filter_names(self) -> frozenset[str]:
        """확장 필터 이름 전부."""
        return frozenset(f.id for ext in self.filters for f in ext.fields)

    def fields(self) -> list[LogFilterFieldInfo]:
        """확장 필터 표시 정보(등록 순)."""
        return [f for ext in self.filters for f in ext.fields]

    def schema(self) -> LogQuerySchema:
        """`GET /logs/schema`: 기본 차원·지표·필터 + 확장 필터."""
        return query_schema(self.fields())

    def parse(self, params: Mapping[str, JsonValue], *, path: str = "") -> LogFilter:
        """확장 이름을 받는 `parse_log_filter`.

        Raises:
            LogQueryError: 모르는 이름(등록되지 않은 확장 포함)·틀린 값.
        """
        return parse_log_filter(params, path=path, extra=self.filter_names)

    def refine(self, flt: LogFilter, ctx: QueryContext, *, path: str = "") -> QueryContext:
        """`flt`의 `scope`·확장 필터를 풀어 질의 맥락에 싣는다(없으면 `ctx`의 이름 목록만 더한다).

        Args:
            path: 오류 위치 접두(예: 집계 요청의 `filter`).

        Raises:
            LogQueryError: 모르는 범위 종류(`scope`), 범위 값·확장 값이 틀림(`scope`·필터 이름),
                등록되지 않은 확장 필터 이름.
        """
        prefix = f"{path}." if path else ""
        scope = ctx.scope
        if flt.scope is not None:
            kind, _, value = flt.scope.partition(":")
            found = self.scope_kinds.get(kind)
            if found is None:
                raise LogQueryError(f"모르는 범위 종류: {kind}", prefix + "scope")
            try:
                scope = found.resolve(value)
            except LogQueryError:
                raise
            except ValueError as exc:
                raise LogQueryError(f"scope: {exc}", prefix + "scope") from None
        predicates = list(ctx.predicates)
        given = flt.extra_values()
        unknown = sorted(set(given) - self.filter_names)
        if unknown:
            raise LogQueryError(f"모르는 필터 이름: {unknown[0]}", prefix + unknown[0])
        if given:
            context = LogFilterContext(filter=flt, query=ctx)
            for ext in self.filters:
                mine = {f.id: given[f.id] for f in ext.fields if f.id in given}
                if not mine:
                    continue
                try:
                    predicates.append(ext.build(mine, context))
                except LogQueryError:
                    raise
                except ValueError as exc:
                    name = next(iter(mine))
                    raise LogQueryError(f"{name}: {exc}", prefix + name) from None
        names = ctx.extra_names | self.filter_names
        if (
            scope is ctx.scope
            and len(predicates) == len(ctx.predicates)
            and names == ctx.extra_names
        ):
            return ctx
        return replace(ctx, scope=scope, predicates=tuple(predicates), extra_names=names)
