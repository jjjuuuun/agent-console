"""probe가 받은 종료 신호를 자식 프로세스 그룹에 전달한다(agent_bench `terminate` 규칙)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX 신호·프로세스 그룹")


def _start(probe_argv: list[str], out: Path, command: str) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [*probe_argv, "--out", str(out), "--", command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline() == b"ready\n"  # 자식이 신호 처리기를 건 뒤
    return proc


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_term_is_forwarded_to_child_group(tmp_path: Path, probe_argv: list[str]) -> None:
    mark = tmp_path / "mark"
    out = tmp_path / "rec"
    command = (
        f"trap 'echo got > {mark}; exit 7' TERM; sleep 60 & echo $! > {tmp_path / 'gc'}; "
        "echo ready; wait"
    )
    proc = _start(probe_argv, out, command)
    proc.send_signal(signal.SIGTERM)  # probe에만 보낸다
    assert proc.wait(timeout=30) == 7  # 자식이 처리하고 낸 종료 코드 그대로
    assert mark.read_text().strip() == "got"
    grandchild = int((tmp_path / "gc").read_text())
    deadline = time.monotonic() + 10
    while _alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(grandchild)  # 같은 그룹의 손자도 신호를 받았다
    [line] = (out / "no-session.jsonl").read_text().splitlines()
    record = json.loads(line)
    assert record["forwarded_signal"] == signal.SIGTERM
    assert record["exit_code"] == 7


def test_child_killed_by_signal_makes_probe_die_the_same_way(
    tmp_path: Path, probe_argv: list[str]
) -> None:
    out = tmp_path / "rec"
    proc = _start(probe_argv, out, "echo ready; exec sleep 60")
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=30) == -signal.SIGTERM
    record = json.loads((out / "no-session.jsonl").read_text().splitlines()[0])
    assert record["exit_code"] is None
    assert record["signal"] == signal.SIGTERM


def test_stubborn_child_group_is_killed_after_grace(tmp_path: Path, probe_argv: list[str]) -> None:
    out = tmp_path / "rec"
    proc = _start(probe_argv, out, "trap '' TERM; echo ready; while :; do sleep 0.1; done")
    started = time.monotonic()
    proc.send_signal(signal.SIGTERM)
    code = proc.wait(timeout=30)
    assert code == -signal.SIGKILL  # 유예(2초) 뒤 그룹 강제 종료 → 같은 신호로 끝남
    assert time.monotonic() - started < 20
