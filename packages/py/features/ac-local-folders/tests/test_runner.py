"""`SubprocessRunner`: 실제 자식 프로세스(파이썬 한 줄)로 실행·시간 상한·중단을 확인한다.

창을 띄우는 명령은 실행하지 않는다.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from agent_console_local_folders import SubprocessRunner

PY = sys.executable


def test_runs_without_shell_and_captures_output() -> None:
    runner = SubprocessRunner(base_env={"PATH": ""})
    code = "import os,sys; print(sys.argv[1]); print(os.environ.get('X_VAL'))"
    out = runner([PY, "-c", code, "a; echo injected"], env={"X_VAL": "v"}, timeout=30)
    assert out.exit_code == 0
    assert out.stdout.decode().splitlines() == ["a; echo injected", "v"]
    assert not out.timed_out
    assert not out.cancelled


def test_exit_code_and_stderr() -> None:
    out = SubprocessRunner()(
        [PY, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"], env={}, timeout=30
    )
    assert out.exit_code == 3
    assert out.stderr == b"bad"


def test_timeout_kills_process() -> None:
    start = time.monotonic()
    out = SubprocessRunner(poll_interval=0.05)(
        [PY, "-c", "import time; time.sleep(30)"], env={}, timeout=0.5
    )
    assert out.timed_out
    assert not out.cancelled
    assert time.monotonic() - start < 15


def test_cancel_signal_kills_process() -> None:
    event = threading.Event()
    timer = threading.Timer(0.3, event.set)
    timer.start()
    try:
        out = SubprocessRunner(poll_interval=0.05)(
            [PY, "-c", "import time; time.sleep(30)"], env={}, timeout=30, cancel=event
        )
    finally:
        timer.cancel()
    assert out.cancelled
    assert not out.timed_out


def test_missing_executable_raises() -> None:
    with pytest.raises(FileNotFoundError):
        SubprocessRunner()(["agent-console-no-such-picker-xyz"], env={}, timeout=5)
    with pytest.raises(ValueError, match="argv"):
        SubprocessRunner()([], env={}, timeout=5)
