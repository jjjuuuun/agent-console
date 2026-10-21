"""4R.7 QA: 실제 프로세스로 본 투명성·비밀 가림·셸 주입·고아 프로세스."""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_console_hook_probe import wrap_command_line

PROBE = [sys.executable, "-m", "agent_console_hook_probe"]
SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ab"
HOOK_IN = json.dumps({"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash"})


def _run(args: list[str], stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, input=stdin, capture_output=True, check=False)


def test_real_process_blocking_exit_2_and_json_are_identical(tmp_path: Path) -> None:
    cmd = 'cat >/dev/null; printf \'{"decision":"block"}\'; echo err >&2; exit 2'
    direct = _run(["/bin/sh", "-c", cmd], HOOK_IN.encode())
    wrapped = _run([*PROBE, "--out", str(tmp_path), "--", cmd], HOOK_IN.encode())
    assert (wrapped.stdout, wrapped.stderr, wrapped.returncode) == (
        direct.stdout,
        direct.stderr,
        direct.returncode,
    )
    assert wrapped.returncode == 2


def test_probe_without_command_or_out_never_uses_blocking_code(tmp_path: Path) -> None:
    assert _run(PROBE).returncode == 1
    assert _run([*PROBE, "--out", str(tmp_path)]).returncode == 1
    assert (
        _run([*PROBE, "--out", str(tmp_path), "--exec", "--", "/nonexistent/x"]).returncode == 127
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX 신호")
def test_term_leaves_no_orphan_grandchild(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    cmd = f"sleep 300 & echo $! > {pid_file}; wait"
    proc = subprocess.Popen([*PROBE, "--out", str(tmp_path / "o"), "--", cmd])
    for _ in range(150):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        time.sleep(0.2)
    child = int(pid_file.read_text())
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=30)
        time.sleep(0.3)
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    finally:
        if proc.poll() is None:
            proc.kill()
        with contextlib.suppress(ProcessLookupError):
            os.kill(child, signal.SIGKILL)


def test_wrap_command_line_is_injection_safe(tmp_path: Path) -> None:
    mark = tmp_path / "PWNED"
    line = wrap_command_line(
        "echo ok",
        out=f"{tmp_path}/o; touch {mark}",
        matcher=f"x'; touch {mark}; '",
        context={"a": f"$(touch {mark})"},
    )
    done = subprocess.run(["/bin/sh", "-c", line], capture_output=True, check=False)
    assert done.stdout == b"ok\n"
    assert not mark.exists()


def test_secrets_in_cwd_matcher_context_are_masked(tmp_path: Path) -> None:
    stdin = json.dumps({"session_id": "s9", "cwd": f"/x?token={SECRET}"}).encode()
    _run(
        [
            *PROBE,
            "--out",
            str(tmp_path),
            "--matcher",
            f"B({SECRET})",
            "--context",
            f"k={SECRET}",
            "--",
            "true",
        ],
        stdin,
    )
    assert SECRET not in (tmp_path / "s9.jsonl").read_text()
