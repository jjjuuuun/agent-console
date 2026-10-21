"""`agent-console statusline`: Claude Code statusLine stdin JSON → 상태 줄 + 브리지 파일.

로직(파싱·합치기·원자적 쓰기·표시)은 `agent_console_usage.statusline`에 있고
여기서는 입출력만 잇는다.
`~/.claude`를 읽지도 쓰지도 않는다. 쓰는 곳은 호출자가 준 경로 하나뿐이다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from agent_console_usage.statusline import (
    DEFAULT_STATUSLINE_TEMPLATE,
    format_status_line,
    parse_statusline,
    update_statusline_file,
)

EXIT_OK = 0
EXIT_FAILED = 1


@dataclass(frozen=True, slots=True)
class StatuslineOptions:
    """표시 옵션(전부 데이터)."""

    labels: Mapping[str, str] = field(default_factory=dict)
    template: str = DEFAULT_STATUSLINE_TEMPLATE
    separator: str = " · "
    empty: str = ""


def parse_labels(items: Sequence[str]) -> dict[str, str]:
    """`창=이름` 목록 → dict.

    Raises:
        ValueError: `=`가 없거나 창 id가 비었다.
    """
    out: dict[str, str] = {}
    for item in items:
        window, sep, label = item.partition("=")
        if not sep or not window.strip():
            raise ValueError(f"--label 형식은 창=이름 입니다: {item!r}")
        out[window.strip()] = label
    return out


def run_statusline(
    stdin_data: bytes,
    output: Path,
    *,
    now: Callable[[], float],
    out: TextIO,
    err: TextIO,
    options: StatuslineOptions | None = None,
) -> int:
    """stdin을 처리해 파일에 합쳐 쓰고 상태 줄 한 줄을 `out`에 쓴다. 종료 코드를 돌려준다.

    - 입력이 JSON 객체가 아니면 파일은 그대로, 빈 줄(`empty`)을 쓰고 1.
    - 창이 하나도 없으면 파일은 그대로, 파일에 남은 유효한 창으로 줄을 만든다.
    - 쓰기 실패면 오류를 `err`에 알리고(경로 없이) 1. 줄은 입력만으로 만든다.
    """
    opts = options or StatuslineOptions()
    at = now()
    code = EXIT_OK
    try:
        windows = update_statusline_file(output, stdin_data, now=at)
    except ValueError:
        err.write("agent-console statusline: 입력이 JSON 객체가 아닙니다\n")
        out.write(opts.empty + "\n")
        return EXIT_FAILED
    except OSError as exc:
        err.write(f"agent-console statusline: 파일을 쓰지 못했습니다({type(exc).__name__})\n")
        windows = parse_statusline(stdin_data, now=at)
        code = EXIT_FAILED
    line = format_status_line(
        windows,
        now=at,
        labels=opts.labels,
        template=opts.template,
        separator=opts.separator,
        empty=opts.empty,
    )
    out.write(line + "\n")
    return code
