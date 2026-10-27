"""범위 캐시: 범위(필터)마다 읽은 이벤트 행·토큰 표본·프로필별 판정 결과·누적 집계·투영 결과를
기억한다.

design §5.5R.10 `[5.5R.6]`·`[5.5R.36]`: 구조도 비용은 색인 읽기·조건 판정·투영이다. 이벤트는 모델이
아니라 JSON 행(``ac-logs`` ``LogEventRow``, 목록 모양)으로 읽어 그대로 판정한다. 같은 범위를 다시
그릴 때는

- 이미 읽은 이벤트 뒤(``seq`` 커서)만 읽고(증분 읽기),
- 새 행은 읽을 때 기억한 프로필 키 모두로 판정하고 칸·연결별 누적 집계(``ArchitectureTally``)에
  더한 뒤 버린다(행 전체는 남기지 않음 — 요약 ``LIGHT_FIELDS``만, 증분 투영),
- 이미 읽은 범위에 새 프로필 키가 오면 같은 범위를 다시 읽어 그 키로만 판정한다,
- (프로필 키, 출처 종류, ``max_seq``)가 같으면 투영 결과를 그대로 준다(결과 캐시).

판정 결과는 이벤트 표의 ``arch`` 필터(X28)도 쓴다(``MemoMatcher`` — 범위 단위 멤버십 표,
§5.5R.11 위험 1). 이 모듈은 HTTP·포트를 모른다.
"""

from __future__ import annotations

import hashlib
import threading
from bisect import bisect_left
from collections import OrderedDict
from collections.abc import Callable, Collection, Hashable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field

from agent_console_architecture import ArchitectureTally, EventMatch, ProfileMatcher
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import ArchitectureProfile, ArchitectureView
from agent_console_contracts.logs import LogEvent, TokenSample
from agent_console_logs import LogEventRow, LogFilter
from agent_console_logs.query import strip_body

from .errors import ScopeTooLargeError
from .settings import DEFAULT_CACHE_PROFILES

VIEW_CACHE_PER_SCOPE = 16
"""범위 하나에 기억할 투영 결과 수(프로필·``max_seq``가 다른 결과)."""


def profile_key(
    profile_id: str,
    profile: ArchitectureProfile,
    operators: Mapping[str, ConditionOperator],
    error_categories: Collection[str],
) -> str:
    """판정 결과가 같으려면 같아야 하는 것의 지문(프로필 본문·연산자·오류 범주).

    연산자는 객체 동일성으로 본다(등록이 바뀌면 다른 키).
    """
    digest = hashlib.sha256()
    digest.update(profile_id.encode())
    digest.update(b"\0")
    digest.update(profile.model_dump_json(by_alias=True).encode())
    digest.update(b"\0")
    for name in sorted(operators):
        digest.update(f"{name}={id(operators[name])};".encode())
    digest.update(b"\0")
    digest.update(",".join(sorted(error_categories)).encode())
    return digest.hexdigest()


def scope_key(flt: LogFilter, page_size: int) -> LogFilter:
    """범위 키: 쪽·순서·``max_seq``를 뺀 필터(같은 범위면 같은 키)."""
    return flt.with_(max_seq=None, cursor=None, order="asc", limit=page_size)


LIGHT_FIELDS: tuple[str, ...] = (
    "seq",
    "source",
    "uid",
    "thread",
    "message_id",
    "time",
    "duration_ms",
)
"""범위에 남기는 이벤트 요약의 필드(``max_seq`` 앞까지 다시 그리기·같은 이벤트 찾기에 쓴다)."""

type Light = tuple[int, str, str, str, str, float | None, float | None]
"""``LIGHT_FIELDS`` 순서의 이벤트 요약."""


def light_of(row: LogEventRow) -> Light:
    """행 → 요약(``LIGHT_FIELDS``)."""
    return (
        row["seq"],
        row["source"],
        row["uid"],
        row.get("thread", ""),
        row.get("message_id", ""),
        row.get("time"),
        row.get("duration_ms"),
    )


