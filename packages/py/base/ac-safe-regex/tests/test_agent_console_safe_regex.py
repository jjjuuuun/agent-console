"""사용자 정규식 검증·시간 제한 실행(ReDoS 회귀 포함)."""

from __future__ import annotations

import dataclasses
import random
import threading
import time
from collections.abc import Callable

import pytest

from agent_console_safe_regex import (
    RegexTimeoutError,
    SafeMatch,
    SafePattern,
    UnsafeRegexError,
    check_user_regex,
    compile_user_regex,
)

HARD_LIMIT_SECONDS = 5.0
"""테스트 자체의 상한. 이 안에 끝나지 않으면 실패(무한 대기 방지)."""

EVIL_INPUT = "a" * 4096 + "c"


def run_bounded[T](fn: Callable[[], T]) -> tuple[T | BaseException, float]:
    """``fn`` 을 데몬 스레드에서 실행하고 상한 안에 끝났는지 확인한다."""
    box: list[T | BaseException] = []

    def target() -> None:
        try:
            box.append(fn())
        except BaseException as exc:
            box.append(exc)

    t = threading.Thread(target=target, daemon=True)
    start = time.perf_counter()
    t.start()
    t.join(HARD_LIMIT_SECONDS)
    elapsed = time.perf_counter() - start
    assert not t.is_alive(), f"상한 {HARD_LIMIT_SECONDS}초 안에 끝나지 않음"
    return box[0], elapsed


@pytest.mark.parametrize("pattern", ["(a|a)*b", "(.*a){20}b"])
def test_qa_redos_regression_rejected_or_bounded(pattern: str) -> None:
    """QA 재현 패턴: 검증에서 거부되거나, 통과하더라도 시간 제한 안에 끝난다."""

    def attempt() -> object:
        try:
            pat = compile_user_regex(pattern, timeout=0.1)
        except UnsafeRegexError as exc:
            return exc
        try:
            return pat.search(EVIL_INPUT)
        except RegexTimeoutError as exc:
            return exc

    result, elapsed = run_bounded(attempt)
    assert isinstance(result, UnsafeRegexError | RegexTimeoutError) or result is None
    assert elapsed < 2.0


def test_timeout_bounds_catastrophic_pattern_that_passes_heuristics() -> None:
    pat = compile_user_regex(r"(\w|a)*\d", timeout=0.05)  # 휴리스틱을 통과하는 폭주 패턴
    result, elapsed = run_bounded(lambda: pat.search(EVIL_INPUT))
    assert isinstance(result, RegexTimeoutError)
    assert elapsed < 2.0


def test_max_input_chars_truncates() -> None:
    pat = compile_user_regex("needle", max_input_chars=10)
    assert pat.search("x" * 20 + "needle") is None
    m = pat.search("needle" + "x" * 20)
    assert isinstance(m, SafeMatch)
    assert (m.start, m.end, m.text) == (0, 6, "needle")


def test_named_groups_match_and_ignore_case() -> None:
    pat = compile_user_regex(r"^@(?P<category>[\w-]+)\s+", required_groups=("category",))
    m = pat.match("@Foo-1 rest")
    assert m is not None
    assert m.group("category") == "Foo-1"
    assert m.group("nope") is None
    assert pat.group_names == frozenset({"category"})
    assert compile_user_regex("abc", ignore_case=True).search("xABC") is not None
    assert compile_user_regex("abc").search("xABC") is None


@pytest.mark.parametrize(
    "pattern",
    [
        "(a|a)*b",
        "(.*a){20}b",
        "(a+)+",
        r"(\w*x)*",
        "(x+){2,}",
        "(?:a*b)*",
        "(a{2})+",
        "(a|ab)+",
        "(.|x)*",
        "(|a)+",
        "a" * 600,
        "",
        "[",
        "(?P<",
    ],
)
def test_unsafe_or_invalid_rejected(pattern: str) -> None:
    with pytest.raises(UnsafeRegexError):
        check_user_regex(pattern)


@pytest.mark.parametrize(
    "pattern",
    [
        r"^(fix|feat)\b",
        r"\d+-\d+",
        "(ab)+",
        "(a|b)*c",
        r"(\+)+",
        "(ab){3}",
        "(a+)?",
        "(a+){1}",
        "(?>a+)+",
        "(a+)++",
        "(?i)abc",
        "[(]+(a)*",
        r"^@(?P<category>[\w-]+)\s+",
    ],
)
def test_safe_patterns_accepted(pattern: str) -> None:
    check_user_regex(pattern)


def test_required_group_and_arg_validation() -> None:
    with pytest.raises(UnsafeRegexError, match="category"):
        check_user_regex(r"^@(\w+)", required_groups=("category",))
    with pytest.raises(ValueError, match="timeout"):
        compile_user_regex("a", timeout=0)
    with pytest.raises(ValueError, match="max_input_chars"):
        compile_user_regex("a", max_input_chars=0)


