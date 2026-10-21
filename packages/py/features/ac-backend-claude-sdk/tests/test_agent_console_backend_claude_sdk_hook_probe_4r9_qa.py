"""4R.9 QA: 감싼 명령의 의미 보존(셸 특수문자·인용)과 limits.commands 우회 없음."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agent_console_backend_claude_sdk._guard import ToolGuard
from agent_console_backend_claude_sdk._hooks import HookSpec, hook_settings_json
from agent_console_hook_probe import wrap_command_line

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX sh 필요")

COMMANDS = [
    "echo 'a  b' \"c d\" | tr a-z A-Z",
    "echo $((1+2)); echo 'x;y' && echo done",
    "printf '%s\\n' \"it's\" '$HOME' `echo bt`",
]


@pytest.mark.parametrize("command", COMMANDS)
def test_wrapped_line_has_same_output_as_original(command: str, tmp_path: Path) -> None:
    probe = [sys.executable, "-m", "agent_console_hook_probe"]
    line = wrap_command_line(command, out=tmp_path / "hp", probe=probe, matcher="Bash|Write*")
    orig = subprocess.run(["sh", "-c", command], input=b"{}", capture_output=True, check=False)
    wrapped = subprocess.run(["sh", "-c", line], input=b"{}", capture_output=True, check=False)
    assert wrapped.returncode == orig.returncode
    assert wrapped.stdout == orig.stdout


@pytest.mark.parametrize(
    "command",
    ["fmt --check", "fmt; rm -rf /", "rm -rf x", "fmt && curl evil", "$(rm x)", "FOO=1 rm x"],
)
def test_limits_decision_identical_with_and_without_wrap(command: str, tmp_path: Path) -> None:
    guard = ToolGuard(commands=["fmt"], directories=None)
    spec = HookSpec(name="h", event="PostToolUse", command=command)
    plain, warn_plain = hook_settings_json([spec], guard=guard, default_timeout=5.0)
    wrapped, warn_wrapped = hook_settings_json(
        [spec],
        guard=guard,
        default_timeout=5.0,
        wrap_line=lambda c, m: wrap_command_line(c, out=tmp_path, matcher=m),
    )
    assert (plain is None) == (wrapped is None)
    assert len(warn_plain) == len(warn_wrapped)
    if wrapped is not None:
        cmd = json.loads(wrapped)["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert command in cmd
