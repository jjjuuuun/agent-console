"""``PtySession``: PTY 하위 프로세스 하나를 asyncio에서 다룬다.

읽기 스레드 하나가 어댑터의 ``read``를 돌며 출력을 ``TerminalText``에 넣는다(이벤트 루프
스레드에서). 출력·종료가 생길 때마다 ``version``이 오르고 ``wait_changed``가 깬다. 원시 출력은
메모리에만 있고 (한도 안에서) 세션이 끝나면 버린다. 이 모듈은 아무것도 로그에 남기지 않는다(출력에
비밀이 섞일 수 있다).
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType, TracebackType
from typing import Self

from ._adapters import PtyHandle, PtySpawner, default_spawner
from ._terminal import (
    DEFAULT_MAX_LINE_CHARS,
    DEFAULT_MAX_TEXT_CHARS,
    DEFAULT_SCROLLBACK_LINES,
    TerminalText,
    TextChunk,
)

KEYS: Mapping[str, str] = MappingProxyType(
    {
        "enter": "\r",
        "escape": "\x1b",
        "tab": "\t",
        "backspace": "\x7f",
        "up": "\x1b[A",
        "down": "\x1b[B",
        "right": "\x1b[C",
        "left": "\x1b[D",
        "ctrl-c": "\x03",
        "ctrl-d": "\x04",
    }
)
"""``send_key``가 아는 키 이름 → 보낼 글자(데이터, 호출자가 다른 표를 넘길 수 있다)."""

DEFAULT_TERMINATE_GRACE_S = 2.0
"""``terminate``가 정중한 종료 뒤 강제 종료까지 기다리는 기본 초."""

_EXIT_POLL_S = 0.02
_DRAIN_S = 0.5


class PtyClosedError(RuntimeError):
    """닫힌(또는 끝난) 세션에 입력을 보내려 했다."""


class PtySession:
    """PTY에 붙은 하위 프로세스 하나.

    ``spawn``으로 만든다. ``async with``로 쓰면 나갈 때 ``terminate``한다.

    Example:
        >>> import asyncio
        >>> from agent_console_pty_session import FakePty
        >>> async def demo() -> list[str]:
        ...     fake = FakePty(output="hello\\r\\n", exit_code=0)
        ...     async with await PtySession.spawn(["demo"], spawner=fake.spawn) as s:
        ...         await s.wait_exit(1.0)
        ...         return s.screen_lines()
        >>> asyncio.run(demo())
        ['hello']
    """

    def __init__(
        self,
        handle: PtyHandle,
        *,
        argv: Sequence[str],
        loop: asyncio.AbstractEventLoop,
        terminal: TerminalText,
        read_size: int,
        keys: Mapping[str, str],
    ) -> None:
        """직접 만들지 않는다. ``PtySession.spawn``을 쓴다."""
        self._handle = handle
        self._argv = tuple(argv)
        self._loop = loop
        self._term = terminal
        self._keys = keys
        self._version = 0
        self._changed = asyncio.Event()
        self._eof = False
        self._closed = False
        self._exit_watch: asyncio.Task[None] | None = None
        self._reader = threading.Thread(
            target=self._read_loop, args=(read_size,), name="pty-session-reader", daemon=True
        )
        self._reader.start()

    @classmethod
    async def spawn(
        cls,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        cols: int = 80,
        rows: int = 24,
        spawner: PtySpawner | None = None,
        scrollback_lines: int = DEFAULT_SCROLLBACK_LINES,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
        max_line_chars: int = DEFAULT_MAX_LINE_CHARS,
        read_size: int = 4096,
        keys: Mapping[str, str] = KEYS,
    ) -> PtySession:
        """하위 프로세스를 PTY에 붙여 띄운다.

        Args:
            argv: 실행 인자(셸을 거치지 않는다).
            env: 하위 프로세스 환경 전체(None = 부모 환경 그대로). 비밀 변수를 빼려면 호출자가
                걸러 넘긴다.
            cwd: 작업 폴더(None = 지금 폴더).
            cols: 열 수. 긴 줄(URL 등)이 하위 프로세스 쪽에서 줄바꿈되지 않게 넓게 줄 수 있다.
            rows: 줄 수.
            spawner: 어댑터(None = ``default_spawner()``). 테스트는 ``FakePty().spawn``.
            scrollback_lines: 화면이 기억하는 최대 줄 수.
            max_text_chars: 원문 흐름이 기억하는 최대 글자 수.
            max_line_chars: 화면 한 줄 최대 글자 수.
            read_size: 한 번에 읽을 최대 글자 수.
            keys: ``send_key`` 이름 표.

        Raises:
            ValueError: ``argv``가 비었거나 크기가 1보다 작다.
            PtyUnavailableError: PTY를 쓸 수 없다.
            FileNotFoundError: 실행 파일이 없다.
            OSError: 그 밖의 시작 실패.
        """
        if not argv:
            raise ValueError("argv가 비었습니다")
        if cols < 1 or rows < 1:
            raise ValueError("cols·rows는 1 이상이어야 합니다")
        spawn = spawner if spawner is not None else default_spawner()
        handle = spawn(list(argv), env=env, cwd=cwd, cols=cols, rows=rows)
        terminal = TerminalText(
            scrollback_lines=scrollback_lines,
            max_text_chars=max_text_chars,
            max_line_chars=max_line_chars,
        )
        return cls(
            handle,
            argv=argv,
            loop=asyncio.get_running_loop(),
            terminal=terminal,
            read_size=read_size,
            keys=keys,
        )

    # ------------------------------------------------------------ 읽기 스레드

    def _read_loop(self, size: int) -> None:
        try:
            while True:
                data = self._handle.read(size)
                if data:
                    self._post(self._on_data, data)
        except (EOFError, OSError):
            pass
        except Exception:  # 어댑터 오류도 출력 끝으로 본다
            pass
        finally:
            self._post(self._on_eof)

    def _post(self, fn: Callable[..., None], *args: str) -> None:
        with contextlib.suppress(RuntimeError):  # 루프가 이미 닫혔다
            self._loop.call_soon_threadsafe(fn, *args)

    def _bump(self) -> None:
        self._version += 1
        self._changed.set()
        self._changed = asyncio.Event()

    def _on_data(self, data: str) -> None:
        self._term.feed(data)
        self._bump()

    def _on_eof(self) -> None:
        if self._eof:
            return
        self._eof = True
        self._bump()
        if self._exit_watch is None:
            self._exit_watch = asyncio.ensure_future(self._watch_exit())

    async def _watch_exit(self) -> None:
        # 출력이 끝나도 프로세스는 조금 더 살아 있을 수 있다. 끝나면 한 번 더 알린다.
        while self._handle.is_alive():
            await asyncio.sleep(_EXIT_POLL_S * 5)
        self._bump()

    # ------------------------------------------------------------ 상태

    @property
    def argv(self) -> tuple[str, ...]:
        """실행 인자."""
        return self._argv

    @property
    def pid(self) -> int | None:
        """하위 프로세스 id."""
        return self._handle.pid

    @property
    def version(self) -> int:
        """출력·종료가 생길 때마다 오르는 번호."""
        return self._version

    @property
    def output_ended(self) -> bool:
        """출력이 끝났다(PTY가 닫혔다)."""
        return self._eof

    def is_alive(self) -> bool:
        """하위 프로세스가 실행 중인가."""
        return self._handle.is_alive()

    @property
    def exit_code(self) -> int | None:
        """종료 코드(실행 중이면 None, 신호로 끝났으면 음수)."""
        return self._handle.exit_code()

    def screen_lines(self, last: int | None = None) -> list[str]:
        """화면 줄(``TerminalText.screen_lines``)."""
        return self._term.screen_lines(last)

    @property
    def text_offset(self) -> int:
        """원문 흐름의 지금 끝 위치."""
        return self._term.text_offset

    def text_since(self, offset: int = 0) -> TextChunk:
        """``offset`` 뒤의 원문 흐름(제어 시퀀스 제거, OSC 8 링크 대상 포함)."""
        return self._term.text_since(offset)

    def links(self) -> list[str]:
        """지금까지 본 OSC 8 링크 대상."""
        return self._term.links()

    # ------------------------------------------------------------ 대기

    async def wait_changed(self, since: int, timeout: float | None = None) -> int:
        """``version``이 ``since``보다 커질 때까지(또는 시간이 다 될 때까지) 기다린다.

        Returns:
            지금 ``version``(시간이 다 됐으면 그대로일 수 있다).
        """
        if self._version > since:
            return self._version
        event = self._changed
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout)
        return self._version

    async def wait_exit(self, timeout: float | None = None) -> int | None:
        """하위 프로세스가 끝날 때까지 기다린다. 끝난 뒤 남은 출력도 잠깐(최대 0.5초) 더 받는다.

        Returns:
            종료 코드. 시간 안에 끝나지 않으면 None.
        """
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while self._handle.is_alive():
            if deadline is not None and loop.time() >= deadline:
                return None
            await asyncio.sleep(_EXIT_POLL_S)
        drain_until = loop.time() + _DRAIN_S
        while not self._eof and not self._closed and loop.time() < drain_until:
            await asyncio.sleep(_EXIT_POLL_S)
        return self._handle.exit_code()

    # ------------------------------------------------------------ 입력

    def write(self, text: str) -> None:
        """글자를 그대로 보낸다(줄 끝 변환 없음, Enter는 ``send_key("enter")``).

        Raises:
            PtyClosedError: 세션이 닫혔거나 출력이 끝났다.
        """
        if self._closed or self._eof:
            raise PtyClosedError("세션이 끝났습니다")
        try:
            self._handle.write(text)
        except OSError as exc:
            raise PtyClosedError("세션이 끝났습니다") from exc

    def send_key(self, name: str) -> None:
        """이름 붙은 키 하나를 보낸다(``KEYS``).

        Raises:
            KeyError: 모르는 키 이름.
            PtyClosedError: 세션이 끝났다.
        """
        self.write(self._keys[name])

    def resize(self, cols: int, rows: int) -> None:
        """터미널 크기를 바꾼다."""
        if not self._closed:
            self._handle.resize(cols, rows)

    # ------------------------------------------------------------ 종료

    async def terminate(self, grace: float = DEFAULT_TERMINATE_GRACE_S) -> int | None:
        """정중히 끝내고(POSIX SIGTERM), ``grace``초 안에 안 끝나면 강제로 끝낸다(SIGKILL).

        여러 번 불러도 된다. PTY를 닫고 읽기 스레드를 멈춘다.

        Returns:
            종료 코드(강제 종료 뒤에도 거두지 못했으면 None).
        """
        code: int | None
        if self._handle.is_alive():
            self._handle.terminate()
            code = await self.wait_exit(max(0.0, grace))
            if code is None and self._handle.is_alive():
                self._handle.kill()
                code = await self.wait_exit(max(1.0, grace))
        else:
            code = self._handle.exit_code()
        await self._close_handle()
        return code

    async def _close_handle(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._handle.close()
        await asyncio.to_thread(self._reader.join, 2.0)
        if self._exit_watch is not None and not self._exit_watch.done():
            self._exit_watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._exit_watch

    async def aclose(self) -> None:
        """``terminate()``와 같다."""
        await self.terminate()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.terminate()


__all__ = [
    "DEFAULT_TERMINATE_GRACE_S",
    "KEYS",
    "PtyClosedError",
    "PtySession",
]
