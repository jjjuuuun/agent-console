"""Windows ConPTY(pywinpty) 어댑터 — pywinpty가 있을 때만."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent_console_pty_session import PtySession, PtyUnavailableError, posix_spawner

STUB = str(Path(__file__).parent / "stub_cli.py")


def _has_winpty() -> bool:
    try:
        import winpty  # type: ignore[import-not-found,unused-ignore]  # noqa: F401
    except ImportError:
        return False
    return sys.platform == "win32"


@pytest.mark.skipif(not _has_winpty(), reason="pywinpty 없음(Windows 선택 추가 기능)")
async def test_windows_echo_and_exit_code() -> None:
    async with await PtySession.spawn([sys.executable, STUB, "exit", "4"]) as s:
        assert await s.wait_exit(20.0) == 4
        assert "bye" in s.text_since(0).text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 전용 확인")
def test_posix_spawner_refuses_on_windows() -> None:
    with pytest.raises(PtyUnavailableError):
        posix_spawner(["x"], env=None, cwd=None, cols=80, rows=24)
