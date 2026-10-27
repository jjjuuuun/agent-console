"""테스트용 가짜 PTY(실제 프로세스·PTY 없음).

``FakePty``는 ``PtyHandle``이자 한 번만 쓰는 ``PtySpawner``(``fake.spawn``)다. 테스트 쪽에서
``emit``으로 출력을 넣고 ``exit``로 끝내며, ``on_input``으로 입력에 반응하는 대본을 만들 수 있다.
하위 프로세스를 여러 번 띄우는 코드(예: 로그인 뒤 상태 확인 명령)는 ``FakePtySpawner``로 띄울
때마다 새 ``FakePty``를 만든다.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ._adapters import PtyHandle

_EOF = object()


@dataclass(frozen=True)
class FakeSpawn:
    """``spawn`` 호출 기록."""

    argv: tuple[str, ...]
    env: Mapping[str, str] | None
    cwd: str | None
    cols: int
    rows: int


@dataclass
class _State:
    alive: bool = True
    code: int | None = None
    closed: bool = False
    inputs: list[str] = field(default_factory=list)


class FakePty:
    """대본으로 움직이는 가짜 PTY 하나.

    Args:
        output: 띄우자마자 낼 출력.
        exit_code: 주면 ``output``을 낸 뒤 이 코드로 끝난다.
        on_input: 입력이 올 때마다 ``(fake, text)``로 부른다(``emit``·``exit``로 반응).
        ignore_terminate: 참이면 ``terminate``(SIGTERM)를 무시한다(``kill``만 통한다).
        pid: 보고할 프로세스 id.
    """

    def __init__(
        self,
        *,
        output: str = "",
        exit_code: int | None = None,
        on_input: Callable[[FakePty, str], None] | None = None,
        ignore_terminate: bool = False,
        pid: int = 4242,
    ) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._lock = threading.Lock()
        self._state = _State()
        self._on_input = on_input
        self._ignore_terminate = ignore_terminate
        self._pid = pid
        self.spawns: list[FakeSpawn] = []
        self.terminate_calls = 0
        self.kill_calls = 0
        self.size: tuple[int, int] | None = None
        if output:
            self.emit(output)
        if exit_code is not None:
            self.exit(exit_code)

    # ------------------------------------------------------------ 테스트 쪽

    def spawn(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        cwd: str | None,
        cols: int,
        rows: int,
    ) -> PtyHandle:
        """``PtySpawner``: 호출을 기록하고 자신을 돌려준다."""
        self.spawns.append(FakeSpawn(tuple(argv), env, cwd, cols, rows))
        self.size = (cols, rows)
        return self

    def emit(self, text: str) -> None:
        """하위 프로세스 출력을 넣는다(끝난 뒤에는 무시)."""
        with self._lock:
            if not self._state.alive and self._state.code is not None:
                return
        self._queue.put(text)

    def exit(self, code: int = 0) -> None:
        """하위 프로세스를 이 코드로 끝낸다(남은 출력 뒤 EOF)."""
        with self._lock:
            if not self._state.alive:
                return
            self._state.alive = False
            self._state.code = code
        self._queue.put(_EOF)

    @property
    def inputs(self) -> list[str]:
        """받은 입력(순서대로)."""
        with self._lock:
            return list(self._state.inputs)

    @property
    def closed(self) -> bool:
        """``close``가 불렸는가."""
        return self._state.closed

    # ------------------------------------------------------------ PtyHandle

    @property
    def pid(self) -> int | None:
        return self._pid

    def read(self, size: int) -> str:
        item = self._queue.get()
        if item is _EOF:
            self._queue.put(_EOF)  # 다음 읽기도 EOF
            raise EOFError
        assert isinstance(item, str)
        return item  # size는 힌트(가짜는 넣은 조각 그대로)

    def write(self, data: str) -> None:
        with self._lock:
            if self._state.closed or not self._state.alive:
                raise OSError("fake pty closed")
            self._state.inputs.append(data)
        if self._on_input is not None:
            self._on_input(self, data)

    def is_alive(self) -> bool:
        with self._lock:
            return self._state.alive

    def exit_code(self) -> int | None:
        with self._lock:
            return None if self._state.alive else self._state.code

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self._ignore_terminate:
            self.exit(-15)

    def kill(self) -> None:
        self.kill_calls += 1
        self.exit(-9)

    def resize(self, cols: int, rows: int) -> None:
        self.size = (cols, rows)

    def close(self) -> None:
        with self._lock:
            if self._state.closed:
                return
            self._state.closed = True
        self._queue.put(_EOF)


class FakePtySpawner:
    """띄울 때마다 ``make(spawn)``으로 새 ``FakePty``를 만드는 ``PtySpawner``.

    Args:
        make: 호출 기록 → 가짜 PTY. 인자를 보고 대본을 고를 수 있다.
    """

    def __init__(self, make: Callable[[FakeSpawn], FakePty]) -> None:
        self._make = make
        self.spawned: list[tuple[FakeSpawn, FakePty]] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None,
        cwd: str | None,
        cols: int,
        rows: int,
    ) -> PtyHandle:
        call = FakeSpawn(tuple(argv), env, cwd, cols, rows)
        fake = self._make(call)
        self.spawned.append((call, fake))
        return fake.spawn(argv, env=env, cwd=cwd, cols=cols, rows=rows)


__all__ = ["FakePty", "FakePtySpawner", "FakeSpawn"]
