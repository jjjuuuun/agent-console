"""``LoopPublisher``(7R.4): 다른 스레드 알림을 바인드한 루프로, 같은 키 연속 한 번,
닫힌 루프 무시."""

from __future__ import annotations

import asyncio
import threading

from agent_console_modkit import LoopPublisher


def _thread_name() -> str:
    return threading.current_thread().name


def test_unbound_calls_directly() -> None:
    seen: list[tuple[str, int]] = []
    publisher: LoopPublisher[int] = LoopPublisher(lambda n: seen.append((_thread_name(), n)))
    publisher(1)
    assert seen == [(_thread_name(), 1)]
    assert publisher.loop is None


async def test_other_thread_moves_to_bound_loop() -> None:
    seen: list[tuple[str, int]] = []
    loop_thread = _thread_name()
    publisher: LoopPublisher[int] = LoopPublisher(lambda n: seen.append((_thread_name(), n)))
    publisher.bind(asyncio.get_running_loop())
    worker = threading.Thread(target=publisher, args=(7,), name="worker")
    worker.start()
    worker.join()
    assert seen == []  # 아직 루프가 돌지 않았다
    await asyncio.sleep(0.01)
    assert seen == [(loop_thread, 7)]
    publisher(8)  # 루프 스레드에서는 바로
    assert seen[-1] == (loop_thread, 8)


def test_consecutive_duplicates_published_once() -> None:
    seen: list[tuple[str, int]] = []
    publisher: LoopPublisher[tuple[str, int]] = LoopPublisher(seen.append, key=lambda p: p[0])
    for payload in (("a", 1), ("a", 2), ("b", 3), ("a", 4), ("a", 5)):
        publisher(payload)
    assert seen == [("a", 1), ("b", 3), ("a", 4)]


def test_none_key_skips_check_and_clears_last() -> None:
    seen: list[str] = []
    publisher: LoopPublisher[str] = LoopPublisher(
        seen.append, key=lambda p: None if p.startswith("auto") else p
    )
    for payload in ("x", "auto1", "auto1", "x", "x"):
        publisher(payload)
    assert seen == ["x", "auto1", "auto1", "x"]


def test_without_key_everything_published() -> None:
    seen: list[int] = []
    publisher: LoopPublisher[int] = LoopPublisher(seen.append)
    for n in (1, 1, 1):
        publisher(n)
    assert seen == [1, 1, 1]


def test_bind_resets_last_key() -> None:
    seen: list[int] = []
    publisher: LoopPublisher[int] = LoopPublisher(seen.append, key=lambda n: n)
    publisher(1)
    publisher.bind(None)
    publisher(1)
    assert seen == [1, 1]


def test_closed_loop_drops() -> None:
    seen: list[int] = []
    publisher: LoopPublisher[int] = LoopPublisher(seen.append)
    loop = asyncio.new_event_loop()
    publisher.bind(loop)
    loop.close()
    publisher(1)
    worker = threading.Thread(target=publisher, args=(2,))
    worker.start()
    worker.join()
    assert seen == []
    assert publisher.dropped == 2
    publisher.bind(None)  # 풀면 다시 바로 부른다
    publisher(3)
    assert seen == [3]


def test_loop_closing_between_check_and_schedule_is_dropped() -> None:
    class ClosingLoop(asyncio.SelectorEventLoop):
        def call_soon_threadsafe(self, *args: object, **kwargs: object) -> asyncio.Handle:
            raise RuntimeError("Event loop is closed")

    loop = ClosingLoop()
    try:
        seen: list[int] = []
        publisher: LoopPublisher[int] = LoopPublisher(seen.append)
        publisher.bind(loop)
        publisher(1)
        assert seen == []
        assert publisher.dropped == 1
    finally:
        loop.close()


def test_duplicates_from_many_threads_published_once() -> None:
    seen: list[str] = []
    publisher: LoopPublisher[str] = LoopPublisher(seen.append, key=lambda p: p)
    threads = [threading.Thread(target=publisher, args=("same",)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen == ["same"]
