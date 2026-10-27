"""범위 캐시: 범위(필터)마다 읽은 이벤트·토큰 표본·프로필별 판정 결과·투영 결과를 기억한다.

design §5.5R.10 `[5.5R.6]` 측정: 구조도 비용은 색인 읽기(이벤트 모델 생성)와 조건 판정이다.
같은 범위를
다시 그릴 때는

- 이미 읽은 이벤트 뒤(``seq`` 커서)만 읽고(증분 읽기),
- 이미 판정한 이벤트는 다시 판정하지 않으며(프로필 키별 판정 결과),
- (프로필 키, 출처 종류, ``max_seq``)가 같으면 투영 결과를 그대로 준다(결과 캐시).

판정 결과는 이벤트 표의 ``arch`` 필터(X28)도 쓴다(``MemoMatcher`` — 범위 단위 멤버십 표,
§5.5R.11 위험 1). 이 모듈은 HTTP·포트를 모른다.
"""

from __future__ import annotations

import hashlib
import threading
from bisect import bisect_left
from collections import OrderedDict
from collections.abc import Callable, Collection, Hashable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from agent_console_architecture import EventMatch, ProfileMatcher
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import ArchitectureProfile, ArchitectureView
from agent_console_contracts.logs import LogEvent, TokenSample
from agent_console_logs import LogFilter
from agent_console_logs.query import strip_body

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


@dataclass
class Judged:
    """범위 하나·프로필 키 하나의 판정 결과(``events``와 같은 순서, 앞부분부터 채운다)."""

    matcher: ProfileMatcher
    matches: list[EventMatch] = field(default_factory=list)


@dataclass
class ScopeEvents:
    """범위 하나의 이벤트(``seq`` 오름차순)와 그에 딸린 캐시.

    Attributes:
        key: 범위 키(``scope_key``).
        events: 읽은 이벤트(목록용 — ``detail``·``raw`` 없음).
        seqs: ``events``의 ``seq``(이분 탐색용).
        tokens: 범위 토큰 표본(이벤트가 바뀔 때만 다시 읽는다). None = 아직 안 읽음.
        judged: 프로필 키 → 판정 결과(최근 쓴 것이 뒤, ``max_profiles``개까지).
        views: (프로필 키, 출처 종류, 요청 프로필, ``max_seq``) → 투영 결과.
        lock: 같은 범위를 동시에 읽고 고치지 않게 한다.
        max_profiles: 기억할 판정 결과(프로필 키) 수. 프로필을 고칠 때마다 새 키가 생기므로
            오래 쓰지 않은 것부터 버린다(버린 키의 투영 결과도 함께 버린다).
    """

    key: LogFilter
    events: list[LogEvent] = field(default_factory=list)
    seqs: list[int] = field(default_factory=list)
    tokens: list[TokenSample] | None = None
    judged: OrderedDict[str, Judged] = field(default_factory=OrderedDict)
    views: OrderedDict[Hashable, ArchitectureView] = field(default_factory=OrderedDict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    max_profiles: int = DEFAULT_CACHE_PROFILES

    @property
    def last_seq(self) -> int | None:
        """읽은 마지막 ``seq``(없으면 None)."""
        return self.seqs[-1] if self.seqs else None

    def reset(self) -> None:
        """읽은 것을 모두 버린다(범위 구성이 바뀌었을 때). 새 목록 객체로 바꿔 읽는 쪽이 옛
        목록을 계속 볼 수 있게 한다."""
        self.events = []
        self.seqs = []
        self.tokens = None
        self.judged = OrderedDict()
        self.views = OrderedDict()

    def extend(self, new: Sequence[LogEvent]) -> None:
        """새 이벤트를 뒤에 붙인다(``seq``가 더 큰 것만 — 쪽 경계 중복 방지)."""
        last = self.last_seq
        for event in new:
            if last is not None and event.seq <= last:
                continue
            self.events.append(event)
            self.seqs.append(event.seq)
            last = event.seq
        if new:
            self.tokens = None
            self.views.clear()

    def judge(self, key: str, make: Callable[[], ProfileMatcher]) -> Judged:
        """프로필 키의 판정 결과를 읽은 이벤트 끝까지 채운다(새 이벤트만 판정).

        Args:
            key: 프로필 키(``profile_key``).
            make: 처음 판정할 때 판정기를 만드는 함수.
        """
        found = self.judged.get(key)
        if found is None:
            found = self.judged[key] = Judged(make())
        self.judged.move_to_end(key)
        while len(self.judged) > max(1, self.max_profiles):
            dropped, _ = self.judged.popitem(last=False)
            for view_key in [k for k in self.views if _profile_of(k) == dropped]:
                del self.views[view_key]
        start = len(found.matches)
        if start < len(self.events):
            matcher = found.matcher
            found.matches.extend(matcher.match(e) for e in self.events[start:])
        return found

    def match_at(self, key: str, event: LogEvent) -> EventMatch | None:
        """이미 판정한 같은 이벤트(같은 ``seq``·``uid``)의 판정 결과. 없으면 None."""
        found = self.judged.get(key)
        if found is None:
            return None
        seqs, events, matches = self.seqs, self.events, found.matches
        i = bisect_left(seqs, event.seq)
        if i >= len(matches) or i >= len(events) or seqs[i] != event.seq:
            return None
        if events[i].uid != event.uid:
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
        return sum(len(s.events) for s in self._scopes.values())

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
    "VIEW_CACHE_PER_SCOPE",
    "Judged",
    "MemoMatcher",
    "ScopeCache",
    "ScopeEvents",
    "profile_key",
    "scope_key",
]
