"""probe가 받은 종료 신호를 자식 프로세스 그룹에 전달한다(agent_bench `terminate` 규칙)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_console_hook_probe import ProbeIO, run_probe

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


_DEFERRED_SIGNAL_SCRIPT = """
import json, os, signal, subprocess, sys, threading, time
from agent_console_hook_probe import ProbeIO, run_probe

spawned = threading.Event()

def foreign():  # 처리기 설치 전에 만든 스레드라 종료 신호를 막지 않는다
    spawned.wait()
    time.sleep(0.3)
    signal.pthread_kill(threading.get_ident(), signal.SIGTERM)  # C 처리기는 이 스레드에서 돈다

threading.Thread(target=foreign, daemon=True).start()

def popen(*args, **kwargs):
    proc = subprocess.Popen(*args, **kwargs)
    spawned.set()
    return proc

null = os.open(os.devnull, os.O_RDONLY)
started = time.monotonic()
outcome = run_probe(["/bin/sh", "-c", "exec sleep 30"], io=ProbeIO(null, 1, 2), popen=popen)
print(json.dumps({"signal": outcome.signal, "forwarded": outcome.forwarded_signal,
                  "seconds": time.monotonic() - started}))
"""


@pytest.mark.skipif(not hasattr(signal, "pthread_kill"), reason="스레드 지정 신호")
def test_signal_noted_while_main_is_blocked_is_still_forwarded_promptly(tmp_path: Path) -> None:
    """C 처리기가 메인 스레드를 깨우지 못한 신호도 곧바로 전달된다(공개 CI 30초 시간 초과 회귀).

    Python 신호 처리기는 메인 스레드에서만 돈다. 메인 스레드가 `waitpid`에 막 들어가려는 순간(또는
    다른 스레드에) 신호가 오면 `EINTR`이 나지 않아, 예전 구현은 자식이 끝날 때까지 전달도 유예 강제
    종료도 하지 않았다(`echo ready; exec sleep 60`이 60초를 다 잤다). 여기서는 신호를 막지 않은 다른
    스레드로 보내 같은 상태를 결정적으로 만든다.
    """
    done = subprocess.run(
        [sys.executable, "-c", _DEFERRED_SIGNAL_SCRIPT],
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    result = json.loads(done.stdout.decode().strip().splitlines()[-1])
    assert result["forwarded"] == signal.SIGTERM
    assert result["signal"] == signal.SIGTERM  # 자식이 전달받은 신호로 끝났다(30초 sleep 전에)
    assert result["seconds"] < 10


@pytest.mark.skipif(not Path("/proc/self/task").is_dir(), reason="/proc 스레드 상태(Linux)")
def test_helper_threads_block_forwarded_signals(tmp_path: Path) -> None:
    """중계 스레드는 종료 신호를 막는다 → 신호가 늘 메인 스레드로 가서 처리기가 바로 돈다.

    보조 스레드가 신호를 받으면 메인 스레드는 다음 주기 깨어남까지 처리기를 돌리지 않는다(무기한
    대기는 하지 않으므로 늦어도 그 간격 안에는 처리된다). 막아 두면 그 지연도 없다.
    """
    me = os.getpid()
    command = f"sleep 0.3; for f in /proc/{me}/task/*/status; do echo $f; grep SigBlk $f; done"
    out, err, stdin = tmp_path / "out", tmp_path / "err", tmp_path / "in"
    stdin.write_bytes(b"")
    with stdin.open("rb") as i, out.open("w+b") as o, err.open("w+b") as e:
        outcome = run_probe(
            ["/bin/sh", "-c", command], io=ProbeIO(i.fileno(), o.fileno(), e.fileno())
        )
    assert outcome.exit_code == 0
    lines = out.read_text().splitlines()
    blocked: dict[int, bool] = {}
    for path, mask in zip(lines[::2], lines[1::2], strict=True):
        tid = int(path.split("/")[-2])
        blocked[tid] = bool(int(mask.split()[1], 16) >> (signal.SIGTERM - 1) & 1)
    assert blocked[me] is False  # 메인 스레드는 받는다
    assert sum(blocked.values()) >= 2  # stdout·stderr 중계 스레드는 막는다
    assert not signal.pthread_sigmask(signal.SIG_BLOCK, []) & {signal.SIGTERM}  # 마스크 복원