def test_finditer_returns_all_matches_with_group_spans() -> None:
    pat = compile_user_regex(r"--(?P<name>\w+)=(?P<value>\w+)(?P<tail>!)?")
    found = pat.finditer("a --x=1 b --yy=22!")
    assert [m.text for m in found] == ["--x=1", "--yy=22!"]
    assert found[1].span("value") == (15, 17)
    assert found[0].span("tail") is None
    assert found[0].span("missing") is None


def test_finditer_times_out_on_whole_scan() -> None:
    pat = compile_user_regex(r"(?:a|aa)c", timeout=0.01, max_input_chars=10_000_000)
    # 대안이 반복되지 않아 검증은 통과하지만, 매치 실패가 매우 많은 입력은 시간 제한에 걸릴 수 있다.
    result, _ = run_bounded(lambda: pat.finditer("ab" * 2_000_000))
    assert isinstance(result, (list, RegexTimeoutError))


# ---------------------------------------------------------------- 남의 CPU로 난 시간 초과(CI 회귀)


class _StallingPattern:
    """``regex`` 패턴을 감싸 처음 ``stalls`` 번은 CPU를 쓰지 않고 시간 초과를 낸다.

    `regex`의 timeout은 프로세스 전체 CPU(``clock()``)로 재므로, 다른 스레드가 바쁜 동안 매치
    스레드가 밀리면 짧은 매치도 시간 초과가 난다. 그 상황을 결정적으로 흉내 낸다.
    """

    def __init__(self, inner: object, stalls: int) -> None:
        self._inner = inner
        self.stalls = stalls
        self.calls = 0
        self.kwargs: list[dict[str, object]] = []

    def __getattr__(self, name: str) -> object:
        target = getattr(self._inner, name)
        if name not in {"match", "search", "finditer"}:
            return target

        def call(*args: object, **kwargs: object) -> object:
            self.calls += 1
            self.kwargs.append(kwargs)
            if self.stalls > 0:
                self.stalls -= 1
                raise TimeoutError("regex timed out")
            return target(*args, **kwargs)

        return call


def _stalling(pattern: str, stalls: int) -> tuple[SafePattern, _StallingPattern]:
    pat = compile_user_regex(pattern)
    fake = _StallingPattern(pat._compiled, stalls)  # 구현 대역 주입
    return dataclasses.replace(pat, _compiled=fake), fake  # type: ignore[arg-type]


@pytest.mark.parametrize("method", ["match", "search", "finditer"])
def test_timeout_from_other_threads_cpu_is_retried(method: str) -> None:
    pat, fake = _stalling(r"(?P<id>\d+)", stalls=2)
    result = getattr(pat, method)("12 34")
    found = result if isinstance(result, list) else [result]
    assert found
    assert found[0] is not None
    assert found[0].group("id") == "12"
    assert fake.calls == 3
    assert all(kw.get("concurrent") is False for kw in fake.kwargs)  # 매치 중 GIL 유지


def test_persistent_foreign_timeout_still_raises() -> None:
    pat, fake = _stalling(r"\d+", stalls=10)
    with pytest.raises(RegexTimeoutError):
        pat.search("12")
    assert fake.calls == 3  # 상한: 시도 횟수 제한


def test_own_cpu_timeout_is_not_retried() -> None:
    pat = compile_user_regex(r"(\w|a)*\d", timeout=0.02)
    start = time.perf_counter()
    result, _ = run_bounded(lambda: pat.search(EVIL_INPUT))
    assert isinstance(result, RegexTimeoutError)
    assert time.perf_counter() - start < 2.0


def test_short_match_survives_gil_holding_thread() -> None:
    """GIL을 오래 쥐는 다른 스레드가 있어도 짧은 매치는 시간 초과가 나지 않는다.

    예전에는 `regex`가 매치 시작에 GIL을 놓았다가 다시 잡으면서 그 사이 다른 스레드의 긴 C 호출을
    기다렸고, 그 CPU 시간이 프로세스 ``clock()`` 에 더해져 몇 µs짜리 매치가 시간 초과로 끝났다
    (공개 CI에서 정상 작업 문서를 통째로 못 읽은 원인). 지금은 매치 중 GIL을 놓지 않는다.
    """
    stop = threading.Event()
    big = [random.random() for _ in range(1_000_000)]

    def hog() -> None:
        while not stop.is_set():
            sorted(big)  # GIL을 쥔 채 수백 ms 걸리는 C 호출

    thread = threading.Thread(target=hog, daemon=True)
    thread.start()
    try:
        pat = compile_user_regex(r"^\s*-\s+\[(?P<m>.)\]\s+(?P<id>[\d.]+)", timeout=0.1)
        line = "  - [x] 12.3 제목 [owner: a] [req: R1, R2]"
        deadline = time.perf_counter() + 1.0
        while time.perf_counter() < deadline:
            m = pat.search(line)
            assert m is not None
            assert m.group("id") == "12.3"
    finally:
        stop.set()
        thread.join()
