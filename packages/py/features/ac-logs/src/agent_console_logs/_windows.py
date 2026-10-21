"""로컬 로그 토큰 창 추정(design §4R.8 `local-logs`, R8.7 C). 순수 함수.

블록 규칙은 ccusage 방식이다: 첫 메시지 시각을 UTC 시 단위로 내려 블록을 시작하고 블록 길이 동안
이어진다. 블록이 끝난 뒤(또는 마지막 메시지에서 블록 길이 이상 쉰 뒤) 메시지는 새 블록을 연다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from agent_console_contracts.logs import LogTokenTotals, TokenSample

__all__ = ["TokenBlock", "block_windows", "rolling_totals", "sum_samples"]


@dataclass(frozen=True, slots=True)
class TokenBlock:
    """토큰 블록 하나.

    Attributes:
        start·end: 블록 시작·끝(epoch 초, `end = start + hours`).
        first_time·last_time: 블록 안 첫·마지막 메시지 시각.
        tokens: 블록 토큰 합(값 없는 항목은 None).
        samples: 블록 안 응답 수.
        active: `now`가 블록 안이고 마지막 메시지에서 블록 길이가 지나지 않았다.
    """

    start: float
    end: float
    first_time: float
    last_time: float
    tokens: LogTokenTotals
    samples: int
    active: bool


def _add(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def sum_samples(samples: Iterable[TokenSample]) -> LogTokenTotals:
    """토큰 표본 합. 어느 표본에도 없는 항목은 None(0으로 채우지 않음)."""
    inp = out = cr = cc = None
    for s in samples:
        inp = _add(inp, s.input_tokens)
        out = _add(out, s.output_tokens)
        cr = _add(cr, s.cache_read_input_tokens)
        cc = _add(cc, s.cache_creation_input_tokens)
    parts = [v for v in (inp, out, cr, cc) if v is not None]
    return LogTokenTotals(
        input=inp,
        output=out,
        cache_read=cr,
        cache_creation=cc,
        total=sum(parts) if parts else None,
    )


def block_windows(
    samples: Iterable[TokenSample], *, hours: float, now: float | None = None
) -> list[TokenBlock]:
    """토큰 표본을 ccusage 방식 블록으로 나눈다(시각 없는 표본은 뺀다).

    Args:
        samples: 응답별 토큰 표본(F-8로 중복 없는 것).
        hours: 블록 길이(시간, > 0).
        now: 활성 판정 시각(None이면 활성 블록 없음).

    Returns:
        시간순 블록 목록.

    Raises:
        ValueError: `hours <= 0`.
    """
    if hours <= 0:
        raise ValueError("hours는 0보다 커야 합니다")
    length = hours * 3600.0
    timed = sorted((s for s in samples if s.time is not None), key=lambda s: s.time or 0.0)
    blocks: list[TokenBlock] = []
    current: list[TokenSample] = []
    start = 0.0

    def close() -> None:
        first = current[0].time or 0.0
        last = current[-1].time or 0.0
        active = now is not None and now < start + length and now - last < length
        blocks.append(
            TokenBlock(
                start=start,
                end=start + length,
                first_time=first,
                last_time=last,
                tokens=sum_samples(current),
                samples=len(current),
                active=active,
            )
        )

    for sample in timed:
        t = sample.time or 0.0
        if current and (t >= start + length or t - (current[-1].time or 0.0) >= length):
            close()
            current = []
        if not current:
            start = t - (t % 3600.0)
        current.append(sample)
    if current:
        close()
    return blocks


def rolling_totals(samples: Iterable[TokenSample], *, seconds: float, now: float) -> LogTokenTotals:
    """`now - seconds <= time <= now`인 표본 합(이동 창)."""
    lo = now - seconds
    return sum_samples(s for s in samples if s.time is not None and lo <= s.time <= now)
