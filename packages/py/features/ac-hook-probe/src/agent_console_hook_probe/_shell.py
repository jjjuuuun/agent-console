"""원래 hook 명령을 Claude Code와 같은 셸 인자 규칙으로 실행할 인자 목록(표준 라이브러리만).

Claude Code는 셸 형식 hook(`args` 없음)을 macOS·Linux에서 `sh -c`, Windows에서 Git Bash(없으면
PowerShell)로 돌린다. 셸 이름 → 인자 규칙은 데이터(`DEFAULT_SHELLS`)이고 호출자가 바꿀 수 있다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

__all__ = [
    "DEFAULT_SHELLS",
    "ShellRule",
    "default_shell_name",
    "exec_invocation",
    "shell_invocation",
]


@dataclass(frozen=True, slots=True)
class ShellRule:
    """셸 하나의 실행 규칙.

    Attributes:
        prefix: 명령 문자열 앞에 오는 인자(실행 파일 포함). 예: `("/bin/sh", "-c")`.
        raw_command_line: Windows에서 인자 목록 대신 명령 줄 문자열을 그대로 만든다(`cmd /c`처럼
            자체 따옴표 규칙을 쓰는 셸). POSIX에서는 무시한다.
    """

    prefix: tuple[str, ...]
    raw_command_line: bool = False


DEFAULT_SHELLS: Mapping[str, ShellRule] = MappingProxyType(
    {
        "sh": ShellRule(("/bin/sh", "-c")),
        "bash": ShellRule(("bash", "-c")),
        "powershell": ShellRule(("powershell", "-NoProfile", "-Command")),
        "pwsh": ShellRule(("pwsh", "-NoProfile", "-Command")),
        "cmd": ShellRule(("cmd", "/d", "/s", "/c"), raw_command_line=True),
    }
)
"""기본 셸 규칙(이름 → 규칙). 표에 없는 이름은 실행 파일 경로로 보고 `<경로> -c <명령>`으로 돈다."""


def default_shell_name(
    *, os_name: str = os.name, which: Callable[[str], str | None] = shutil.which
) -> str:
    """`--shell`을 주지 않았을 때의 셸 이름(Claude Code 규칙).

    POSIX는 `sh`. Windows는 `bash`(Git Bash)가 PATH에 있으면 `bash`, 없으면 `powershell`.
    """
    if os_name != "nt":
        return "sh"
    return "bash" if which("bash") else "powershell"


def shell_invocation(
    command: str,
    shell: str | None = None,
    *,
    shells: Mapping[str, ShellRule] = DEFAULT_SHELLS,
    os_name: str = os.name,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str] | str:
    """셸 형식 명령의 실행 인자.

    Args:
        command: 원래 명령 문자열(사용자가 쓴 그대로).
        shell: 셸 이름(`shells`의 키) 또는 셸 실행 파일 경로. None이면 `default_shell_name`.
        shells: 셸 규칙 표.
        os_name: `os.name` 값(테스트에서 바꾼다).
        which: PATH 검색(테스트에서 바꾼다).

    Returns:
        `subprocess.Popen`에 넘길 인자 목록. Windows의 `raw_command_line` 규칙이면 명령 줄 문자열
        (`cmd /d /s /c "<명령>"`, 명령 안 따옴표를 바꾸지 않는다).
    """
    name = shell or default_shell_name(os_name=os_name, which=which)
    rule = shells.get(name) or ShellRule((name, "-c"))
    if rule.raw_command_line and os_name == "nt":
        head = subprocess.list2cmdline(list(rule.prefix))
        return f'{head} "{command}"'
    return [*rule.prefix, command]


def exec_invocation(argv: Sequence[str]) -> list[str]:
    """실행 형식(셸 없음): 인자 목록을 그대로 쓴다(Claude Code의 `args` 형식과 같음)."""
    if not argv:
        raise ValueError("실행할 명령이 없습니다.")
    return list(argv)
