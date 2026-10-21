"""POSIX·Windows 셸 인자 규칙(Claude Code가 hook을 실행하는 방식과 같게)."""

from __future__ import annotations

import subprocess

import pytest

from agent_console_hook_probe import (
    DEFAULT_SHELLS,
    ShellRule,
    default_shell_name,
    exec_invocation,
    shell_invocation,
)

CMD = 'echo "a b" && jq -r .x <<<"$IN" | grep \'q\''


def _no_bash(_name: str) -> str | None:
    return None


def _has_bash(name: str) -> str | None:
    return "C:\\Git\\bin\\bash.exe" if name == "bash" else None


def test_posix_default_is_sh_dash_c_with_command_untouched() -> None:
    assert default_shell_name(os_name="posix") == "sh"
    assert shell_invocation(CMD, os_name="posix") == ["/bin/sh", "-c", CMD]


def test_windows_default_prefers_git_bash_then_powershell() -> None:
    assert default_shell_name(os_name="nt", which=_has_bash) == "bash"
    assert default_shell_name(os_name="nt", which=_no_bash) == "powershell"
    assert shell_invocation(CMD, os_name="nt", which=_has_bash) == ["bash", "-c", CMD]
    assert shell_invocation(CMD, os_name="nt", which=_no_bash) == [
        "powershell",
        "-NoProfile",
        "-Command",
        CMD,
    ]


def test_windows_cmd_builds_raw_command_line_without_escaping_quotes() -> None:
    line = shell_invocation('echo "x y" & exit /b 2', "cmd", os_name="nt")
    assert line == 'cmd /d /s /c "echo "x y" & exit /b 2"'
    # POSIX에서는 cmd도 인자 목록(raw 규칙은 Windows 전용)
    assert shell_invocation("x", "cmd", os_name="posix") == ["cmd", "/d", "/s", "/c", "x"]


def test_windows_list_quoting_round_trips_through_msvcrt_rules() -> None:
    argv = shell_invocation(CMD, "bash", os_name="nt")
    assert isinstance(argv, list)
    # Windows가 인자 목록을 명령 줄로 합치는 규칙(list2cmdline) — 셸이 받는 마지막 인자는 원문
    line = subprocess.list2cmdline(argv)
    assert line.startswith("bash -c ")
    assert '\\"a b\\"' in line


def test_unknown_shell_is_executable_path_with_dash_c() -> None:
    assert shell_invocation("ls", "/usr/local/bin/zsh", os_name="posix") == [
        "/usr/local/bin/zsh",
        "-c",
        "ls",
    ]


def test_shell_rules_are_data() -> None:
    custom = {**DEFAULT_SHELLS, "fish": ShellRule(("fish", "--no-config", "-c"))}
    assert shell_invocation("ls", "fish", shells=custom, os_name="posix") == [
        "fish",
        "--no-config",
        "-c",
        "ls",
    ]
    assert "fish" not in DEFAULT_SHELLS
    with pytest.raises(TypeError):
        DEFAULT_SHELLS["x"] = ShellRule(("x",))  # type: ignore[index]


def test_exec_invocation_keeps_argv() -> None:
    assert exec_invocation(["node", "a b.js", "--fix"]) == ["node", "a b.js", "--fix"]
    with pytest.raises(ValueError, match="명령"):
        exec_invocation([])
