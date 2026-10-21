"""``local-logs`` 사용량 출처(X13 구현, 신뢰 등급 ``estimated``).

로그 색인(``logs.query``)의 토큰 표본으로 창을 추정한다. 창 정의·예산·필터는 사용량 설정
(``usage.sources[{id: local-logs, config}]``) 데이터이고, 생략한 키는 기본값 데이터를 쓴다.

표본 캐시: (필터, 범위)마다 마지막으로 읽은 표본을 둔다. 새 로그가 색인되면(``logs.ingested`` →
``invalidate``) 그 출처를 읽는 캐시만 버린다. 표본은 수집으로만 늘어나므로 무효화 사이에는 다시
읽지 않는다. 창 계산(지금 시각 기준)은 매번 한다.
"""

from __future__ import annotations

import asyncio
import threading
from collections import OrderedDict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import KnownUsageTrust, UsageSourceDescriptor, UsageWindowSnapshot
from agent_console_contracts.logs import TokenSample
from agent_console_logs import LogFilter, LogQueryError, parse_log_filter
from agent_console_usage import UsageSourceContext

from .estimate import (
    CONFIG_SCHEMA,
    LocalLogsConfig,
    estimate_windows,
    load_default_config,
    parse_config,
    window_infos,
)
from .ports import LogIngest, LogTokenQuery

__all__ = ["DEFAULT_SOURCE_ID", "LocalLogsUsageSource"]

DEFAULT_SOURCE_ID = "local-logs"
"""기본 출처 id(연동 모듈 설정 ``source_id``로 바꿀 수 있다)."""

_SETUP_HELP = (
    "로컬 로그(기본: Claude Code 세션 로그)의 토큰 수를 창별로 더한 **추정**입니다. "
    "한도가 공개되지 않아 사용률은 사용량 설정 `usage.sources`의 이 출처 `config.budgets`"
    "(창 id → 토큰 수)를 적었을 때만 보입니다. 창·필터도 같은 곳에서 바꿉니다."
)


@dataclass(frozen=True, slots=True)
class _Cached:
    since: float
    sources: tuple[str, ...]
    samples: tuple[TokenSample, ...]


