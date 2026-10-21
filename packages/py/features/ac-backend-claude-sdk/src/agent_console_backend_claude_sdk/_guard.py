"""실행 범위 검사(design §4.7): 도구 호출 입력을 `Limits`의 명령·디렉터리 목록과 대조한다.

SDK와 무관한 순수 로직이다. 백엔드는 이것을 `PreToolUse` 훅(모든 도구 호출, 서브에이전트 포함)과
`can_use_tool`에 걸어 거부 사유를 돌려준다.

- 명령: 입력에 명령 키(기본 `command`)가 있는 모든 도구에 적용. 허용 목록이 비었거나 없으면 전부
  거부, `"*"`는 전부 허용. 셸 연결·치환·리다이렉트 문자(`; & | < > \\` $( 줄바꿈`)가 있으면 거부
  (허용 명령 뒤에 다른 명령을 붙이는 우회 방지). 허용 항목의 토큰이 명령 토큰의 앞부분과 같아야 한다
  (`"git status"`는 `git status -s`를 허용, `git push`는 거부).
- 디렉터리: 입력의 경로 키(기본 `file_path`·`path`·`notebook_path`)가 허용 디렉터리 안인지 본다
  (상대 경로는 cwd 기준, 심볼릭 링크 해석). 명령이 건드리는 파일까지는 알 수 없으므로 최선 노력이다.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ALLOW_ALL = "*"
"""명령 허용 목록에서 '모든 명령'을 뜻하는 항목."""

_SHELL_META = (";", "&", "|", "<", ">", "`", "$(", "\n", "\r")


@dataclass(frozen=True)
class ToolGuard:
    """도구 호출 하나를 검사한다. `check`가 None이면 통과, 문자열이면 거부 사유.

    Args:
        commands: 허용 명령(None이나 빈 목록 = 모두 거부, `"*"` 포함 = 모두 허용).
        directories: 허용 디렉터리(None이면 검사하지 않음).
        cwd: 상대 경로 기준.
        command_keys: 명령으로 볼 입력 키.
        path_keys: 경로로 볼 입력 키.
    """

    commands: Sequence[str] | None
    directories: Sequence[str] | None
    cwd: str | None = None
    command_keys: Sequence[str] = ("command",)
    path_keys: Sequence[str] = ("file_path", "path", "notebook_path")
    _roots: tuple[Path, ...] = field(init=False, repr=False, default=())

    def __post_init__(self) -> None:
        roots = tuple(self._resolve(d) for d in self.directories or ())
        object.__setattr__(self, "_roots", roots)

    def check(self, tool_name: str, tool_input: Mapping[str, Any]) -> str | None:
        """거부 사유(통과면 None)."""
        for key in self.command_keys:
            value = tool_input.get(key)
            if isinstance(value, str):
                reason = self.check_command(value)
                if reason is not None:
                    return f"{tool_name}: {reason}"
        if self.directories is not None:
            for key in self.path_keys:
                value = tool_input.get(key)
                if isinstance(value, str) and value:
                    reason = self.check_path(value)
                    if reason is not None:
                        return f"{tool_name}: {reason}"
        return None

    def check_command(self, command: str) -> str | None:
        """명령 문자열 검사. 거부 사유 또는 None."""
        allowed = list(self.commands or ())
        if ALLOW_ALL in allowed:
            return None
        if not allowed:
            return "명령 실행이 허용되지 않았습니다(limits.commands가 비어 있음)"
        if any(meta in command for meta in _SHELL_META):
            return "셸 연결·치환·리다이렉트가 포함된 명령은 허용되지 않습니다"
        try:
            tokens = shlex.split(command)
        except ValueError:
            return "명령을 해석할 수 없습니다"
        if not tokens:
            return "빈 명령입니다"
        for entry in allowed:
            try:
                prefix = shlex.split(entry)
            except ValueError:
                continue
            if prefix and tokens[: len(prefix)] == prefix:
                return None
        return f"허용 목록에 없는 명령입니다: {tokens[0]}"

    def check_path(self, path: str) -> str | None:
        """경로 검사. 허용 디렉터리 밖이면 거부 사유."""
        target = self._resolve(path)
        if any(target == root or target.is_relative_to(root) for root in self._roots):
            return None
        return f"허용 디렉터리 밖의 경로입니다: {path}"

    def _resolve(self, path: str) -> Path:
        raw = Path(os.path.expanduser(path))
        if not raw.is_absolute() and self.cwd:
            raw = Path(self.cwd) / raw
        return raw.resolve(strict=False)


def guard_from_limits(
    *,
    commands: Iterable[str] | None,
    directories: Iterable[str] | None,
    cwd: str | None,
    command_keys: Iterable[str] = ("command",),
    path_keys: Iterable[str] = ("file_path", "path", "notebook_path"),
) -> ToolGuard:
    """`Limits` 값으로 검사기를 만든다. 디렉터리가 없으면 cwd 하나(cwd도 없으면 검사 안 함)."""
    dirs = list(directories) if directories is not None else ([cwd] if cwd else None)
    return ToolGuard(
        commands=list(commands) if commands is not None else None,
        directories=dirs,
        cwd=cwd,
        command_keys=tuple(command_keys),
        path_keys=tuple(path_keys),
    )
