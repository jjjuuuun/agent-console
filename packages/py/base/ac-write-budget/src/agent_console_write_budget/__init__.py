"""쓰기 횟수 한도: 실행 하나가 여러 도구 묶음에 함께 넘기는 스레드 안전 카운터.

도구 묶음(메모리·위키 등)은 쓰기 전에 `take()`를 부르고, 거짓이면 쓰지 않고 "한도 넘음"
사유로 답한다. 한도 값·사유 코드·문구는 쓰는 쪽이 정한다. 이 패키지는 세는 일만 한다.

공개 API: `WriteBudget`(기본 구현), `WriteBudgetLike`(프로토콜 — `take()`만 있으면 된다).
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

__all__ = ["WriteBudget", "WriteBudgetLike"]


@runtime_checkable
class WriteBudgetLike(Protocol):
    """쓰기 횟수 한도(실행 하나가 함께 쓴다). `take()`가 거짓이면 쓰지 않는다."""

    def take(self) -> bool:
        """한 번 쓴다. 남은 횟수가 없으면 False."""
        ...


class WriteBudget:
    """`WriteBudgetLike` 기본 구현. `limit=None`이면 한도 없음. 스레드 안전.

    Attributes:
        limit: 최대 쓰기 횟수(None = 한도 없음).
        used: 지금까지 허락한 횟수.

    >>> b = WriteBudget(1)
    >>> b.take(), b.take(), b.used
    (True, False, 1)
    """

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        """한 번 쓴다. 남은 횟수가 없으면 False(이때 `used`는 늘지 않는다)."""
        with self._lock:
            if self.limit is not None and self.used >= self.limit:
                return False
            self.used += 1
            return True
