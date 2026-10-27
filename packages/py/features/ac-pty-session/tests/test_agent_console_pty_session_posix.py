"""실제 PTY(POSIX ptyprocess) + 파이썬 스텁 스크립트. 실제 외부 CLI는 부르지 않는다."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from agent_console_pty_session import (
    ExpectRules,
    ExpectWatcher,
    PtySession,
    PtyUnavailableError,
    default_spawner,
    posix_spawner,
    pty_available,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not pty_available(), reason="POSIX PTY(ptyprocess)가 없다"
)

STUB = str(Path(__file__).parent / "stub_cli.py")


def argv(*args: str) -> list[str]:
    return [sys.executable, STUB, *args]


def gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    # 좀비(거두지 않은 자식)도 끝난 것으로 본다
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
            return fh.read().split(")")[-1].split()[0] == "Z"
    except OSError:
        return True


async def wait_text(session: PtySession, needle: str, timeout: float = 10.0) -> str:
    import asyncio

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    version = session.version
    while needle not in session.text_since(0).text:
        if loop.time() > deadline:
            raise AssertionError(f"{needle!r} 기다림 시간 초과: {session.text_since(0).text!r}")
        version = await session.wait_changed(version, 0.2)
    return session.text_since(0).text


async def test_echo_input_and_exit_code() -> None:
    async with await PtySession.spawn(argv("echo", "7"), spawner=default_spawner()) as s:
        await wait_text(s, "ready> ")
        s.write("hello")
        s.send_key("enter")
        assert await s.wait_exit(10.0) == 7
        text = s.text_since(0).text
        assert "hello" in text  # PTY 에코
        assert "got:hello" in text


async def test_long_line_not_wrapped_with_wide_terminal() -> None:
    async with await PtySession.spawn(argv("long"), cols=400, rows=40) as s:
        assert await s.wait_exit(10.0) == 0
        lines = s.screen_lines()
        assert "size=400x40" in lines
        assert "x" * 300 + "END" in lines


async def test_ansi_osc8_and_code_prompt() -> None:
    rules = ExpectRules(
        {"open_url": r"https://\S+/oauth/authorize\S*", "needs_code": r"(?i)paste code"}
    )
    watcher = ExpectWatcher(rules)
    async with await PtySession.spawn(argv("ansi"), cols=200) as s:
        await wait_text(s, "Paste code here")
        found = watcher.feed(s.text_since(0).text)
        names = {m.name: m.text for m in found}
        assert names["open_url"] == "https://example.com/oauth/authorize?x=1"
        assert "needs_code" in names
        assert s.links() == ["https://example.com/oauth/authorize?x=1"]
        s.write("SECRET-CODE")
        s.send_key("enter")
        assert await s.wait_exit(10.0) == 0
        assert s.screen_lines()[-1] == "code-len=11"
        assert s.screen_lines()[0] == "loading 99%"


async def test_env_and_cwd(tmp_path: Path) -> None:
    env = {"PATH": os.environ.get("PATH", ""), "STUB_VAR": "v1"}
    async with await PtySession.spawn(argv("env"), env=env, cwd=str(tmp_path)) as s:
        assert await s.wait_exit(10.0) == 0
        assert f"VAR=v1 CWD={tmp_path}" in s.screen_lines()


async def test_nonzero_exit() -> None:
    async with await PtySession.spawn(argv("exit", "1")) as s:
        assert await s.wait_exit(10.0) == 1


async def test_sigterm_ignored_is_force_killed() -> None:
    s = await PtySession.spawn(argv("ignore_term"))
    await wait_text(s, "ignoring")
    pid = s.pid
    assert pid is not None
    code = await s.terminate(grace=0.3)
    assert code == -9
    assert gone(pid)


async def test_terminate_kills_process_group() -> None:
    s = await PtySession.spawn(argv("grandchild"))
    text = await wait_text(s, "\n", timeout=10.0)
    child = int(text.split("child=")[1].split()[0])
    pid = s.pid
    assert pid is not None
    await s.terminate(grace=1.0)
    assert gone(pid)
    import asyncio

    for _ in range(50):
        if gone(child):
            break
        await asyncio.sleep(0.05)
    assert gone(child)


async def test_missing_executable() -> None:
    with pytest.raises(FileNotFoundError):
        await PtySession.spawn(["/nonexistent/agent-console-no-such-cli"])


def test_windows_spawner_unavailable_here() -> None:
    from agent_console_pty_session import windows_spawner

    with pytest.raises(PtyUnavailableError) as info:
        windows_spawner(["x"], env=None, cwd=None, cols=80, rows=24)
    assert info.value.reason == "unsupported_platform"
    assert posix_spawner is not None