def light_row(light: Light) -> LogEventRow:
    """요약 → 누적 집계·투영이 읽는 키만 있는 행."""
    return dict(zip(LIGHT_FIELDS, light, strict=True))


@dataclass
class Judged:
    """범위 하나·프로필 키 하나의 판정 결과(``seqs``와 같은 순서)와 누적 집계.

    Attributes:
        matcher: 판정기.
        tally: 판정한 이벤트 전부를 더한 누적 집계(증분 투영).
        matches: 판정 결과.
    """

    matcher: ProfileMatcher
    tally: ArchitectureTally
    matches: list[EventMatch] = field(default_factory=list)

    def take(self, row: LogEventRow) -> None:
        """행 하나를 판정해 결과와 누적 집계에 더한다."""
        matched = self.matcher.match_subject(row)
        self.matches.append(matched)
        self.tally.add_row(row, matched)


@dataclass
class ScopeEvents:
    """범위 하나의 이벤트 요약(``seq`` 오름차순)과 그에 딸린 캐시.

    행 전체는 남기지 않는다(메모리·GC). 새 행은 읽을 때 지금 기억한 프로필 키 모두로 판정·집계하고
    버린다. 이미 읽은 범위에 새 프로필 키가 오면 같은 행을 다시 읽어 판정한다(``backfill``).

    Attributes:
        key: 범위 키(``scope_key``).
        seqs: 읽은 이벤트의 ``seq``(이분 탐색용).
        lights: 읽은 이벤트 요약(``LIGHT_FIELDS``, ``seqs``와 같은 순서).
        sources: 읽은 이벤트의 출처 id.
        tokens: 범위 토큰 표본(이벤트가 바뀔 때만 다시 읽는다). None = 아직 안 읽음.
        judged: 프로필 키 → 판정 결과·누적 집계(최근 쓴 것이 뒤, ``max_profiles``개까지).
        views: (프로필 키, 출처 종류, 요청 프로필, ``max_seq``) → 투영 결과.
        lock: 같은 범위를 동시에 읽고 고치지 않게 한다.
        max_profiles: 기억할 판정 결과(프로필 키) 수. 프로필을 고칠 때마다 새 키가 생기므로
            오래 쓰지 않은 것부터 버린다(버린 키의 투영 결과도 함께 버린다).
    """

    key: LogFilter
    seqs: list[int] = field(default_factory=list)
    lights: list[Light] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    tokens: list[TokenSample] | None = None
    judged: OrderedDict[str, Judged] = field(default_factory=OrderedDict)
    views: OrderedDict[Hashable, ArchitectureView] = field(default_factory=OrderedDict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    max_profiles: int = DEFAULT_CACHE_PROFILES

    @property
    def last_seq(self) -> int | None:
        """읽은 마지막 ``seq``(없으면 None)."""
        return self.seqs[-1] if self.seqs else None

    def __len__(self) -> int:
        return len(self.seqs)

    def reset(self) -> None:
        """읽은 것을 모두 버린다(범위 구성이 바뀌었을 때). 새 목록 객체로 바꿔 읽는 쪽이 옛
        목록을 계속 볼 수 있게 한다."""
        self.seqs = []
        self.lights = []
        self.sources = set()
        self.tokens = None
        self.judged = OrderedDict()
        self.views = OrderedDict()

    def track(
        self, key: str, make: Callable[[], ProfileMatcher], *, profile_id: str
    ) -> tuple[Judged, bool]:
        """프로필 키의 판정 결과를 꺼낸다(없으면 만든다). 오래 쓰지 않은 키는 버린다.

        Args:
            key: 프로필 키(``profile_key``).
            make: 처음일 때 판정기를 만드는 함수.
            profile_id: 프로필 id(누적 집계의 선택 필터 ``arch``에 쓴다 — 키에 들어 있다).

        Returns:
            (판정 결과, 이미 읽은 이벤트를 다시 읽어 판정해야 하는지).
        """
        found = self.judged.get(key)
        fresh = found is None
        if found is None:
            matcher = make()
            found = self.judged[key] = Judged(
                matcher, ArchitectureTally(matcher.profile, profile_id=profile_id)
            )
        self.judged.move_to_end(key)
        while len(self.judged) > max(1, self.max_profiles):
            dropped, _ = self.judged.popitem(last=False)
            for view_key in [k for k in self.views if _profile_of(k) == dropped]:
                del self.views[view_key]
        return found, fresh and bool(self.seqs)

    def extend(self, new: Iterable[LogEventRow], *, limit: int | None = None) -> int:
        """새 행을 붙이고 기억한 프로필 키 모두로 판정·집계한다(``seq``가 더 큰 것만 — 쪽 경계
        중복 방지). 행은 하나씩 받아 처리하고 남기지 않는다. 판정 횟수를 돌려준다.

        Raises:
            ScopeTooLargeError: 범위 이벤트가 ``limit``을 넘었을 때(넘은 행까지는 붙어 있다 —
                호출자가 범위를 버린다).
        """
        last = self.last_seq
        judged = list(self.judged.values())
        added = 0
        try:
            for row in new:
                seq = row["seq"]
                if last is not None and seq <= last:
                    continue
                self.seqs.append(seq)
                self.lights.append(light_of(row))
                self.sources.add(row["source"])
                for one in judged:
                    one.take(row)
                last = seq
                added += 1
                if limit is not None and len(self.seqs) > limit:
                    raise ScopeTooLargeError(len(self.seqs), limit)
        finally:
            if added:
                self.tokens = None
                self.views.clear()
        return added * len(judged)

    def backfill(self, judged: Judged, rows: Iterable[LogEventRow]) -> bool:
        """이미 읽은 이벤트를 새 프로필 키로 판정한다(같은 범위를 처음부터 다시 읽은 행).

        Returns:
            다시 읽은 행이 기억한 이벤트와 같으면(``seq``·``uid``·수) 참. 다르면 거짓이고 그
            판정 결과는 쓸 수 없다(범위 구성이 바뀌었다 — 처음부터 다시 읽는다).
        """
        seqs, lights = self.seqs, self.lights
        i = 0
        for row in rows:
            if i >= len(seqs) or row["seq"] != seqs[i] or row["uid"] != lights[i][2]:
                return False
            judged.take(row)
            i += 1
        return i == len(seqs)

    def match_at(self, key: str, event: LogEvent) -> EventMatch | None:
        """이미 판정한 같은 이벤트(같은 ``seq``·``uid``)의 판정 결과. 없으면 None."""
        found = self.judged.get(key)
        if found is None:
            return None
        seqs, lights, matches = self.seqs, self.lights, found.matches
        i = bisect_left(seqs, event.seq)
        if i >= len(matches) or i >= len(seqs) or seqs[i] != event.seq:
            return None
        if lights[i][2] != event.uid:
            return None
        return matches[i]

    def remember(self, key: Hashable, view: ArchitectureView) -> None:
        """투영 결과를 기억한다(범위당 ``VIEW_CACHE_PER_SCOPE``개, 오래 쓰지 않은 것부터 버림)."""
        self.views[key] = view
        self.views.move_to_end(key)
        while len(self.views) > VIEW_CACHE_PER_SCOPE:
            self.views.popitem(last=False)

    def recall(self, key: Hashable) -> ArchitectureView | None:
        """기억한 투영 결과(없으면 None)."""
        view = self.views.get(key)
        if view is not None:
            self.views.move_to_end(key)
        return view


def _profile_of(view_key: Hashable) -> Hashable:
    # 투영 결과 키는 (프로필 키, 출처 종류, 요청 프로필, max_seq)다(views.py)
    return view_key[0] if isinstance(view_key, tuple) and view_key else None


class ScopeCache:
    """범위 캐시(오래 쓰지 않은 범위부터 버림).

    Args:
        max_scopes: 기억할 범위 수(0 = 기억하지 않음 — 부를 때마다 새로 읽는다).
        max_events: 기억한 범위들의 이벤트 수 합 상한.
        max_profiles: 범위 하나에 기억할 판정 결과(프로필 키) 수.
    """

    def __init__(
        self, *, max_scopes: int, max_events: int, max_profiles: int = DEFAULT_CACHE_PROFILES
    ) -> None:
        self._max_scopes = max_scopes
        self._max_events = max_events
        self._max_profiles = max_profiles
        self._scopes: OrderedDict[LogFilter, ScopeEvents] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: LogFilter) -> ScopeEvents:
        """범위를 꺼낸다(없으면 새로 만든다 — 기억은 ``trim``에서 정한다)."""
        with self._lock:
            found = self._scopes.get(key)
            if found is not None:
                self._scopes.move_to_end(key)
                return found
            scope = ScopeEvents(key, max_profiles=self._max_profiles)
            if self._max_scopes > 0:
                self._scopes[key] = scope
            return scope

    def trim(self, keep: ScopeEvents) -> None:
        """상한을 넘으면 오래 쓰지 않은 범위부터 버린다(``keep``은 마지막에, 혼자 넘으면 버린다)."""
        with self._lock:
            while len(self._scopes) > self._max_scopes or (
                self._total() > self._max_events and len(self._scopes) > 1
            ):
                oldest = next(iter(self._scopes))
                if self._scopes[oldest] is keep and len(self._scopes) > 1:
                    self._scopes.move_to_end(oldest)
                    continue
                del self._scopes[oldest]
            if self._total() > self._max_events:
                self._scopes.pop(keep.key, None)

    def drop(self, key: LogFilter) -> None:
        """범위 하나를 버린다."""
        with self._lock:
            self._scopes.pop(key, None)

    def _total(self) -> int:
        return sum(len(s) for s in self._scopes.values())

    def scopes(self) -> list[ScopeEvents]:
        """기억한 범위(최근 쓴 것이 뒤)."""
        with self._lock:
            return list(self._scopes.values())

    def lookup(self, key: str, event: LogEvent) -> EventMatch | None:
        """기억한 범위 중 이 이벤트를 이미 판정한 결과(최근 범위부터)."""
        for scope in reversed(self.scopes()):
            found = scope.match_at(key, event)
            if found is not None:
                return found
        return None

    def __len__(self) -> int:
        with self._lock:
            return len(self._scopes)

    def __iter__(self) -> Iterator[ScopeEvents]:
        return iter(self.scopes())


class MemoMatcher(ProfileMatcher):
    """판정 결과를 먼저 범위 캐시에서 찾는 판정기(``selector_predicate(matcher=)``에 넘긴다).

    캐시에 없으면 목록용 사본(``detail``·``raw`` 없음 — 구조도가 센 이벤트와 같은 모양)으로
    판정한다.
    """

    def __init__(
        self,
        profile: ArchitectureProfile,
        operators: Mapping[str, ConditionOperator],
        *,
        key: str,
        cache: ScopeCache,
        error_categories: Collection[str] = frozenset(),
    ) -> None:
        super().__init__(profile, operators, error_categories=error_categories)
        self._key = key
        self._cache = cache
        self.hits = 0
        self.misses = 0

    def match(self, event: LogEvent) -> EventMatch:
        found = self._cache.lookup(self._key, event)
        if found is not None:
            self.hits += 1
            return found
        self.misses += 1
        return super().match(strip_body(event))


__all__ = [
    "LIGHT_FIELDS",
    "VIEW_CACHE_PER_SCOPE",
    "Judged",
    "Light",
    "MemoMatcher",
    "ScopeCache",
    "ScopeEvents",
    "light_of",
    "light_row",
    "profile_key",
    "scope_key",
]
