"""`agent-console` 명령(Typer).

- `serve`: 서버 실행. 인자를 서버 `main`에 그대로 넘긴다(`_server`에서 지연 import).
- `statusline`: Claude Code statusLine 사용량 브리지. 로직은 `agent_console_usage`.
- `logs purge`: 로그 색인 비우기(M-3). 로직은 `agent_console_logs.purge_index`
  (`_logs`에서 지연 import).
- `--version`: 설치 메타데이터(`agent-console-cli`)의 버전을 `agent-console <버전>`으로 출력한다.

시작 시간: `statusline`은 Claude Code가 상태 줄을 그릴 때마다 실행되므로 모듈 상단에서
서버 패키지를 import하지 않는다(`tests/test_agent_console_cli_unit.py`가 검사).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as dist_version
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
DIST_NAME = "agent-console-cli"
"""`--version`이 버전을 읽는 배포 이름(설치 메타데이터)."""
EXIT_FAILED = 1
CONFIG_ENV = "AGENT_CONSOLE_CONFIG"
DEFAULT_LOGS_MODULE = "mod-logs"
"""`logs purge`가 색인 위치(`modules.options.<id>.index_path`)를 읽는 로그 모듈 id 기본값."""

app = typer.Typer(
    name=PROG_NAME,
    help=(
        "Agent Console: run the local server, show Claude Code usage in the status line, "
        "and manage the log index."
    ),
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

logs_app = typer.Typer(
    name="logs",
    help="Manage the log index (edits the index file directly, without the server).",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
app.add_typer(logs_app, name="logs")


def cli_version(read: Callable[[str], str] = dist_version) -> str:
    """설치된 `agent-console-cli` 버전.

    설치 메타데이터가 없으면(소스로 실행) `"0.0.0"`(서버 `server_version`과 같음).

    Args:
        read: 배포 이름 → 버전(기본 `importlib.metadata.version`, 테스트에서 바꿔 끼운다).
    """
    try:
        return read(DIST_NAME)
    except PackageNotFoundError:
        return "0.0.0"


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"{PROG_NAME} {cli_version()}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
) -> None:
    pass


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help=(
            "Server settings file (agent-console.yaml). "
            "Default: AGENT_CONSOLE_CONFIG, then the current folder."
        ),
        show_default=False,
    ),
]


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
)
def serve(ctx: typer.Context) -> None:
    """Run the server (press Ctrl-C to stop). For options, run `agent-console serve --help`.

    The server command line (`agent_console_server.main`) reads the arguments. The API token is
    never printed.
    """
    raise typer.Exit(run_serve(ctx.args, prog=f"{PROG_NAME} serve"))


@app.command()
def statusline(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Bridge file path. Default: .state/usage/statusline.json in the workspace "
                "from the server settings."
            ),
            show_default=False,
        ),
    ] = None,
    config: ConfigOption = None,
    label: Annotated[
        list[str] | None,
        typer.Option(
            "--label",
            metavar="WINDOW=TEXT",
            help=(
                "Display name for a window id (repeatable). "
                "Default: the built-in short names (5h, 7d, and so on)."
            ),
            show_default=False,
        ),
    ] = None,
    template: Annotated[
        str,
        typer.Option(
            help=(
                "Template for one window. Placeholders: "
                "{label} {window} {percent} {resets_in} {resets_suffix}."
            )
        ),
    ] = DEFAULT_STATUSLINE_TEMPLATE,
    separator: Annotated[str, typer.Option(help="Separator between windows.")] = " · ",
    empty: Annotated[str, typer.Option(help="Text to print when there is no window to show.")] = "",
) -> None:
    """Read Claude Code statusLine JSON on stdin and print a usage status line.

    It also updates the bridge file (atomic write). This command never reads or writes
    `~/.claude`; add the statusLine setting yourself (see the agent-console-usage README).
    """
    try:
        labels = parse_labels(label) if label else default_window_labels()
        template.format(label="", window="", percent="", resets_in="", resets_suffix="")
    except (ValueError, KeyError, IndexError) as exc:
        typer.echo(f"{PROG_NAME}: invalid option: {exc}", err=True)
        raise typer.Exit(2) from None
    if output is None:
        if config is None and not os.environ.get(CONFIG_ENV):
            typer.echo(f"{PROG_NAME}: give --output, or --config (or {CONFIG_ENV})", err=True)
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
            help="Log index SQLite file to use (the server settings are not read).",
            show_default=False,
        ),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Event source id (repeatable).", show_default=False),
    ] = None,
    category: Annotated[
        list[str] | None,
        typer.Option("--category", help="Event category id (repeatable).", show_default=False),
    ] = None,
    before: Annotated[
        str | None,
        typer.Option(
            "--before",
            help=(
                "Only events before this time "
                "(epoch seconds or ISO 8601; local time if no time zone)."
            ),
            show_default=False,
        ),
    ] = None,
    rescan: Annotated[
        bool,
        typer.Option(
            "--rescan/--no-rescan",
            help=(
                "Also clear the cursors of the matching sources "
                "so the next collection indexes them again."
            ),
        ),
    ] = True,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Count only, delete nothing (the default).")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Delete for real.")] = False,
    everything: Annotated[
        bool, typer.Option("--all", help="Clear the whole index, with no filter (use with --yes).")
    ] = False,
    module_id: Annotated[
        str,
        typer.Option(
            "--module-id",
            help="Log module id whose index_path to read (settings modules.options).",
        ),
    ] = DEFAULT_LOGS_MODULE,
) -> None:
    """Delete log index rows by source, category, or time. The original log files are not changed.

    By default this only counts the rows it would delete; add `--yes` to delete them. The index is
    `--index`, or else the log module `index_path` from the server settings (`--config`,
    `AGENT_CONSOLE_CONFIG`, or the current folder), or else the server database. To index old events
    again after the classification defaults change, delete the range and collect again.
    """
    if dry_run and yes:
        typer.echo(f"{PROG_NAME}: --dry-run and --yes cannot be used together", err=True)
        raise typer.Exit(2)
    try:
        bound = parse_before(before) if before is not None else None
    except ValueError as exc:
        typer.echo(f"{PROG_NAME}: invalid option: {exc}", err=True)
        raise typer.Exit(2) from None
    if index is None:
        try:
            index = server_log_index_path(config, module_id=module_id)
        except ServerConfigError as exc:
            typer.echo(f"{PROG_NAME}: {exc}", err=True)
            raise typer.Exit(2) from None
    typer.echo(f"Index: {index}")
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
