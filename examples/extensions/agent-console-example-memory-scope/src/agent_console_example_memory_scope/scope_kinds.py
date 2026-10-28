"""계산 범위 종류 하나: ISO 주차(`{year}-W{week}`).

데이터 범위 종류(id 틀)는 접근 맥락의 값만 읽는다. 이 예제는 맥락 밖의 값(지금 시각)으로 범위 id를
계산하므로 `resolver`를 쓰는 플러그인으로 낸다. 시계는 주입받는다(테스트는 고정 시각).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Final

from agent_console_contracts.memory import MemoryAccessContext
from agent_console_memory import MemoryScopeKind

KIND_ID: Final = "example-week"
"""예제 범위 종류 id(예제가 정한 임의 값)."""

LABEL: Final = "주차(예제)"
DESCRIPTION: Final = "기록한 주(ISO 주차, UTC 기준)마다 나뉘는 기록"

type Clock = Callable[[], datetime]
"""지금 시각을 돌려주는 함수."""


def utc_now() -> datetime:
    """기본 시계(UTC)."""
    return datetime.now(UTC)


def iso_week_id(moment: date) -> str:
    """날짜 → ISO 주차 범위 id `{year}-W{week}`(주는 두 자리, 연도는 ISO 주차 연도).

    >>> from datetime import date
    >>> iso_week_id(date(2026, 10, 28))
    '2026-W44'
    >>> iso_week_id(date(2027, 1, 1))  # ISO 주차로는 2026년의 마지막 주
    '2026-W53'
    """
    year, week, _weekday = moment.isocalendar()
    return f"{year}-W{week:02d}"


def iso_week_scope_kind(clock: Clock = utc_now, *, kind_id: str = KIND_ID) -> MemoryScopeKind:
    """ISO 주차 계산 범위 종류(맥락은 읽지 않고 `clock()`의 주차를 범위 id로 쓴다).

    Args:
        clock: 지금 시각. 지역 시간대 주차가 필요하면 그 시간대의 `datetime`을 돌려준다.
        kind_id: 범위 종류 id.

    >>> from datetime import UTC, datetime
    >>> kind = iso_week_scope_kind(lambda: datetime(2026, 10, 28, tzinfo=UTC))
    >>> kind.resolve(MemoryAccessContext())
    '2026-W44'
    """

    def resolve(_context: MemoryAccessContext) -> str:
        return iso_week_id(clock())

    return MemoryScopeKind(id=kind_id, label=LABEL, description=DESCRIPTION, resolver=resolve)


def scope_kinds() -> list[MemoryScopeKind]:
    """entry point 대상: 범위 종류 목록(UTC 시계). 출처는 로더가 `plugin:<배포 이름>`으로 채운다."""
    return [iso_week_scope_kind()]
