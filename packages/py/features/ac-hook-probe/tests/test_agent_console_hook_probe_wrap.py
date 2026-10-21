"""감싸기 인자(`wrap_command`)와 실제 실행 왕복."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from agent_console_hook_probe import default_probe_command, wrap_command, wrap_command_line


def test_shell_form_keeps_command_as_one_argument() -> None:
    argv = wrap_command("echo 'a b' | cat", out="/o", probe=["probe"], matcher="Bash")
    assert argv == ["probe", "--out", "/o", "--matcher", "Bash", "--", "echo 'a b' | cat"]


def test_exec_form_and_options() -> None:
    argv = wrap_command(
        ["node", "x.js"],
        out=Path("/o"),
        probe=["p"],
        shell="bash",
        context={"run_id": "R", "node": "a/b"},
        capture_bytes=10,
    )
    assert argv == [
        "p",
        "--out",
        "/o",
        "--shell",
        "bash",
        "--capture-bytes",
        "10",
        "--context",
        "run_id=R",
        "--context",
        "node=a/b",
        "--exec",
        "--",
        "node",
        "x.js",
    ]
    with pytest.raises(ValueError, match="명령"):
        wrap_command([], out="/o")
    with pytest.raises(ValueError, match="맥락"):
        wrap_command("x", out="/o", context={"a=b": "c"})


def test_default_probe_command_uses_current_python() -> None:
    assert default_probe_command() == [sys.executable, "-m", "agent_console_hook_probe"]


def test_command_line_is_quoted_for_settings_files() -> None:
    line = wrap_command_line("echo 'x'", out="/o d", probe=["probe"])
    assert shlex.split(line) == ["probe", "--out", "/o d", "--", "echo 'x'"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX 셸")
def test_wrapped_command_runs_like_original(tmp_path: Path) -> None:
    original = "cat; echo done >&2; exit 2"
    payload = json.dumps({"session_id": "S", "hook_event_name": "Stop"}).encode()
    direct = subprocess.run(
        ["/bin/sh", "-c", original], input=payload, capture_output=True, check=False
    )
    wrapped = subprocess.run(
        wrap_command(original, out=tmp_path / "rec", context={"run_id": "R"}),
        input=payload,
        capture_output=True,
        check=False,
    )
    assert (wrapped.stdout, wrapped.stderr, wrapped.returncode) == (
        direct.stdout,
        direct.stderr,
        direct.returncode,
    )
    record = json.loads((tmp_path / "rec" / "S.jsonl").read_text().splitlines()[0])
    assert record["decision"]["value"] == "block"
    assert record["context"] == {"run_id": "R"}
