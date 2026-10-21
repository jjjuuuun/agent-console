"""대기열 값 객체와 저장소 예외."""

from __future__ import annotations

from dataclasses import dataclass


class QueueItemExistsError(LookupError):
    """같은 id의 대기열 항목이 이미 있다."""


class QueueItemNotFoundError(LookupError):
    """대기열 항목이 없다."""


@dataclass(frozen=True, slots=True)
class QueuedItem:
    """저장된 대기열 항목(`chat.busy_policy = queue`)."""

    id: str
    conversation_id: str
    position: int
    """대화 안의 순번(1 = 다음 차례). 항목을 지우면 빈틈 없이 다시 매겨진다."""
    text: str
    created_at: float
    held: bool = False
    """재시작 등으로 멈춘 항목. 사용자가 풀기 전에는 `pop_next`가 꺼내지 않는다."""
    held_reason: str | None = None


@dataclass(frozen=True, slots=True)
class QueueCounts:
    """대화의 대기열 규모."""

    queued: int
    held: int


__all__ = ["QueueCounts", "QueueItemExistsError", "QueueItemNotFoundError", "QueuedItem"]
