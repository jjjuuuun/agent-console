"""열린 자원 캐시(`OpenCache`): 이름 → 열린 핸들, 오래 안 쓴 순서·유휴·상한·종료.

프로젝트 공간 풀(기록 DB·메모리 DB 등)이 같이 쓴다. 캐시는 무엇을 여는지 모른다. 유휴·상한에
걸린 항목을 **어떻게** 할지(닫기·연결만 잠시 닫기)는 호출자가 정한다. ``shutdown()`` 뒤에는 새
항목을 받지 않는다(`CacheShut`) - 서버 종료 뒤 늦게 온 열기(배경 스레드)가 연결을 남기지 않게.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


class CacheShut(RuntimeError):  # noqa: N818 - 상태 이름(닫힌 캐시)
    """``shutdown()`` 뒤에 항목을 넣으려 했다."""


@dataclass
class _Slot[V]:
    value: V
    last_used: float


class OpenCache[V]:
    """이름 → 열린 값(스레드 안전, 잠금은 ``lock``으로 함께 잡을 수 있다).

    Args:
        close: 값을 닫는 함수(``drop``·``clear``·``shutdown``이 부른다).
        clock: 단조 시계(초).

    >>> closed = []
    >>> cache = OpenCache(closed.append, clock=lambda: 0.0)
    >>> cache.put("a", "A")
    >>> cache.get("a")
    'A'
    >>> cache.shutdown()
    >>> closed, cache.names(), cache.shut
    (['A'], [], True)
    >>> cache.put("b", "B")
    Traceback (most recent call last):
    ...
    agent_console_store.open_cache.CacheShut: open cache is shut down
    """

    def __init__(
        self, close: Callable[[V], None], *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._close = close
        self._clock = clock
        self._slots: OrderedDict[str, _Slot[V]] = OrderedDict()
        self._shut = False
        self.lock = threading.RLock()
        """캐시 잠금(호출자가 찾기 → 만들기 → 넣기를 한 번에 묶을 때 함께 잡는다)."""

    @property
    def shut(self) -> bool:
        """``shutdown()``을 불렀나."""
        return self._shut

    def peek(self, name: str) -> V | None:
        """값(쓴 시각을 바꾸지 않는다)."""
        with self.lock:
            slot = self._slots.get(name)
            return None if slot is None else slot.value

    def get(self, name: str) -> V | None:
        """값을 꺼내고 최근에 쓴 것으로 표시한다."""
        with self.lock:
            slot = self._slots.get(name)
            if slot is None:
                return None
            slot.last_used = self._clock()
            self._slots.move_to_end(name)
            return slot.value

    def put(self, name: str, value: V) -> None:
        """값을 넣는다(같은 이름이 있으면 바꾸되 옛 값은 닫지 않는다 - 먼저 ``drop``).

        Raises:
            CacheShut: ``shutdown()`` 뒤다(호출자는 연 값을 스스로 닫는다).
        """
        with self.lock:
            if self._shut:
                raise CacheShut("open cache is shut down")
            self._slots[name] = _Slot(value, self._clock())
            self._slots.move_to_end(name)

    def pop(self, name: str) -> V | None:
        """빼기만 한다(닫지 않는다)."""
        with self.lock:
            slot = self._slots.pop(name, None)
            return None if slot is None else slot.value

    def drop(self, name: str) -> None:
        """빼고 닫는다(없으면 아무 일도 없다)."""
        found = self.pop(name)
        if found is not None:
            self._close(found)

    def names(self) -> list[str]:
        """지금 든 이름(오래 안 쓴 것부터)."""
        with self.lock:
            return list(self._slots)

    def idle(self, seconds: float) -> list[tuple[str, V]]:
        """``seconds``초 넘게 안 쓴 항목(빼지 않는다, 오래된 것부터). 0 이하면 빈 목록."""
        if seconds <= 0:
            return []
        with self.lock:
            now = self._clock()
            return [(n, s.value) for n, s in self._slots.items() if now - s.last_used >= seconds]

    def over(self, limit: int) -> list[tuple[str, V]]:
        """``limit``개를 넘는 만큼 오래된 것부터 **빼서** 돌려준다(닫기는 호출자가 정한다)."""
        out: list[tuple[str, V]] = []
        with self.lock:
            while len(self._slots) > max(0, limit):
                name, slot = self._slots.popitem(last=False)
                out.append((name, slot.value))
        return out

    def clear(self) -> None:
        """모두 빼고 닫는다(다음 ``put``은 된다)."""
        with self.lock:
            for name in list(self._slots):
                self.drop(name)

    def shutdown(self) -> None:
        """모두 닫고, 그 뒤 ``put``을 거부한다(서버 종료). 여러 번 불러도 된다."""
        with self.lock:
            self._shut = True
            self.clear()


__all__ = ["CacheShut", "OpenCache"]
