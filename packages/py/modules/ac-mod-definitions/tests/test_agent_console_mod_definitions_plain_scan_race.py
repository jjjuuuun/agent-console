"""PlainSecretScan: 계산 도중 무효화된 결과는 담지 않고, 무효화는 계산을 기다리지 않는다
(3R.10 QA, 3R.12에서 mod-definitions로 이동)."""

from __future__ import annotations

import threading

from agent_console_contracts import Issue
from agent_console_mod_definitions import PlainSecretScan


def _issue(tag: str) -> Issue:
    return Issue(severity="warning", code="x", message=tag)


def test_invalidate_during_compute_is_not_cached() -> None:
    calls: list[int] = []
    holder: list[PlainSecretScan] = []

    def compute() -> list[Issue]:
        calls.append(1)
        if len(calls) == 1:
            holder[0].invalidate()  # 계산 도중 쓰기(같은 스레드여도 잠금 없이 통과)
        return [_issue(str(len(calls)))]

    scan = PlainSecretScan(compute)
    holder.append(scan)
    assert scan.warnings()[0].message == "1"
    assert scan.warnings()[0].message == "2"  # 낡은 결과가 캐시되지 않았다
    assert scan.warnings()[0].message == "2"  # 이번엔 캐시
    assert len(calls) == 2


def test_invalidate_while_other_thread_computes_does_not_deadlock() -> None:
    started, release = threading.Event(), threading.Event()

    def compute() -> list[Issue]:
        started.set()
        release.wait(5)
        return []

    scan = PlainSecretScan(compute)
    worker = threading.Thread(target=scan.warnings)
    worker.start()
    assert started.wait(5)
    invalidator = threading.Thread(target=scan.invalidate)
    invalidator.start()
    invalidator.join(2)
    assert not invalidator.is_alive()
    release.set()
    worker.join(5)


def test_invalidate_between_compare_and_store_is_not_lost() -> None:
    """세대 비교와 캐시 대입 사이에 무효화가 끼면 낡은 결과가 남던 틈(3R.10 QA 후속).

    계산이 끝난 직후, 결과를 담기 전에 다른 스레드가 무효화한다. 비교와 대입이 같은 상태 잠금
    안에 있으므로 무효화는 그 앞이나 뒤에만 들어간다: 앞이면 담지 않고, 뒤면 담은 것을 지운다.
    어느 쪽이든 다음 읽기는 다시 계산한다.
    """
    results = iter(["old", "new", "new"])
    done, go = threading.Event(), threading.Event()
    scan: PlainSecretScan

    def compute() -> list[Issue]:
        value = next(results)
        if value == "old":
            done.set()
            go.wait(5)
        return [_issue(value)]

    scan = PlainSecretScan(compute)
    worker = threading.Thread(target=scan.warnings)
    worker.start()
    assert done.wait(5)
    invalidator = threading.Thread(target=scan.invalidate)
    invalidator.start()
    go.set()
    invalidator.join(5)
    worker.join(5)
    assert scan.warnings()[0].message == "new"


def test_concurrent_readers_compute_once() -> None:
    calls: list[int] = []
    gate = threading.Event()

    def compute() -> list[Issue]:
        calls.append(1)
        gate.wait(5)
        return [_issue("x")]

    scan = PlainSecretScan(compute)
    threads = [threading.Thread(target=scan.warnings) for _ in range(4)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert len(calls) == 1
