"""다른 스레드에서 온 알림을 이벤트 루프 스레드로 옮기는 발행기(design §7R.3, 7R.4).

저장소 쓰기·파일 감시 알림은 스레드(REST 동기 처리기·``asyncio.to_thread``·감시 스레드)에서
오지만 ``Hub`` 큐는 루프 스레드에서만 만져야 한다. ``LoopPublisher``는 ``bind(loop)``한 루프로
발행을 옮기고, ``key``를 주면 같은 키가 바로 이어 오는 알림은 한 번만 낸다(모듈 쓰기와 저장소
저장 알림이 같은 변경을 두 번 알리는 경우).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Hashable


class LoopPublisher[T]:
    """알림을 바인드한 이벤트 루프 스레드에서 ``publish``로 넘긴다.

    - ``bind(loop)`` 전(또는 ``bind(None)`` 뒤)에는 부른 스레드에서 바로 부른다
      (단독 라이브러리 사용·테스트).
    - 루프 스레드에서 부르면 바로, 다른 스레드에서 부르면 ``call_soon_threadsafe``로 옮긴다.
    - 바인드한 루프가 닫혔으면 알림을 버린다(종료 중 늦게 온 알림, ``dropped``를 센다).
    - ``key``가 있으면 직전 알림과 키가 같은 알림을 버린다. ``key``가 None을 돌려주면 그 알림은
      중복 검사 없이 내고 직전 키를 지운다(다음 알림은 늘 나간다).

    Args:
        publish: 루프 스레드에서 부를 발행 함수(예: 허브 ``publish``를 감싼 함수).
        key: 중복 판정 키 함수(None = 중복 검사 안 함).

    Example:
        >>> seen = []
        >>> pub = LoopPublisher(seen.append, key=lambda n: n // 10)
        >>> for n in (1, 2, 15, 3):
        ...     pub(n)
        >>> seen
        [1, 15, 3]
    """

    def __init__(
        self,
        publish: Callable[[T], None],
        *,
        key: Callable[[T], Hashable | None] | None = None,
    ) -> None:
        self._publish = publish
        self._key = key
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last: Hashable | None = None
        self._lock = threading.Lock()
        self.dropped = 0
        """닫힌 루프 때문에 버린 알림 수(중복으로 거른 것은 세지 않는다)."""

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """지금 바인드한 루프(없으면 None)."""
        return self._loop

    def bind(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """발행을 옮길 루프(None = 풀기 — 이후 바로 부른다). 직전 키도 지운다."""
        with self._lock:
            self._loop = loop
            self._last = None

    def __call__(self, payload: T) -> None:
        """알림 하나를 낸다(중복이면 버림)."""
        if self._key is not None:
            current = self._key(payload)
            with self._lock:
                if current is not None and current == self._last:
                    return
                self._last = current
        loop = self._loop
        if loop is None:
            self._publish(payload)
            return
        if loop.is_closed():
            self.dropped += 1
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._publish(payload)
            return
        try:
            loop.call_soon_threadsafe(self._publish, payload)
        except RuntimeError:  # 확인과 예약 사이에 루프가 닫혔다
            self.dropped += 1


__all__ = ["LoopPublisher"]