class LocalLogsUsageSource:
    """로그 토큰 표본 → 창 추정(``UsageSource`` 프로토콜).

    Args:
        query: 토큰 표본 조회(``logs.query``) 또는 그것을 돌려주는 함수(없으면 ``None``).
        source_id: 디스크립터 id(사용량 설정의 출처 id).
        defaults: 생략한 설정 키의 기본값(``None``이면 패키지 데이터).
        max_cache_entries: 표본 캐시 항목 수 상한(필터 조합별).
        ingest: 로그 수집(``logs.ingest``) 또는 그것을 돌려주는 함수. 주면 **첫 조회**가 읽을 로그
            출처의 수집(진행 중이면 그 수집)을 ``first_scan_wait_seconds``까지 기다린다 — 서버를
            띄운 직후 첫 ``GET /usage``에도 값이 나오게. 없으면 기다리지 않는다.
        first_scan_wait_seconds: 첫 조회가 수집을 기다리는 최대 시간(넘으면 지금 색인으로 답한다).

    디스크립터: ``auto_enable``(설정이 없어도 켜짐 — 로그가 없으면 창도 없다), ``windows``는 기본값
    데이터의 창 ``title``·``short_title``.
    """

    def __init__(
        self,
        query: LogTokenQuery | Callable[[], LogTokenQuery | None],
        *,
        source_id: str = DEFAULT_SOURCE_ID,
        defaults: Mapping[str, Any] | None = None,
        max_cache_entries: int = 8,
        ingest: LogIngest | Callable[[], LogIngest | None] | None = None,
        first_scan_wait_seconds: float = 5.0,
    ) -> None:
        self._query = query
        self._ingest = ingest
        self._first_wait = max(0.0, first_scan_wait_seconds)
        self._first_done = False
        self._defaults = dict(defaults) if defaults is not None else load_default_config()
        self._max = max(1, max_cache_entries)
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, _Cached] = OrderedDict()
        self._generation = 0  # invalidate마다 증가(조회 중에 버려진 결과를 넣지 않는다)
        self.descriptor = UsageSourceDescriptor(
            id=source_id,
            title="로컬 로그 추정",
            description="로컬 로그의 토큰 합(5시간 블록·7일 이동 창 등, 창 정의는 설정 데이터)",
            config_schema=CONFIG_SCHEMA,
            trust=KnownUsageTrust.ESTIMATED,
            setup_help=_SETUP_HELP,
            auto_enable=True,
            windows=window_infos(self._defaults),
        )

    @property
    def defaults(self) -> Mapping[str, Any]:
        """생략한 설정 키에 쓰는 기본값(읽기 전용 사본)."""
        return dict(self._defaults)

    def invalidate(self, source_ids: Collection[str] | None = None) -> int:
        """표본 캐시를 버린다. ``source_ids``가 있으면 그 로그 출처를 읽는 항목만(출처 필터가 없는
        항목은 늘 버린다). 버린 항목 수를 돌려준다."""
        wanted = None if source_ids is None else set(source_ids)
        with self._lock:
            drop = [
                k
                for k, c in self._cache.items()
                if wanted is None or not c.sources or wanted.intersection(c.sources)
            ]
            for key in drop:
                del self._cache[key]
            self._generation += 1
        return len(drop)

    def on_ingested(self, payload: Any) -> None:
        """``logs.ingested`` 구독 처리기(``source_ids``가 없으면 전부 버린다)."""
        ids = getattr(payload, "source_ids", None)
        self.invalidate(None if ids is None else [str(i) for i in ids])

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        """설정으로 창을 추정한다. 로그 색인이 없거나 범위에 표본이 없으면 빈 목록.

        Raises:
            ValueError: 필터 이름·값이 로그 질의가 모르는 것일 때(서비스가 출처 오류로 보고).
        """
        query = self._resolve()
        if query is None:
            return []
        cfg = parse_config(ctx.config, self._defaults)
        if not cfg.windows:
            return []
        await self._wait_first_scan(cfg)
        samples = await self._samples(query, cfg, now=ctx.now)
        return estimate_windows(samples, cfg, now=ctx.now, source_id=ctx.source_id)

    # ------------------------------------------------------------ 내부

    async def _wait_first_scan(self, cfg: LocalLogsConfig) -> None:
        """첫 조회 한 번만: 읽을 로그 출처의 수집을 정해진 시간까지 기다린다(실패·초과는 무시)."""
        if self._first_done:
            return
        self._first_done = True
        ingest = self._ingest
        if ingest is not None and not isinstance(ingest, LogIngest):
            ingest = ingest()
        if ingest is None or self._first_wait <= 0:
            return
        wanted = cfg.filter.get("source")
        ids = [wanted] if isinstance(wanted, str) else list(wanted) if wanted else None
        try:
            await asyncio.wait_for(asyncio.shield(ingest.scan(ids)), self._first_wait)
        except TimeoutError:
            return  # 수집은 배경에서 계속된다. 지금 색인으로 답한다
        except Exception:
            return  # 수집 실패는 로그 화면·경고가 알린다

    def _resolve(self) -> LogTokenQuery | None:
        query = self._query
        if isinstance(query, LogTokenQuery):
            return query
        return query()

    async def _samples(
        self, query: LogTokenQuery, cfg: LocalLogsConfig, *, now: float
    ) -> Sequence[TokenSample]:
        since = now - cfg.span_seconds
        key = cfg.cache_key()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached.since <= since:
                self._cache.move_to_end(key)
                return cached.samples
            generation = self._generation
        try:
            flt = parse_log_filter(cfg.filter, path="filter")
        except LogQueryError as exc:
            raise ValueError(f"로그 필터가 맞지 않습니다: {exc.path}") from None
        flt = _with_since(flt, since)
        rows = tuple(await asyncio.to_thread(query.token_samples, flt))
        entry = _Cached(since=since, sources=flt.source, samples=rows)
        with self._lock:
            if generation != self._generation:
                return rows  # 조회 중에 새 로그가 들어왔다: 이번 결과만 쓰고 담지 않는다
            self._cache[key] = entry
            self._cache.move_to_end(key)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)
        return rows


def _with_since(flt: LogFilter, since: float) -> LogFilter:
    return flt.with_(since=since, until=None, cursor=None)
