"""플랫폼 PTY 어댑터: POSIX ``ptyprocess``, Windows ``pywinpty``(선택 추가 기능 ``windows``).

``PtySession``은 ``PtySpawner``(→ ``PtyHandle``)만 안다. 어댑터는 외부 라이브러리를 이 모양으로
감싼다. 라이브러리가 없거나 이 플랫폼에서 PTY를 쓸 수 없으면 ``PtyUnavailableError``다. 외부
라이브러리는 쓸 때 가져온다(패키지 import만으로는 불러오지 않는다).
"""

from __future__ import annotations

import codecs
import contextlib
import importlib
import os
import select
import signal
import sys
import threading
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

_POLL_S = 0.2


def _platform() -> str:
    """지금 플랫폼(테스트·정적 분석에서 분기를 고정하지 않게 함수로 읽는다)."""
    return sys.platform


class PtyUnavailableError(RuntimeError):
    """이 환경에서 PTY를 쓸 수 없다(라이브러리 미설치·플랫폼 미지원).

    Attributes:
        reason: 기계용 사유(``missing_library``·``unsupported_platform``).
        hint: 사람이 읽을 해결 방법(설치 명령 등).
    """

    def __init__(self, reason: str, hint: str) -> None:
        super().__init__(hint)
        self.reason = reason
        self.hint = hint


@runtime_checkable
class PtyHandle(Protocol):
    """PTY에 붙은 하위 프로세스 하나(어댑터가 구현). 메서드는 스레드에서 불릴 수 있다."""

    @property
    def pid(self) -> int | None:
        """프로세스 id(모르면 None)."""
        ...

    def read(self, size: int) -> str:
        """출력을 읽는다. 올 때까지 막힌다. 출력이 끝나면 ``EOFError``."""
        ...

    def write(self, data: str) -> None:
        """입력을 보낸다(글자 그대로, 줄 끝 변환 없음)."""
        ...

    def is_alive(self) -> bool:
        """아직 실행 중인가."""
        ...

    def exit_code(self) -> int | None:
        """종료 코드(실행 중이면 None, 신호로 끝났으면 음수 신호 번호)."""
        ...

    def terminate(self) -> None:
        """끝내 달라고 요청한다(POSIX SIGTERM을 프로세스 그룹에)."""
        ...

    def kill(self) -> None:
        """강제로 끝낸다(POSIX SIGKILL을 프로세스 그룹에)."""
        ...

    def resize(self, cols: int, rows: int) -> None:
        """터미널 크기를 바꾼다."""
        ...

    def close(self) -> None:
        """PTY를 닫는다(읽기는 ``EOFError``로 끝난다). 여러 번 불러도 된다."""
        ...


