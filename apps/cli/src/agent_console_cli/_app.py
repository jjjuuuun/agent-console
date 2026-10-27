"""`agent-console` 명령(Typer).

- `serve`: 서버 실행. 인자를 서버 `main`에 그대로 넘긴다(`_server`에서 지연 import).
- `statusline`: Claude Code statusLine 사용량 브리지. 로직은 `agent_console_usage`.
- `logs purge`: 로그 색인 비우기(M-3). 로직은 `agent_console_logs.purge_index`
  (`_logs`에서 지연 import).

시작 시간: `statusline`은 Claude Code가 상태 줄을 그릴 때마다 실행되므로 모듈 상단에서
서버 패키지를 import하지 않는다(`tests/test_agent_console_cli_unit.py`가 검사).
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

from ._logs import PurgeOptions, parse_before, run_purge
from ._server import ServerConfigError, run_serve, server_log_index_path, server_state_dir
from ._statusline import StatuslineOptions, parse_labels, run_statusline

PROG_NAME = "agent-console"
EXIT_FAILED = 1
CONFIG_ENV = "AGENT_CONSOLE_CONFIG"
DEFAULT_LOGS_MODULE = "mod-logs"
"""`logs purge`가 색인 위치(`modules.options.<id>.index_path`)를 읽는 로그 모듈 id 기본값."""

app = typer.Typer(
    name=PROG_NAME,
    help="Agent Console — 로컬 서버 실행, Claude Code 사용량 상태 줄, 로그 색인 관리.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

logs_app = typer.Typer(
    name="logs",
    help="로그 색인 관리(서버 없이 색인 파일을 직접 고친다).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
app.add_typer(logs_app, name="logs")


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="서버 설정 파일(agent-console.yaml). 없으면 AGENT_CONSOLE_CONFIG → 현재 폴더.",
        show_default=False,
    ),
]


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
)
def serve(ctx: typer.Context) -> None:
    """서버를 실행한다(Ctrl-C로 종료). 옵션은 `agent-console serve --help`.

    인자는 서버 명령행(`agent_console_server.main`)이 해석한다. 토큰은 출력하지 않는다.
    """
    raise typer.Exit(run_serve(ctx.args, prog=f"{PROG_NAME} serve"))


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


@logs_app.command("purge")
def logs_purge(
    config: ConfigOption = None,
    index: Annotated[
        Path | None,
        typer.Option(
            "--index",
            help="색인 SQLite 파일을 직접 지정(서버 설정을 읽지 않는다).",
            show_default=False,
        ),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="이벤트 출처 id(여러 번 가능).", show_default=False),
    ] = None,
    category: Annotated[
        list[str] | None,
        typer.Option("--category", help="이벤트 범주 id(여러 번 가능).", show_default=False),
    ] = None,
    before: Annotated[
        str | None,
        typer.Option(
            "--before",
            help="이 시각보다 이른 이벤트만(epoch 초 또는 ISO 8601, 시간대 없으면 로컬).",
            show_default=False,
        ),
    ] = None,
    rescan: Annotated[
        bool,
        typer.Option(
            "--rescan/--no-rescan",
            help="범위 출처의 커서도 지워 다음 수집에서 다시 색인되게 한다.",
        ),
    ] = True,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="지우지 않고 수만 센다(기본 동작).")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="실제로 지운다.")] = False,
    everything: Annotated[
        bool, typer.Option("--all", help="범위 없이 색인 전체를 비운다(--yes와 함께).")
    ] = False,
    module_id: Annotated[
        str,
        typer.Option("--module-id", help="색인 위치를 읽을 로그 모듈 id(설정 modules.options)."),
    ] = DEFAULT_LOGS_MODULE,
) -> None:
    """로그 색인에서 출처·범주·시각 범위의 행을 지운다. 원본 로그 파일은 그대로다.

    기본은 지울 행 수만 센다. `--yes`가 있어야 지운다. 색인 위치는 `--index`, 없으면 서버 설정
    (`--config`·`AGENT_CONSOLE_CONFIG`·현재 폴더)의 로그 모듈 `index_path` → 서버 DB 순이다.
    분류 기본값이 바뀐 뒤 옛 이벤트를 다시 색인하려면 범위를 지우고 다시 수집한다.
    """
    if dry_run and yes:
        typer.echo(f"{PROG_NAME}: --dry-run과 --yes는 함께 쓸 수 없습니다", err=True)
        raise typer.Exit(2)
    try:
        bound = parse_before(before) if before is not None else None
    except ValueError as exc:
        typer.echo(f"{PROG_NAME}: 옵션 오류: {exc}", err=True)
        raise typer.Exit(2) from None
    if index is None:
        try:
            index = server_log_index_path(config, module_id=module_id)
        except ServerConfigError as exc:
            typer.echo(f"{PROG_NAME}: {exc}", err=True)
            raise typer.Exit(2) from None
    typer.echo(f"색인: {index}")
    code = run_purge(
        index,
        PurgeOptions(
            sources=tuple(source or ()),
            categories=tuple(category or ()),
            before=bound,
            rescan=rescan,
            apply=yes,
            everything=everything,
        ),
        out=sys.stdout,
        err=sys.stderr,
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
