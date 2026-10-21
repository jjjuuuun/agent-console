"""사용량 보고 서비스: 부분 조회(``parts``)대로 필요한 것만 계산한다(design §3R.5, E-14).

- ``windows``(창 스냅샷)는 출처 수집뿐이다. 실행 기록(토큰 집계)을 읽지 않는다.
- ``tokens``(토큰 집계)는 ``TokenRollups``가 있을 때만 부른다. 없으면 빈 목록이다.
- 요청하지 않은 부분은 ``None``(계약 ``UsageReport``: null = 요청 안 함).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, tzinfo

from agent_console_contracts import (
    USAGE_REPORT_PARTS,
    UsageReport,
    UsageSettings,
    UsageSourceInfo,
)
from agent_console_usage import UsageService

from .ports import TokenRollups

PART_WINDOWS = "windows"
PART_TOKENS = "tokens"


def parse_parts(
    values: Iterable[str] | None, *, known: Iterable[str] = USAGE_REPORT_PARTS
) -> frozenset[str]:
    """``parts`` 쿼리 값(쉼표 목록, 여러 번 가능) → 알려진 부분 이름 집합.

    ``None``이거나 빈 값뿐이면 전부다(생략 = 전부). 모르는 이름은 무시한다(전방 호환).

    >>> sorted(parse_parts(["windows"]))
    ['windows']
    >>> sorted(parse_parts(None))
    ['tokens', 'windows']
    >>> sorted(parse_parts(["windows,future"]))
    ['windows']
    """
    allowed = tuple(known)
    if values is None:
        return frozenset(allowed)
    names = [n.strip() for v in values for n in v.split(",") if n.strip()]
    if not names:
        return frozenset(allowed)
    return frozenset(n for n in names if n in allowed)


def local_timezone() -> tzinfo:
    """서버 시간대(토큰 집계의 일 단위 기준)."""
    return datetime.now().astimezone().tzinfo or UTC


class UsageReportService:
    """``GET /usage``·``/usage/sources``의 로직(HTTP 없이도 쓴다).

    Args:
        usage: 출처 수집 서비스(``agent_console_usage.UsageService``).
        settings: 지금 사용량 사용자 설정(``usage.sources``)을 돌려주는 함수. None을 돌려주면
            등록된 출처 전부 켜짐.
        rollups: 토큰 집계 제공자. 없으면 ``rollups``는 빈 목록.
        rollup_run_limit: 토큰 집계 범위(최근 Run 수).
        clock: 현재 시각(Unix epoch 초, ``generated_at``).
        tz: 일 단위 집계 기준 시간대를 돌려주는 함수.
    """

    def __init__(
        self,
        usage: UsageService,
        *,
        settings: Callable[[], UsageSettings | None] = lambda: None,
        rollups: TokenRollups | None = None,
        rollup_run_limit: int = 500,
        clock: Callable[[], float],
        tz: Callable[[], tzinfo] = local_timezone,
    ) -> None:
        self._usage = usage
        self._settings = settings
        self._rollups = rollups
        self._limit = rollup_run_limit
        self._clock = clock
        self._tz = tz

    @property
    def usage(self) -> UsageService:
        return self._usage

    async def report(self, parts: Iterable[str] | None = None) -> UsageReport:
        """요청한 부분만 계산한 보고.

        Args:
            parts: 부분 이름(``parse_parts`` 결과 등). None이면 전부.
        """
        wanted = parse_parts(None) if parts is None else frozenset(parts)
        windows = None
        if PART_WINDOWS in wanted:
            windows = await self._usage.collect(self._settings())
        rollups = None
        if PART_TOKENS in wanted:
            rollups = []
            if self._rollups is not None:
                provider = self._rollups
                rows = await asyncio.to_thread(provider.rollups, limit=self._limit, tz=self._tz())
                rollups = list(rows)
        return UsageReport(windows=windows, rollups=rollups, generated_at=self._clock())

    def sources(self) -> list[UsageSourceInfo]:
        """출처 디스크립터 + 사용 여부·설정 + 마지막 수집 상태."""
        return self._usage.sources(self._settings())


__all__ = ["PART_TOKENS", "PART_WINDOWS", "UsageReportService", "local_timezone", "parse_parts"]
