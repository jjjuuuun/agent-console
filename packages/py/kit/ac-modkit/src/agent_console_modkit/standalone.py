"""모듈 하나 단독 실행(개발·재사용, modularity §3.9.4). extra ``[host]``가 필요하다.

각 모듈 패키지의 ``__main__.py``는 이 함수를 부르는 몇 줄뿐이다::

    import sys
    from agent_console_modkit.standalone import run
    from my_module.module import module
    raise SystemExit(run(module, argv=sys.argv[1:]))

옵션(통합 실행과 같은 호스트 코드·보안 규칙):
    ``--with ID``      함께 띄울 모듈 id(반복). 설치된 entry point(``MODULES_GROUP``)에서 찾는다.
                       필수 포트를 자동으로 끌어오지 않는다(사용자가 고른다). 하나도 주지 않으면
                       모듈 패키지가 ``run(default_with=)``로 정한 모듈을 붙인다.
    ``--config PATH``  설정 파일(통합 서버 설정과 같은 키, ``.json``·``.toml``·YAML).
    ``--host H``       바인딩 주소(기본 127.0.0.1). 루프백이 아니면 ``security.allow_remote`` 필요.
    ``--port N``       포트(0 = 빈 포트).
    ``--check``        시작 → ``GET <api_prefix>/health`` 200 확인 → 종료(이식성 검사용).
    ``--timeout S``    ``--check`` 준비 대기 한도(초, 기본 30).

종료 코드: 0 정상, 1 대상 모듈이 켜지지 않음·``--check`` 실패, 2 인자·설정 오류.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from ._assemble import Assembly, ModuleState, assemble
from ._database import DatabaseHandle
from ._loading import load_installed_modules
from ._module import Module
from ._services import BaseServices, Paths
from .host import (
    DEFAULT_ERROR_STATUS,
    HostSettings,
    QueryRedactingFilter,
    SecurityPolicy,
    create_host_app,
    install_log_redaction,
    is_loopback_host,
    load_host_settings,
    resolve_token,
)

_log = logging.getLogger("agent_console_modkit.standalone")


def build_parser(prog: str) -> argparse.ArgumentParser:
    """단독 실행 인자 해석기."""
    parser = argparse.ArgumentParser(prog=prog, description="모듈 단독 실행(개발·재사용)")
    parser.add_argument("--with", dest="with_", action="append", default=[], metavar="ID")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def select_modules(
    module: Module, with_ids: Sequence[str], available: Iterable[Module]
) -> tuple[list[Module], list[str]]:
    """대상 모듈 + ``--with`` 모듈. 돌려준 값: (모듈 목록, 찾지 못한 id)."""
    by_id: dict[str, Module] = {}
    for m in available:
        by_id.setdefault(m.descriptor.id, m)
    chosen = [module]
    missing: list[str] = []
    for mid in with_ids:
        if mid == module.descriptor.id or any(m.descriptor.id == mid for m in chosen):
            continue
        found = by_id.get(mid)
        if found is None:
            missing.append(mid)
        else:
            chosen.append(found)
    return chosen, missing


def format_report(assembly: Assembly) -> str:
    """보고 표(한 줄에 모듈 하나)."""
    lines = []
    for r in assembly.report:
        reason = f" — {r.reason}" if r.reason else ""
        lines.append(f"{r.id} {r.version} [{r.kind}] {r.state.value}{reason}")
    lines.extend(f"경고: {w}" for w in assembly.warnings)
    return "\n".join(lines)


def _url_host(host: str) -> str:
    if host in ("0.0.0.0", ""):
        return "127.0.0.1"
    if host == "::":
        return "[::1]"
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _http_status(url: str, timeout: float) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


async def check_app(app: Any, settings: HostSettings, *, timeout: float, out: TextIO) -> int:
    """앱을 띄워 ``/health``가 200인지 확인하고 끈다. 0이면 성공."""
    import uvicorn

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    task = asyncio.ensure_future(server.serve())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while not server.started:
            if task.done() or loop.time() > deadline:
                print("check: 서버가 시작하지 못했습니다", file=out)
                return 1
            await asyncio.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        url = f"http://{_url_host(settings.host)}:{port}{settings.api_prefix}/health"
        status = await asyncio.to_thread(_http_status, url, timeout)
        print(f"check: GET {settings.api_prefix}/health → {status}", file=out)
        return 0 if status == 200 else 1
    finally:
        server.should_exit = True
        await task


def run(
    module: Module,
    argv: Sequence[str] | None = None,
    *,
    available: Iterable[Module] | None = None,
    default_with: Sequence[Module] = (),
    error_status: Mapping[str, int] | None = None,
    environ: Mapping[str, str] | None = None,
    base: BaseServices | None = None,
    database: Callable[[Paths], DatabaseHandle | None] | None = None,
    serve: Callable[[Any, HostSettings], None] | None = None,
    out: TextIO | None = None,
    prog: str | None = None,
) -> int:
    """모듈 하나(+ ``--with``)를 호스트에 붙여 실행한다.

    Args:
        module: 대상 모듈.
        argv: 명령행 인자(None이면 ``sys.argv[1:]``).
        available: ``--with``로 고를 수 있는 모듈. None이면 설치된 entry point.
        default_with: ``--with``를 하나도 주지 않았을 때 함께 띄울 모듈. 모듈 패키지가 단독
            실행용으로 정한다(예: 같은 패키지 ``testing``의 로컬 제공 모듈). ``--with``로도 고를
            수 있다. ``--with``를 주면 쓰지 않는다(사용자가 고른 것만 붙인다).
        error_status: 오류 코드 → HTTP 상태(모듈이 쓰는 계약 표). None이면 호스트 기본값.
        environ: 모듈에 줄 환경. None이면 ``os.environ``.
        base: 기본 서비스. None이면 ``environ``·설정 경로로 만든다.
        database: ``base``가 None일 때 DB 핸들을 만드는 함수(경로 → 핸들). 저장소가 있는 모듈의
            단독 실행용(예: ``lambda paths: SqliteDatabase.open(paths.state / "console.sqlite3")``).
            끝나면 핸들을 닫는다. None이면 DB 없이 띄운다(저장이 필요한 부분은 꺼진다).
        serve: 막히는 실행 함수(테스트 주입). None이면 uvicorn.
        out: 보고 출력. None이면 ``sys.stdout``.
        prog: 도움말 프로그램 이름.

    Returns:
        종료 코드(0 정상, 1 모듈 꺼짐·확인 실패, 2 인자·설정 오류).
    """
    stream = out or sys.stdout
    parser = build_parser(prog or f"python -m {type(module).__module__.split('.')[0]}")
    args = parser.parse_args(list(argv) if argv is not None else None)
    overrides: dict[str, Any] = {}
    if args.host is not None:
        overrides["host"] = args.host
    if args.port is not None:
        overrides["port"] = args.port
    try:
        settings = load_host_settings(args.config, overrides=overrides)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"설정 오류: {exc}", file=stream)
        return 2
    if not is_loopback_host(settings.host) and not settings.security.allow_remote:
        print(
            f"루프백이 아닌 주소({settings.host})에 바인딩하려면 "
            "security.allow_remote: true가 필요합니다",
            file=stream,
        )
        return 2
    pool = list(available) if available is not None else load_installed_modules()[0]
    pool = [*default_with, *pool]
    with_ids = list(args.with_) or [m.descriptor.id for m in default_with]
    modules, missing = select_modules(module, with_ids, pool)
    if missing:
        print(f"--with 모듈을 찾을 수 없습니다: {', '.join(missing)}", file=stream)
        return 2
    env = os.environ if environ is None else environ
    fallback = args.config.parent if args.config is not None else Path.cwd()
    if base is not None:
        services = base
    else:
        paths = settings.paths(fallback)
        services = BaseServices(
            environ=env, paths=paths, database=database(paths) if database is not None else None
        )
    try:
        return _run_assembled(
            module, modules, settings, services, args, stream, serve, error_status
        )
    finally:
        if base is None and services.database is not None:
            services.database.close()


def _run_assembled(
    module: Module,
    modules: Sequence[Module],
    settings: HostSettings,
    services: BaseServices,
    args: argparse.Namespace,
    stream: TextIO,
    serve: Callable[[Any, HostSettings], None] | None,
    error_status: Mapping[str, int] | None,
) -> int:
    assembly = assemble(modules, settings.modules, base=services)
    print(format_report(assembly), file=stream)
    target = assembly.status(module.descriptor.id)
    if target is None or target.state is not ModuleState.ACTIVE:
        return 1
    token_value = settings.security.token.get_secret_value() if settings.security.token else None
    token = resolve_token(configured=token_value)
    policy = SecurityPolicy.from_settings(settings, token)
    install_log_redaction(QueryRedactingFilter(values=[token]))
    app = create_host_app(
        assembly,
        policy=policy,
        title=module.descriptor.title,
        version=module.descriptor.version,
        api_prefix=settings.api_prefix,
        ws_path=settings.ws_path,
        error_status=error_status if error_status is not None else DEFAULT_ERROR_STATUS,
    )
    if args.check:
        return asyncio.run(check_app(app, settings, timeout=args.timeout, out=stream))
    (serve or _serve_uvicorn)(app, settings)
    return 0


def _serve_uvicorn(app: Any, settings: HostSettings) -> None:
    import uvicorn

    logging.basicConfig(
        level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        ws_max_size=settings.security.max_ws_message_bytes + 1024,
        log_level=settings.log_level.lower(),
    )


__all__ = ["build_parser", "check_app", "format_report", "run", "select_modules"]
