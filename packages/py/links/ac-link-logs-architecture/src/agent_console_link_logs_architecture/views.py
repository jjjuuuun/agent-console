"""로그 범위 → 구조도(``ArchitectureView``)와 이벤트 멤버십. FastAPI를 모른다.

흐름(``project``):

1. 프로필을 고른다(``architecture.catalog``, 없는 id면 기본 프로필 + 대체 안내, 하나도 없으면
   ``ProfileNotFoundError``).
2. 범위 이벤트를 모은다(``logs.query``의 키셋 쪽 넘김). 질의 포트에 행 읽기(``event_rows``)가
   있으면 모델 없이 JSON 행으로, 없으면 ``events`` 결과를 행으로 덤프한다. 기억한 범위면 마지막
   ``seq`` 뒤만 읽고, 범위 전체 수(``total``)로 기억한 것이 맞는지 확인한다(범위 구성·설정이 바뀌어
   수가 다르면 처음부터).
3. 프로필로 판정하고 누적 집계(``ArchitectureTally``)에 더한다(이미 판정한 이벤트는 건너뜀).
4. 그린다(출처 종류·토큰 표본은 인자). 범위 끝까지면 누적 집계에서, ``max_seq``가 범위 끝보다
   앞이면 그 앞까지를 ``project_architecture``로 한 번에. 같은 (프로필, 출처 종류, ``max_seq``)면
   기억한 결과를 그대로 준다.

오류 범주는 질의 맥락(``query_context().error_categories`` — 분류 체계에서 오류로 표시한 범주)에서,
출처 종류는 출처 id 그대로(설정 ``source_kinds``가 바꾼다) 넘긴다. 코드에 출처·범주·칸 이름이 없다.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

from agent_console_architecture import (
    ProfileEntry,
    ProfileMatcher,
    event_membership,
    project_architecture,
)
from agent_console_contracts.architecture import (
    ArchitectureMembership,
    ArchitectureNote,
    ArchitectureView,
)
from agent_console_logs import JsonValue, LogEventRow, LogFilter, LogQueryError, event_row
from agent_console_logs.query import strip_body

from .errors import (
    ArchitectureQueryError,
    EventNotFoundError,
    ProfileNotFoundError,
    ScopeTooLargeError,
)
from .ports import ArchitectureCatalogReader, LogQueryReader, LogRowReader
from .scopes import Judged, ScopeCache, ScopeEvents, light_row, profile_key, scope_key
from .settings import (
    DEFAULT_CACHE_EVENTS,
    DEFAULT_CACHE_PROFILES,
    DEFAULT_CACHE_SCOPES,
    DEFAULT_PAGE_SIZE,
)

PROFILE_PARAM = "profile"
"""프로필을 고르는 쿼리 이름(나머지 쿼리는 로그 필터)."""


@dataclass
class ViewStats:
    """작업량(측정·테스트용). 부를 때마다 늘어난다.

    Attributes:
        pages: 색인에서 읽은 쪽 수.
        events_read: 색인에서 읽은 이벤트 수.
        judged: 조건 판정한 이벤트 수(프로필 키별 합).
        total_checks: 범위 전체 수 확인 질의 수.
        rebuilds: 기억한 범위가 맞지 않아 처음부터 다시 읽은 수.
        view_hits: 기억한 투영 결과를 그대로 준 수.
        projections: 투영을 새로 계산한 수(누적 집계에서 그린 것 포함).
        slices: 그중 ``max_seq``가 범위 끝보다 앞이라 그 앞까지를 한 번에 투영한 수.
    """

    pages: int = 0
    events_read: int = 0
    judged: int = 0
    total_checks: int = 0
    rebuilds: int = 0
    view_hits: int = 0
    projections: int = 0
    slices: int = 0


class LogArchitectureViews:
    """로그 범위 구조도·멤버십 계산(결과 캐시·증분 읽기 포함).

    Args:
        query: ``logs.query``.
        catalog: ``architecture.catalog``.
        source_kinds: 출처 id → 출처 종류(적지 않은 출처는 id 그대로).
        cache: 범위 캐시(없으면 ``cache_scopes``·``cache_events``로 만든다).
        cache_scopes: 기억할 범위 수.
        cache_events: 기억한 범위들의 이벤트 수 합 상한.
        cache_profiles: 범위 하나에 기억할 판정 결과(프로필 키) 수.
        page_size: 색인 쪽 크기.
    """

    def __init__(
        self,
        query: LogQueryReader,
        catalog: ArchitectureCatalogReader,
        *,
        source_kinds: Mapping[str, str] | None = None,
        cache: ScopeCache | None = None,
        cache_scopes: int = DEFAULT_CACHE_SCOPES,
        cache_events: int = DEFAULT_CACHE_EVENTS,
        cache_profiles: int = DEFAULT_CACHE_PROFILES,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._query = query
        self._catalog = catalog
        self._kinds = dict(source_kinds or {})
        self.cache = (
            cache
            if cache is not None
            else ScopeCache(
                max_scopes=cache_scopes, max_events=cache_events, max_profiles=cache_profiles
            )
        )
        self._page = page_size
        self.stats = ViewStats()
        self._rows = query if isinstance(query, LogRowReader) else None

    @property
    def query(self) -> LogQueryReader:
        return self._query

    @property
    def catalog(self) -> ArchitectureCatalogReader:
        return self._catalog

    # ------------------------------------------------------------------ 입력
    def parse(self, params: Mapping[str, JsonValue]) -> tuple[LogFilter, str | None]:
        """쿼리 이름별 값 → (로그 필터, 요청 프로필 id).

        Raises:
            ArchitectureQueryError: 모르는 필터 이름·틀린 값.
        """
        rest = dict(params)
        raw = rest.pop(PROFILE_PARAM, None)
        if isinstance(raw, list | tuple):
            raw = raw[-1] if raw else None
        profile = str(raw).strip() if raw not in (None, "") else None
        try:
            flt = self._query.parse_filter(rest)
        except LogQueryError as exc:
            raise ArchitectureQueryError(str(exc), exc.path) from None
        return flt, profile or None

    def pick(self, requested: str | None) -> tuple[ProfileEntry, ArchitectureNote | None]:
        """그릴 프로필.

        Raises:
            ProfileNotFoundError: 프로필이 하나도 없다.
        """
        entry, note = self._catalog.catalog().pick(requested)
        if entry is None:
            raise ProfileNotFoundError(requested)
        return entry, note

    def source_kinds(self, source_ids: set[str]) -> dict[str, str]:
        """범위에 든 출처 id → 출처 종류."""
        return {sid: self._kinds.get(sid, sid) for sid in sorted(source_ids)}

    # ------------------------------------------------------------------ 범위 읽기
    def _rows_after(self, flt: LogFilter, cursor: str | None) -> Iterator[LogEventRow]:
        """``cursor`` 뒤를 끝까지 행으로 읽는다(쪽 수·읽은 수를 센다). 질의 포트에 행 읽기가
        있으면 그것을, 없으면 ``events`` 쪽을 행으로 덤프한다.

        Raises:
            ArchitectureQueryError: 질의가 거절됐을 때(모르는 범위 종류 등).
        """

        def counted(rows: int) -> None:
            self.stats.pages += 1
            self.stats.events_read += rows

        start = flt.with_(cursor=cursor)
        try:
            if self._rows is not None:
                yield from self._rows.iter_event_rows(start, on_page=counted)
                return
            while True:
                page = self._query.events(start)
                counted(len(page.items))
                for event in page.items:
                    yield event_row(event)
                if page.next_cursor is None or not page.items:
                    return
                start = start.with_(cursor=page.next_cursor)
        except LogQueryError as exc:
            raise ArchitectureQueryError(str(exc), exc.path) from None

    def _read_after(self, scope: ScopeEvents, limit: int) -> None:
        """기억한 범위 뒤의 새 이벤트를 읽어 붙인다(기억한 프로필 키 모두로 판정·집계).

        Raises:
            ScopeTooLargeError: 범위 이벤트가 ``limit``을 넘을 때.
            ArchitectureQueryError: 질의가 거절됐을 때.
        """
        cursor = str(scope.last_seq) if scope.last_seq is not None else None
        self.stats.judged += scope.extend(self._rows_after(scope.key, cursor), limit=limit)

    def _backfill(self, scope: ScopeEvents, judged: Judged) -> bool:
        """이미 읽은 범위를 처음부터 다시 읽어 새 프로필 키로 판정한다(같은 이벤트인지 확인)."""
        before = len(judged.matches)
        bound = scope.key.with_(max_seq=scope.last_seq)
        ok = scope.backfill(judged, self._rows_after(bound, None))
        self.stats.judged += len(judged.matches) - before
        return ok

    def _total(self, scope: ScopeEvents) -> int | None:
        last = scope.last_seq
        if last is None:
            return 0
        self.stats.total_checks += 1
        page = self._query.events(scope.key.with_(max_seq=last, limit=1), with_total=True)
        return page.total

    def _refresh(
        self,
        scope: ScopeEvents,
        want: tuple[str, Callable[[], ProfileMatcher], str] | None,
    ) -> Judged | None:
        """범위를 지금까지로 맞춘다(``scope.lock`` 안에서). ``want`` = (프로필 키, 판정기 만들기,
        프로필 id)면 그 키의 판정 결과를 범위 끝까지 채워 돌려준다."""
        limit = self._catalog.max_scope_events

        def track() -> Judged | None:
            if want is None:
                return None
            key, make, profile_id = want
            judged, backfill = scope.track(key, make, profile_id=profile_id)
            if backfill and not self._backfill(scope, judged):
                return None  # 다시 읽은 것이 다르다 — 처음부터
            return judged

        try:
            had = len(scope)
            judged = track()
            if want is not None and judged is None:
                had = 0
                self.stats.rebuilds += 1
                scope.reset()
                judged = track()
            self._read_after(scope, limit)
            if had and self._total(scope) != len(scope):
                # 범위 구성이 바뀌었다(범위 종류의 세션 추가, 묶기 설정 변경, 보존 정리 등)
                self.stats.rebuilds += 1
                scope.reset()
                judged = track()
                self._read_after(scope, limit)
            if scope.tokens is None:
                scope.tokens = list(self._query.token_samples(scope.key))
        except ScopeTooLargeError:
            scope.reset()
            self.cache.drop(scope.key)
            raise
        return judged

    def refresh(self, flt: LogFilter) -> ScopeEvents:
        """범위 이벤트를 지금까지로 맞춘다(증분 읽기 + 범위 수 확인, 기억한 프로필 키로 판정).

        Raises:
            ScopeTooLargeError: 범위 이벤트가 ``max_scope_events``를 넘을 때.
            ArchitectureQueryError: 질의가 거절됐을 때.
        """
        scope = self.cache.get(scope_key(flt, self._page))
        with scope.lock:
            self._refresh(scope, None)
        self.cache.trim(scope)
        return scope

    # ------------------------------------------------------------------ 투영
    def project(self, flt: LogFilter, profile: str | None = None) -> ArchitectureView:
        """로그 범위 구조도.

        Args:
            flt: 로그 필터(범위). ``max_seq``를 주면 그 이하만 센다(없으면 지금까지).
            profile: 프로필 id(없으면 기본 프로필).

        Raises:
            ProfileNotFoundError: 프로필이 하나도 없다.
            ScopeTooLargeError: 범위 이벤트가 상한을 넘었다.
            ArchitectureQueryError: 필터가 거절됐다.
        """
        entry, note = self.pick(profile)
        errors = self._query.query_context().error_categories
        operators = self._catalog.operators()
        key = profile_key(entry.id, entry.profile, operators, errors)

        def make() -> ProfileMatcher:
            return ProfileMatcher(entry.profile, operators, error_categories=errors)

        scope = self.cache.get(scope_key(flt, self._page))
        try:
            with scope.lock:
                judged = self._refresh(scope, (key, make, entry.id))
                assert judged is not None  # want를 주면 판정 결과가 있다
                return self._view(scope, judged, flt, key, profile, entry.id, note)
        finally:
            self.cache.trim(scope)

    def _view(
        self,
        scope: ScopeEvents,
        judged: Judged,
        flt: LogFilter,
        key: str,
        requested: str | None,
        profile_id: str,
        note: ArchitectureNote | None,
    ) -> ArchitectureView:
        kinds = self.source_kinds(scope.sources)
        last = scope.last_seq
        bound = flt.max_seq if flt.max_seq is not None else last
        view_key = (key, tuple(kinds.items()), requested, bound)
        cached = scope.recall(view_key)
        if cached is not None:
            self.stats.view_hits += 1
            return cached
        notes = [note] if note is not None else []
        if flt.max_seq is None or last is None or flt.max_seq >= last:
            # 범위 끝까지: 누적 집계에서 그린다(새 이벤트만 더해져 있다)
            view = judged.tally.view(source_kinds=kinds, tokens=scope.tokens or (), notes=notes)
        else:
            # 범위 끝보다 앞까지(클릭 표와 같은 경계): 그 앞까지만 요약으로 한 번에 투영한다
            upto = bisect_right(scope.seqs, flt.max_seq)
            view = project_architecture(
                [light_row(x) for x in scope.lights[:upto]],
                judged.matcher.profile,
                profile_id=profile_id,
                operators=judged.matcher.operators,
                source_kinds=kinds,
                tokens=scope.tokens or (),
                error_categories=judged.matcher.error_categories,
                notes=notes,
                matches=judged.matches[:upto],
            )
            self.stats.slices += 1
        self.stats.projections += 1
        scope.remember(view_key, view)
        return view

    def architecture(self, params: Mapping[str, JsonValue]) -> ArchitectureView:
        """쿼리 이름별 값(로그 필터 + ``profile``) → 구조도(``GET /logs/architecture``)."""
        flt, profile = self.parse(params)
        return self.project(flt, profile)

    # ------------------------------------------------------------------ 멤버십
    def membership(self, uid: str, profile: str | None = None) -> ArchitectureMembership:
        """이벤트 하나가 맞은 칸·연결·묶음(``GET /logs/events/{uid}/architecture``).

        판정은 목록용 사본(``detail``·``raw`` 없음)으로 한다 — 구조도가 센 이벤트와 같은 모양.

        Raises:
            EventNotFoundError: 없는 이벤트.
            ProfileNotFoundError: 프로필이 하나도 없다.
        """
        found = self._query.event(uid)
        if found is None:
            raise EventNotFoundError(uid)
        entry, _note = self.pick(profile)
        return event_membership(
            strip_body(found.event),
            entry.profile,
            profile_id=entry.id,
            operators=self._catalog.operators(),
        )


__all__ = ["PROFILE_PARAM", "LogArchitectureViews", "ViewStats"]
