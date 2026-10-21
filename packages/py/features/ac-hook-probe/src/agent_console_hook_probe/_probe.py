"""원래 명령을 자식 프로세스 그룹으로 실행하고 입출력을 바이트 그대로 중계한다(표준 라이브러리만).

- stdin은 받은 그대로 자식에게, 자식의 stdout·stderr는 받은 그대로 probe의 stdout·stderr로 보낸다
  (파일 기술자에 직접 쓰므로 텍스트 변환·버퍼링이 없다). 기록용으로는 앞부분만 따로 잡아 둔다.
- 자식은 새 프로세스 그룹(POSIX: 새 세션, Windows: `CREATE_NEW_PROCESS_GROUP`)으로 띄운다.
  probe가 종료 신호를 받으면 그룹에 전달하고, 유예 시간 뒤에도 남아 있으면 그룹을 강제 종료한다
  (agent_bench `terminate` 규칙).
- 시간 제한은 두지 않는다(Claude Code의 hook timeout에 맡긴다).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import FrameType
from typing import IO, Any

from ._record import DEFAULT_CAPTURE_BYTES, Capture, ProbeOutcome

__all__ = ["DEFAULT_GRACE_SECONDS", "SPAWN_FAILED_EXIT_CODE", "ProbeIO", "run_probe"]

DEFAULT_GRACE_SECONDS = 2.0
"""전달한 종료 신호 뒤 강제 종료까지 기다리는 시간(agent_bench `terminate`와 같음)."""

SPAWN_FAILED_EXIT_CODE = 127
"""원래 명령(또는 셸)을 띄우지 못했을 때 probe의 종료 코드(셸의 "명령 없음"과 같음)."""

_CHUNK = 65536


@dataclass(frozen=True, slots=True)
class ProbeIO:
    """probe가 중계할 파일 기술자(테스트에서 파이프로 바꾼다)."""

    stdin: int = 0
    stdout: int = 1
    stderr: int = 2


def _write_all(fd: int, data: bytes) -> bool:
    view = memoryview(data)
    try:
        while view:
            view = view[os.write(fd, view) :]
    except OSError:
        return False
    return True


def _pump_out(source: IO[bytes], fd: int, capture: Capture) -> None:
    alive = True
    while True:
        chunk = source.read(_CHUNK)  # bufsize=0: 원시 파이프라 온 만큼 바로 돌려준다
        if not chunk:
            break
        capture.add(chunk)
        if alive:
            alive = _write_all(fd, chunk)  # 받는 쪽이 닫혀도 자식이 막히지 않게 계속 읽는다
    source.close()


def _pump_in(fd: int, sink: IO[bytes], capture: Capture) -> None:
    try:
        while True:
            try:
                chunk = os.read(fd, _CHUNK)
            except OSError:
                break
            if not chunk:
                break
            capture.add(chunk)
            try:
                sink.write(chunk)
                sink.flush()
            except (BrokenPipeError, OSError, ValueError):
                break  # 자식이 stdin을 닫았다
    finally:
        with contextlib.suppress(OSError):
            sink.close()


def _group_kwargs(os_name: str) -> dict[str, Any]:
    if os_name == "nt":  # pragma: no cover - Windows 전용
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


@dataclass(slots=True)
class _Forwarder:
    """받은 종료 신호를 자식 그룹에 전달하고, 유예 뒤 강제 종료한다."""

    proc: subprocess.Popen[bytes]
    grace_seconds: float
    os_name: str
    received: int | None = None
    _timer: threading.Timer | None = field(default=None)

    def signals(self) -> list[int]:
        names = (
            ("SIGINT", "SIGBREAK", "SIGTERM")
            if self.os_name == "nt"
            else ("SIGTERM", "SIGINT", "SIGHUP", "SIGQUIT")
        )
        return [int(getattr(signal, n)) for n in names if hasattr(signal, n)]

    def __call__(self, signum: int, frame: FrameType | None) -> None:
        if self.received is None:
            self.received = signum
        self._send(signum)
        if self._timer is None:
            self._timer = threading.Timer(self.grace_seconds, self._kill)
            self._timer.daemon = True
            self._timer.start()

    def _send(self, signum: int) -> None:
        try:
            if self.os_name == "nt":  # pragma: no cover - Windows 전용
                if signum in (signal.SIGINT, getattr(signal, "SIGBREAK", -1)):
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    self.proc.terminate()
            else:
                os.killpg(self.proc.pid, signum)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _kill(self) -> None:
        try:
            if self.os_name == "nt":  # pragma: no cover - Windows 전용
                self.proc.kill()
            else:
                os.killpg(self.proc.pid, signal.SIGKILL)  # 리더가 끝났어도 남은 그룹원까지
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


def run_probe(
    invocation: Sequence[str] | str,
    *,
    io: ProbeIO = ProbeIO(),  # noqa: B008 - 불변 값
    capture_bytes: int = DEFAULT_CAPTURE_BYTES,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    handle_signals: bool = True,
    os_name: str = os.name,
    wall: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.monotonic,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> ProbeOutcome:
    """원래 명령을 실행하고 입출력을 중계한다.

    Args:
        invocation: 실행 인자(`shell_invocation`·`exec_invocation` 결과).
        io: 중계할 파일 기술자.
        capture_bytes: 스트림마다 기록용으로 보관할 최대 바이트(중계에는 제한 없음).
        grace_seconds: 신호 전달 뒤 강제 종료까지 기다리는 시간.
        handle_signals: 종료 신호 처리기를 설치한다(메인 스레드에서만 가능, 테스트는 끔).
        os_name, wall, monotonic, popen: 주입(테스트용).

    Returns:
        `ProbeOutcome`. 실행하지 못하면 `exit_code=None`, `error="spawn_failed: ..."`.
    """
    stdin_cap, stdout_cap, stderr_cap = (Capture(capture_bytes) for _ in range(3))
    started, t0 = wall(), monotonic()
    try:
        proc = popen(
            invocation,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            **_group_kwargs(os_name),
        )
    except OSError as exc:
        return ProbeOutcome(
            exit_code=None,
            started_at=started,
            ended_at=wall(),
            duration_ms=(monotonic() - t0) * 1000.0,
            stdin=stdin_cap,
            stdout=stdout_cap,
            stderr=stderr_cap,
            error=f"spawn_failed: {type(exc).__name__}",
        )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    forwarder = _Forwarder(proc, grace_seconds, os_name)
    previous: dict[int, Any] = {}
    if handle_signals:
        for signum in forwarder.signals():
            with contextlib.suppress(ValueError, OSError):
                previous[signum] = signal.signal(signum, forwarder)
    feeder = threading.Thread(target=_pump_in, args=(io.stdin, proc.stdin, stdin_cap), daemon=True)
    readers = [
        threading.Thread(target=_pump_out, args=(proc.stdout, io.stdout, stdout_cap), daemon=True),
        threading.Thread(target=_pump_out, args=(proc.stderr, io.stderr, stderr_cap), daemon=True),
    ]
    feeder.start()
    for reader in readers:
        reader.start()
    try:
        returncode = proc.wait()
        for reader in readers:
            reader.join()
        feeder.join(timeout=0.5)  # 보통 이미 끝났다(stdin EOF). 안 끝났으면 기다리지 않는다.
    finally:
        forwarder.cancel()
        for signum, handler in previous.items():
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signum, handler)
    ended = wall()
    duration_ms = (monotonic() - t0) * 1000.0
    exit_code: int | None = returncode
    died_by: int | None = None
    if returncode < 0 and os_name != "nt":
        exit_code, died_by = None, -returncode
    return ProbeOutcome(
        exit_code=exit_code,
        signal=died_by,
        started_at=started,
        ended_at=ended,
        duration_ms=duration_ms,
        stdin=stdin_cap,
        stdout=stdout_cap,
        stderr=stderr_cap,
        forwarded_signal=forwarder.received,
    )
