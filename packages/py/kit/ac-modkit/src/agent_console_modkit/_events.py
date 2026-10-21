"""모듈 이벤트 버스(프로세스 안, design §3R.1.5).

- 토픽(``Topic[T]``) 이름별 구독자 목록. 항목 형식은 모른다.
- **구독자 예외 격리**: 한 구독자가 실패해도 다른 구독자와 발행자는 계속한다
  (로그 + ``errors`` 증가).
- 순서는 보장하지 않는다(지금 구현은 구독 순서지만 계약이 아니다).
- 비동기 처리기(코루틴을 돌려주는 처리기)는 ``publish``에서 실행 중인 이벤트 루프에 작업으로 띄우고,
  ``deliver``에서는 끝날 때까지 기다린다. ``drain``은 띄운 작업이 모두 끝날 때까지 기다린다.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ._ports import Topic

type Handler[T] = Callable[[T], Awaitable[None] | None]

_default_log = logging.getLogger("agent_console_modkit.events")


class EventBus:
    """토픽 → 구독자. 전역 상태 없음(호스트가 하나 만들어 모듈에 나눠 준다).

    Args:
        logger: 구독자 예외를 남길 로거. 기본 ``agent_console_modkit.events``.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._subs: dict[str, list[Callable[[Any], Awaitable[None] | None]]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._log = logger or _default_log
        self.errors = 0
        """구독자 예외 수(관측·테스트용)."""

    def subscribe[T](self, topic: Topic[T], handler: Handler[T]) -> Callable[[], None]:
        """구독한다. 돌려준 함수를 부르면 해제된다(여러 번 불러도 안전)."""
        subs = self._subs.setdefault(topic.name, [])
        subs.append(handler)

        def unsubscribe() -> None:
            current = self._subs.get(topic.name)
            if current is not None and handler in current:
                current.remove(handler)
                if not current:
                    del self._subs[topic.name]

        return unsubscribe

    def subscriber_count(self, topic: Topic[Any] | None = None) -> int:
        if topic is not None:
            return len(self._subs.get(topic.name, ()))
        return sum(len(v) for v in self._subs.values())

    def publish[T](self, topic: Topic[T], item: T) -> None:
        """막히지 않고 발행한다. 동기 처리기는 바로 부르고, 비동기 처리기는 작업으로 띄운다.

        실행 중인 이벤트 루프가 없는데 처리기가 코루틴을 돌려주면 그 코루틴은 닫고 오류로 센다.
        """
        for handler in list(self._subs.get(topic.name, ())):
            result = self._call(topic, handler, item)
            if result is None:
                continue
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                _close(result)
                self._fail(topic, "실행 중인 이벤트 루프가 없어 비동기 구독자를 부르지 못했습니다")
                continue
            task = loop.create_task(self._guard(topic, result))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def deliver[T](self, topic: Topic[T], item: T) -> None:
        """발행하고 이 항목의 모든 처리기(비동기 포함)가 끝날 때까지 기다린다."""
        pending: list[Awaitable[None]] = []
        for handler in list(self._subs.get(topic.name, ())):
            result = self._call(topic, handler, item)
            if result is not None:
                pending.append(self._guard(topic, result))
        if pending:
            await asyncio.gather(*pending)

    async def drain(self) -> None:
        """``publish``가 띄운 작업이 모두 끝날 때까지 기다린다(종료·테스트용)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ------------------------------------------------------------ 내부

    def _call(
        self,
        topic: Topic[Any],
        handler: Callable[[Any], Awaitable[None] | None],
        item: Any,
    ) -> Awaitable[None] | None:
        try:
            result = handler(item)
        except Exception:
            self._fail(topic, "구독자 실패", exc_info=True)
            return None
        return result if inspect.isawaitable(result) else None

    async def _guard(self, topic: Topic[Any], awaitable: Awaitable[None]) -> None:
        try:
            await awaitable
        except asyncio.CancelledError:
            raise
        except Exception:
            self._fail(topic, "비동기 구독자 실패", exc_info=True)

    def _fail(self, topic: Topic[Any], message: str, *, exc_info: bool = False) -> None:
        self.errors += 1
        self._log.error("모듈 이벤트 %s: %s", topic.name, message, exc_info=exc_info)


def _close(awaitable: Awaitable[None]) -> None:
    close = getattr(awaitable, "close", None)
    if callable(close):
        close()


__all__ = ["EventBus", "Handler"]