class PtySpawner(Protocol):
    """하위 프로세스를 PTY에 붙여 띄운다."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        cwd: str | None,
        cols: int,
        rows: int,
    ) -> PtyHandle:
        """띄운다.

        Raises:
            FileNotFoundError: 실행 파일이 없다.
            PtyUnavailableError: PTY를 쓸 수 없다.
            OSError: 그 밖의 시작 실패.
        """
        ...


def _import(module: str, hint: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise PtyUnavailableError("missing_library", hint) from exc


# ---------------------------------------------------------------- POSIX


class PosixPty:
    """``ptyprocess.PtyProcess``를 감싼 ``PtyHandle``. 출력은 UTF-8(깨진 바이트는 대체 글자)."""

    def __init__(self, proc: Any, *, encoding: str = "utf-8") -> None:
        self._proc = proc
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        self._encoding = encoding
        self._closed = threading.Event()

    @property
    def pid(self) -> int | None:
        return int(self._proc.pid)

    def read(self, size: int) -> str:
        fd = self._proc.fd
        while True:
            if self._closed.is_set():
                raise EOFError
            try:
                ready, _, _ = select.select([fd], [], [], _POLL_S)
            except (OSError, ValueError) as exc:  # 닫힌 fd
                raise EOFError from exc
            if not ready:
                continue
            try:
                data: bytes = self._proc.read(size)
            except (OSError, ValueError) as exc:
                raise EOFError from exc
            text = self._decoder.decode(data)
            if text:
                return text

    def write(self, data: str) -> None:
        self._proc.write(data.encode(self._encoding))

    def is_alive(self) -> bool:
        try:
            return bool(self._proc.isalive())
        except Exception:  # 이미 거둔 프로세스 등
            return False

    def exit_code(self) -> int | None:
        if self.is_alive():
            return None
        status = self._proc.exitstatus
        if status is not None:
            return int(status)
        sig = self._proc.signalstatus
        return -int(sig) if sig is not None else None

    def _signal(self, sig: int) -> None:
        pid = int(self._proc.pid)
        try:
            os.killpg(pid, sig)  # pty.fork는 setsid로 새 세션·그룹을 만든다 → 손자까지
        except (ProcessLookupError, PermissionError):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, sig)

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)

    def resize(self, cols: int, rows: int) -> None:
        self._proc.setwinsize(rows, cols)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        with contextlib.suppress(Exception):
            self._proc.close(force=True)


def posix_spawner(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None,
    cwd: str | None,
    cols: int,
    rows: int,
) -> PtyHandle:
    """POSIX ``ptyprocess``로 띄운다(``PtySpawner``).

    Raises:
        PtyUnavailableError: Windows이거나 ``ptyprocess``가 없다.
        FileNotFoundError: 실행 파일이 없다.
    """
    if _platform() == "win32":
        raise PtyUnavailableError(
            "unsupported_platform", "Windows에서는 windows_spawner(pywinpty)를 씁니다."
        )
    mod = _import("ptyprocess", "ptyprocess가 필요합니다: pip install ptyprocess")
    proc = mod.PtyProcess.spawn(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        dimensions=(rows, cols),
    )
    return PosixPty(proc)


# ---------------------------------------------------------------- Windows


class WindowsPty:
    """``winpty.PtyProcess``(pywinpty, ConPTY)를 감싼 ``PtyHandle``."""

    def __init__(self, proc: Any) -> None:
        self._proc = proc
        self._closed = threading.Event()

    @property
    def pid(self) -> int | None:
        pid = getattr(self._proc, "pid", None)
        return int(pid) if pid is not None else None

    def read(self, size: int) -> str:
        if self._closed.is_set():
            raise EOFError
        try:
            data = self._proc.read(size)
        except (OSError, ValueError) as exc:
            raise EOFError from exc
        if not data and not self.is_alive():
            raise EOFError
        return str(data)

    def write(self, data: str) -> None:
        self._proc.write(data)

    def is_alive(self) -> bool:
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def exit_code(self) -> int | None:
        if self.is_alive():
            return None
        status = getattr(self._proc, "exitstatus", None)
        return int(status) if status is not None else None

    def terminate(self) -> None:
        with contextlib.suppress(Exception):
            self._proc.terminate(force=False)

    def kill(self) -> None:
        with contextlib.suppress(Exception):
            self._proc.terminate(force=True)

    def resize(self, cols: int, rows: int) -> None:
        self._proc.setwinsize(rows, cols)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        with contextlib.suppress(Exception):
            self._proc.close(force=True)


def windows_spawner(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None,
    cwd: str | None,
    cols: int,
    rows: int,
) -> PtyHandle:
    """Windows ConPTY(``pywinpty``)로 띄운다(``PtySpawner``).

    Raises:
        PtyUnavailableError: Windows가 아니거나 ``pywinpty``가 없다.
    """
    if _platform() != "win32":
        raise PtyUnavailableError("unsupported_platform", "pywinpty는 Windows에서만 씁니다.")
    mod = _import(
        "winpty",
        "pywinpty가 필요합니다: pip install 'agent-console-pty-session[windows]'",
    )
    proc = mod.PtyProcess.spawn(
        list(argv),
        cwd=cwd,
        env=dict(env) if env is not None else None,
        dimensions=(rows, cols),
    )
    return WindowsPty(proc)


def default_spawner() -> PtySpawner:
    """이 플랫폼의 어댑터. 라이브러리 확인까지 한다.

    Raises:
        PtyUnavailableError: 이 플랫폼용 라이브러리가 없다.
    """
    if _platform() == "win32":
        _import(
            "winpty",
            "pywinpty가 필요합니다: pip install 'agent-console-pty-session[windows]'",
        )
        return windows_spawner
    _import("ptyprocess", "ptyprocess가 필요합니다: pip install ptyprocess")
    return posix_spawner


def pty_available() -> bool:
    """이 환경에서 기본 어댑터를 쓸 수 있는가."""
    try:
        default_spawner()
    except PtyUnavailableError:
        return False
    return True


__all__ = [
    "PosixPty",
    "PtyHandle",
    "PtySpawner",
    "PtyUnavailableError",
    "WindowsPty",
    "default_spawner",
    "posix_spawner",
    "pty_available",
    "windows_spawner",
]
