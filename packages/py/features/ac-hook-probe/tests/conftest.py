"""probe 테스트 도우미: 프로세스 안에서 `main`을 파이프·파일 기술자로 돌린다."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_console_hook_probe import ProbeIO, main

PROBE = [sys.executable, "-m", "agent_console_hook_probe"]


@dataclass
class Result:
    stdout: bytes
    stderr: bytes
    code: int


def _feed(fd: int, data: bytes) -> None:
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
    except BrokenPipeError:
        pass  # 자식이 stdin을 다 읽지 않고 끝났다
    finally:
        os.close(fd)


@pytest.fixture
def probe(tmp_path: Path) -> Callable[[Sequence[str], bytes], Result]:
    """`main(args)`를 이 프로세스에서 돌리고 (stdout, stderr, 종료 코드)를 돌려준다."""
    counter = iter(range(1_000_000))

    def run(args: Sequence[str], stdin: bytes = b"") -> Result:
        n = next(counter)
        r, w = os.pipe()
        feeder = threading.Thread(target=_feed, args=(w, stdin))
        feeder.start()
        out_path, err_path = tmp_path / f"o{n}", tmp_path / f"e{n}"
        try:
            with out_path.open("w+b") as out, err_path.open("w+b") as err:
                code = main(
                    list(args),
                    io=ProbeIO(r, out.fileno(), err.fileno()),
                    handle_signals=False,
                    reraise_signal=lambda _s: None,
                )
        finally:
            feeder.join()
            os.close(r)
        return Result(out_path.read_bytes(), err_path.read_bytes(), code)

    return run


@pytest.fixture
def direct() -> Callable[[str, bytes], Result]:
    """같은 명령을 probe 없이 `/bin/sh -c`로 돌린 결과(비교 기준)."""

    def run(command: str, stdin: bytes = b"") -> Result:
        done = subprocess.run(
            ["/bin/sh", "-c", command], input=stdin, capture_output=True, check=False
        )
        return Result(done.stdout, done.stderr, done.returncode)

    return run


@pytest.fixture
def probe_argv() -> list[str]:
    """probe를 별도 프로세스로 띄우는 인자."""
    return list(PROBE)
