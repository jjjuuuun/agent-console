"""단독 실행·테스트용 부품(공개).

- ``IndexLogQuery``: 로그 색인(``agent_console_logs.LogIndex``) → ``logs.query`` 모양(필터 확장
  X28·범위
  종류 X27을 받아 ``mod-logs``처럼 필터를 읽고 푼다). 서버 없이 구조도·``arch`` 필터를 쓸 때.
- ``StaticCatalog``: 주어진 프로필 → ``architecture.catalog`` 모양.
- ``local_logs_module``·``local_catalog_module``: 위 둘을 포트로 주는 작은 모듈. 단독 실행
  ``python -m agent_console_link_logs_architecture``가 ``--with`` 없이 실행되면 이것을 붙인다
  (통합 서버에서는 ``mod-logs``·``mod-architecture``가 대신한다).
- 클릭 수 일치 도구: ``click_targets``(구조도의 모든 클릭 대상)·``selector_params``(선택 필터 →
  질의 인자)·``click_count_mismatches``(표 수 ≠ 지표 ``count``인 대상).
- ``LogArchitectureHarness``: 색인 + ``logs.query`` + 프로필 + 구조도 + ``arch`` 필터를 이은 묶음,
  ``random_records``: 무작위 레코드(테스트 전용 데모 프로필 ``DEMO_SOURCE_KINDS``와 맞춘 값).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from agent_console_architecture import (
    ProfileCatalog,
    load_default_profiles,
    merge_profiles,
    parse_profiles_document,
)
from agent_console_architecture.testing import demo_profile
from agent_console_conditions import ConditionOperator, default_operators
from agent_console_contracts.architecture import (
    ArchitectureProfile,
    ArchitectureSelector,
    ArchitectureView,
)
from agent_console_contracts.logs import LogEventDetail, LogEventPage, TokenSample
from agent_console_logs import (
    IndexBatch,
    IndexRecord,
    JsonValue,
    LogEventRow,
    LogFilter,
    LogFilterExtension,
    LogIndex,
    LogQueryExtensions,
    LogScopeKind,
    PageCallback,
    QueryContext,
    iter_event_rows,
)
from agent_console_logs.testing import MemoryLogIndex, make_record
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .filters import ArchitectureFilter
from .ports import ARCHITECTURE_CATALOG, LOG_FILTER_PREDICATES, LOGS_QUERY
from .settings import DEFAULT_CACHE_PROFILES
from .views import LogArchitectureViews

LOCAL_LOGS_ID = "local-logs"
LOCAL_CATALOG_ID = "local-architecture-catalog"
DEFAULT_MAX_SCOPE_EVENTS = 100_000


class IndexLogQuery:
    """``LogIndex`` → ``logs.query``(이 연동이 쓰는 부분).

    Args:
        index: 로그 색인.
        ctx: 질의 맥락(오류 범주 등). 없으면 기본값.
        filters: 필터 확장 목록을 돌려주는 함수(부를 때마다 읽는다).
        scope_kinds: 범위 종류 목록을 돌려주는 함수.
    """

    def __init__(
        self,
        index: LogIndex,
        ctx: QueryContext | None = None,
        *,
        filters: Callable[[], Sequence[LogFilterExtension]] = tuple,
        scope_kinds: Callable[[], Sequence[LogScopeKind]] = tuple,
    ) -> None:
        self.index = index
        self._ctx = ctx if ctx is not None else QueryContext()
        self._filters = filters
        self._kinds = scope_kinds

    def extensions(self) -> LogQueryExtensions:
        """지금 등록된 확장 묶음."""
        return LogQueryExtensions.collect(self._kinds(), self._filters())

    def _refined(self, flt: LogFilter) -> QueryContext:
        return self.extensions().refine(flt, self._ctx)

    def query_context(self, *, tz: str | None = None) -> QueryContext:
        return self._ctx

    def parse_filter(self, params: Mapping[str, JsonValue], *, path: str = "") -> LogFilter:
        return self.extensions().parse(params, path=path)

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage:
        return self.index.query_events(flt, self._refined(flt), with_total=with_total)

    def iter_event_rows(
        self, flt: LogFilter, *, on_page: PageCallback | None = None
    ) -> Iterator[LogEventRow]:
        """행 읽기(``LogRowReader``, ``mod-logs`` ``iter_event_rows``와 같은 모양)."""
        return iter_event_rows(self.index, flt, self._refined(flt), on_page=on_page)

    def event(self, uid: str) -> LogEventDetail | None:
        return self.index.get_event(uid, self._ctx)

    def token_samples(self, flt: LogFilter) -> list[TokenSample]:
        return self.index.token_samples(flt, self._refined(flt))


class StaticCatalog:
    """주어진 프로필 → ``architecture.catalog``(이 연동이 쓰는 부분).

    Args:
        profiles: 프로필(id → 프로필) 또는 병합된 ``ProfileCatalog``. 함수면 부를 때마다 읽는다.
        operators: 조건 연산자(없으면 설치된 연산자).
        max_scope_events: 범위 투영 상한.
    """

    def __init__(
        self,
        profiles: Mapping[str, ArchitectureProfile]
        | ProfileCatalog
        | Callable[[], Mapping[str, ArchitectureProfile] | ProfileCatalog],
        *,
        operators: Mapping[str, ConditionOperator] | None = None,
        max_scope_events: int = DEFAULT_MAX_SCOPE_EVENTS,
    ) -> None:
        self._profiles = profiles
        if operators is None:
            operators, _reports = default_operators()
        self._operators = dict(operators)
        self.max_scope_events = max_scope_events

    def catalog(self) -> ProfileCatalog:
        found: Any = self._profiles() if callable(self._profiles) else self._profiles
        if isinstance(found, ProfileCatalog):
            return found
        return merge_profiles(found)

    def operators(self) -> Mapping[str, ConditionOperator]:
        return self._operators


def local_logs_module(
    module_id: str = LOCAL_LOGS_ID,
    *,
    index: LogIndex | None = None,
    ctx: QueryContext | None = None,
) -> Module:
    """``logs.query`` 제공 모듈(주어진 색인, 없으면 빈 메모리 색인). ``logs.filter_predicates``를
    받아 필터 확장 이름을 읽는다(이 연동의 ``arch`` 필터)."""

    def build(mctx: ModuleContext) -> ModuleParts:
        query = IndexLogQuery(
            index if index is not None else MemoryLogIndex(),
            ctx,
            filters=lambda: mctx.ports(LOG_FILTER_PREDICATES),
        )
        mctx.provide(LOGS_QUERY, query)
        return ModuleParts()

    return fake_module(
        module_id,
        kind="testing",
        provides=[LOGS_QUERY],
        optional=[LOG_FILTER_PREDICATES],
        on_build=build,
    )


def local_catalog_module(
    module_id: str = LOCAL_CATALOG_ID,
    *,
    profiles: Mapping[str, ArchitectureProfile] | ProfileCatalog | None = None,
    max_scope_events: int = DEFAULT_MAX_SCOPE_EVENTS,
) -> Module:
    """``architecture.catalog`` 제공 모듈(주어진 프로필, 없으면 패키지 기본 프로필)."""

    def build(mctx: ModuleContext) -> ModuleParts:
        source = profiles if profiles is not None else load_default_profiles()
        mctx.provide(ARCHITECTURE_CATALOG, StaticCatalog(source, max_scope_events=max_scope_events))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[ARCHITECTURE_CATALOG], on_build=build)


# ---------------------------------------------------------------- 클릭 수 일치 도구


def selector_params(selector: ArchitectureSelector) -> dict[str, JsonValue]:
    """선택 필터 → 이벤트 목록 질의 인자(``arch``·``arch_group``·``arch_sources``)."""
    out: dict[str, JsonValue] = {"arch": selector.arch}
    if selector.arch_group is not None:
        out["arch_group"] = selector.arch_group
    if selector.arch_sources is not None:
        out["arch_sources"] = ",".join(selector.arch_sources)
    return out


def click_targets(
    view: ArchitectureView,
) -> Iterator[tuple[str, ArchitectureSelector, int | None]]:
    """구조도의 모든 클릭 대상(칸·묶음·관측 연결·분류 안 됨) → (이름, 선택 필터, 지표 ``count``).

    ``count``가 없거나 수집 안 됨이면 None.
    """

    def value(metrics: Mapping[str, Any]) -> int | None:
        found = metrics.get("count")
        return None if found is None or found.value is None else int(found.value)

    for cell in view.cells:
        yield f"cell {cell.id}", cell.selector, value(cell.metrics)
        for group in cell.groups or []:
            yield f"group {cell.id}/{group.key}", group.selector, value(group.metrics)
    for edge in view.edges:
        if edge.selector is not None:
            yield f"edge {edge.id}", edge.selector, value(edge.metrics)
    if view.unassigned is not None:
        yield "unassigned", view.unassigned.selector, value(view.unassigned.metrics)


def click_count_mismatches(
    view: ArchitectureView,
    count: Callable[[Mapping[str, JsonValue]], int],
    base: Mapping[str, JsonValue],
) -> tuple[list[tuple[str, int, int]], int]:
    """모든 대상에서 (범위 ``base`` + 선택 필터 + 결과 ``max_seq``)로 거른 표 수와 ``count``를
    견준다.

    Args:
        view: 구조도.
        count: 질의 인자 → 표 전체 수(쪽 넘김으로 끝까지 센 수, 또는 HTTP 목록 질의).
        base: 구조도를 그린 범위 필터(질의 인자).

    Returns:
        (다른 대상 ``(이름, 표 수, 지표)`` 목록, 견준 대상 수).
    """
    wrong: list[tuple[str, int, int]] = []
    checked = 0
    for name, selector, expected in click_targets(view):
        if expected is None:
            continue
        params: dict[str, JsonValue] = {**base, **selector_params(selector)}
        if view.max_seq is not None:
            params["max_seq"] = view.max_seq
        got = count(params)
        checked += 1
        if got != expected:
            wrong.append((name, got, expected))
    return wrong, checked


# ---------------------------------------------------------------- 색인 위 묶음

DEMO_SOURCE_KINDS: dict[str, str] = {"a1": "kind-a", "b1": "kind-b"}
"""``random_records``의 출처 id → 테스트 전용 데모 프로필(``ac-architecture``
``testing.demo_profile``)의 출처 종류. ``c1``은 종류가 없다(우선순위 맨 뒤)."""

DEMO_CONTEXT = QueryContext(error_categories=frozenset({"error"}))
"""테스트 질의 맥락(범주 ``error``를 오류로 센다)."""


def demo_profiles() -> dict[str, ArchitectureProfile]:
    """테스트 전용 데모 프로필(``ac-architecture`` ``testing.demo_profile``, id ``demo``)."""
    return dict(parse_profiles_document(demo_profile()))


def random_records(
    rng: random.Random, count: int, *, sessions: Sequence[str] = ("S1",)
) -> list[IndexRecord]:
    """무작위 레코드(범주·스레드·태그·도구·모델·상태·출처·토큰 표본, 쉼표가 든 도구 이름 포함)."""
    out: list[IndexRecord] = []
    for _ in range(count):
        thread = rng.choice(["main", "main", "sub1", "sub2", ""])
        category = rng.choice(["input", "llm", "tool", "agent", "error", "other"])
        fields: dict[str, Any] = {
            "source": rng.choice(["a1", "a1", "b1", "c1"]),
            "session": rng.choice(list(sessions)),
            "thread": thread,
            "status": rng.choice(["", "", "ok", "failed", "error"]),
            "tags": tuple(rng.sample(["tool_call", "tool_result", "x"], rng.randint(0, 2))),
        }
        if rng.random() < 0.6:
            fields["tool"] = rng.choice(["Read", "Grep", "Write", "a,b", ""])
        if category == "llm" or rng.random() < 0.2:
            fields["model"] = rng.choice(["m1", "m2", ""])
        if category == "llm" and rng.random() < 0.7:
            mid = f"r{rng.randint(1, 6)}"
            fields["message_id"] = mid
            fields["usage"] = TokenSample(
                thread=thread, message_id=mid, output_tokens=rng.randint(1, 50)
            )
        out.append(make_record(category, **fields))
    return out


class LogArchitectureHarness:
    """색인 + ``logs.query``(``IndexLogQuery``) + 프로필(``StaticCatalog``) + 구조도
    (``LogArchitectureViews``) + ``arch`` 필터(같은 범위 캐시를 나눈다).

    Args:
        index: 로그 색인.
        profiles: 프로필(없으면 ``demo_profiles()``).
        ctx: 질의 맥락(없으면 ``DEMO_CONTEXT``).
        scope_kinds: 범위 종류(X27).
        source_kinds: 출처 종류 대응(없으면 ``DEMO_SOURCE_KINDS``).
        cache_scopes·cache_events·cache_profiles: 범위 캐시 크기.
        max_scope_events: 범위 상한.
    """

    def __init__(
        self,
        index: LogIndex,
        *,
        profiles: Mapping[str, ArchitectureProfile] | None = None,
        ctx: QueryContext | None = None,
        scope_kinds: Sequence[LogScopeKind] = (),
        source_kinds: Mapping[str, str] | None = None,
        cache_scopes: int = 8,
        cache_events: int = 100_000,
        cache_profiles: int = DEFAULT_CACHE_PROFILES,
        max_scope_events: int = DEFAULT_MAX_SCOPE_EVENTS,
    ) -> None:
        kinds = tuple(scope_kinds)
        self.index = index
        self.catalog = StaticCatalog(
            profiles if profiles is not None else demo_profiles(),
            max_scope_events=max_scope_events,
        )
        self.filters: list[LogFilterExtension] = []
        self.query = IndexLogQuery(
            index,
            ctx if ctx is not None else DEMO_CONTEXT,
            filters=lambda: self.filters,
            scope_kinds=lambda: kinds,
        )
        self.views = LogArchitectureViews(
            self.query,
            self.catalog,
            source_kinds=DEMO_SOURCE_KINDS if source_kinds is None else source_kinds,
            cache_scopes=cache_scopes,
            cache_events=cache_events,
            cache_profiles=cache_profiles,
        )
        self.arch_filter = ArchitectureFilter(self.catalog, self.views.cache)
        self.filters.append(self.arch_filter)

    def write(self, records: Sequence[IndexRecord]) -> None:
        """레코드를 색인에 쓴다."""
        self.index.write(IndexBatch(records=list(records)))

    def project(self, **params: JsonValue) -> ArchitectureView:
        """질의 인자(로그 필터 + ``profile``) → 구조도."""
        return self.views.architecture(params)

    def count(self, params: Mapping[str, JsonValue], *, page: int = 7) -> int:
        """질의 인자로 거른 이벤트 수(쪽 넘김으로 끝까지)."""
        flt = self.query.parse_filter({**params, "limit": page})
        total = 0
        cursor: str | None = None
        while True:
            found = self.query.events(flt.with_(cursor=cursor))
            total += len(found.items)
            if found.next_cursor is None:
                return total
            cursor = found.next_cursor


__all__ = [
    "DEFAULT_MAX_SCOPE_EVENTS",
    "DEMO_CONTEXT",
    "DEMO_SOURCE_KINDS",
    "LOCAL_CATALOG_ID",
    "LOCAL_LOGS_ID",
    "IndexLogQuery",
    "LogArchitectureHarness",
    "StaticCatalog",
    "click_count_mismatches",
    "click_targets",
    "demo_profiles",
    "local_catalog_module",
    "local_logs_module",
    "random_records",
    "selector_params",
]
