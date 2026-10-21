"""`agent-console` 명령(Typer).

- `serve`: 서버 실행. 서버는 `agent_console_server`(`_server`에서 지연 import).
- `statusline`: Claude Code statusLine 사용량 브리지. 로직은 `agent_console_usage`.
- `console`은 2R.20에서 삭제했다(design §R5.2).

시작 시간: `statusline`은 Claude Code가 상태 줄을 그릴 때마다 실행되므로 모듈 상단에서
무거운 패키지(서버, 클라이언트, prompt_toolkit 등)를 import하지 않는다
(`tests/test_agent_console_cli_unit.py`가 검사).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from agent_console_usage.statusline import (
    DEFAULT_STATUSLINE_FILE,
    DEFAULT_STATUSLINE_TEMPLATE,
    default_window_labels,
)

from ._server import ServerConfigError, run_server, serve_overrides, server_state_dir
from ._statusline import StatuslineOptions, parse_labels, run_statusline

PROG_NAME = "agent-console"
EXIT_FAILED = 1
CONFIG_ENV = "AGENT_CONSOLE_CONFIG"

app = typer.Typer(
    name=PROG_NAME,
    help="Agent Console — 로컬 서버 실행과 Claude Code 사용량 상태 줄.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="서버 설정 파일(agent-console.yaml). 없으면 AGENT_CONSOLE_CONFIG → 현재 폴더.",
        show_default=False,
    ),
]


@app.command()
def serve(
    config: ConfigOption = None,
    host: Annotated[
        str | None, typer.Option(help="바인딩 주소(기본 설정값 127.0.0.1).", show_default=False)
    ] = None,
    port: Annotated[int | None, typer.Option(help="포트(기본 설정값).", show_default=False)] = None,
    workspace: Annotated[
        str | None, typer.Option(help="정의 YAML 폴더(기본 설정값).", show_default=False)
    ] = None,
    apply_preset: Annotated[
        list[str] | None,
        typer.Option(
            "--apply-preset",
            metavar="ID",
            help="시작할 때 workspace에 적용할 프리셋 id(여러 번 가능, 충돌 시 건너뜀).",
            show_default=False,
        ),
    ] = None,
    allow_origin: Annotated[
        list[str] | None,
        typer.Option(
            "--allow-origin",
            metavar="ORIGIN",
            help=(
                "설정의 security.allowed_origins에 더할 웹 출처(여러 번 가능, 예: "
                "http://127.0.0.1:4173). 설정 파일·환경변수 목록을 지우지 않고 덧붙인다."
            ),
            show_default=False,
        ),
    ] = None,
    open_browser: Annotated[
        bool | None,
        typer.Option(
            "--open/--no-open",
            help=(
                "준비되면 웹 화면을 연다(설정 web.open.enabled를 덮어씀). 열 주소·명령은 설정 "
                "web.open.url·command, 주소가 없으면 web.serve_static이 켜졌을 때 서버 주소."
            ),
            show_default=False,
        ),
    ] = None,
    enable_module: Annotated[
        list[str] | None,
        typer.Option(
            "--enable-module",
            metavar="ID",
            help=(
                "켤 서버 모듈 id(여러 번 가능). 설정 modules보다 우선한다. "
                "목록은 GET /api/v1/modules."
            ),
            show_default=False,
        ),
    ] = None,
    disable_module: Annotated[
        list[str] | None,
        typer.Option(
            "--disable-module",
            metavar="ID",
            help=(
                "끌 서버 모듈 id(여러 번 가능). 설정 modules보다 우선하고, 같은 id면 끄기가 이긴다."
            ),
            show_default=False,
        ),
    ] = None,
) -> None:
    """서버를 실행한다(Ctrl-C로 종료).

    토큰은 출력하지 않는다 — 클라이언트는 GET /bootstrap으로 받는다.
    """
    try:
        overrides = serve_overrides(
            host=host,
            port=port,
            workspace=workspace,
            apply_presets=apply_preset,
            open_browser=open_browser,
        )
        run_server(
            config,
            overrides,
            extra_origins=allow_origin or (),
            enable_modules=enable_module or (),
            disable_modules=disable_module or (),
        )
    except ServerConfigError as exc:
        typer.echo(f"{PROG_NAME}: {exc}", err=True)
        raise typer.Exit(2) from None


@app.command()
def statusline(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="브리지 파일 경로. 없으면 서버 설정 workspace의 .state/usage/statusline.json.",
            show_default=False,
        ),
    ] = None,
    config: ConfigOption = None,
    label: Annotated[
        list[str] | None,
        typer.Option(
            "--label",
            metavar="WINDOW=TEXT",
            help="창 id의 표시 이름(여러 번 가능). 없으면 기본 짧은 이름(5h·7d 등, 데이터).",
            show_default=False,
        ),
    ] = None,
    template: Annotated[
        str,
        typer.Option(
            help="창 하나의 틀. 자리: {label} {window} {percent} {resets_in} {resets_suffix}."
        ),
    ] = DEFAULT_STATUSLINE_TEMPLATE,
    separator: Annotated[str, typer.Option(help="창 사이 구분자.")] = " · ",
    empty: Annotated[str, typer.Option(help="보일 창이 없을 때의 문자열.")] = "",
) -> None:
    """Claude Code statusLine stdin JSON → 사용량 상태 줄 출력 + 브리지 파일(원자적 쓰기).

    `~/.claude`를 읽거나 쓰지 않는다. statusLine 설정은 사용자가 직접 넣는다
    (agent-console-usage README).
    """
    try:
        labels = parse_labels(label) if label else default_window_labels()
        template.format(label="", window="", percent="", resets_in="", resets_suffix="")
    except (ValueError, KeyError, IndexError) as exc:
        typer.echo(f"{PROG_NAME}: 옵션 오류: {exc}", err=True)
        raise typer.Exit(2) from None
    if output is None:
        if config is None and not os.environ.get(CONFIG_ENV):
            typer.echo(
                f"{PROG_NAME}: --output 또는 --config(또는 {CONFIG_ENV})가 필요합니다", err=True
            )
            raise typer.Exit(2)
        try:
            output = server_state_dir(config) / DEFAULT_STATUSLINE_FILE
        except ServerConfigError as exc:
            typer.echo(f"{PROG_NAME}: {exc}", err=True)
            raise typer.Exit(2) from None
    code = run_statusline(
        sys.stdin.buffer.read(),
        output,
        now=time.time,
        out=sys.stdout,
        err=sys.stderr,
        options=StatuslineOptions(
            labels=labels, template=template, separator=separator, empty=empty
        ),
    )
    raise typer.Exit(code)


def main(argv: Sequence[str] | None = None) -> int:
    """`agent-console` 진입점. 종료 코드를 돌려준다.

    Args:
        argv: 인자(None이면 `sys.argv[1:]`).
    """
    command = typer.main.get_command(app)
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command.main(args=args, prog_name=PROG_NAME, standalone_mode=True)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else EXIT_FAILED
    return 0
