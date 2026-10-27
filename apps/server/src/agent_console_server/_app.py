"""FastAPI 앱 생성과 실행: 설정 → 호스트 기본 서비스 → 모듈 조립(modkit) → 호스트 경로·모듈
라우터·WS·오류 처리기.

서버는 기능 이름을 모른다(design §3R.1.8, modularity §3.3, 3R.16). entry point
`agent_console.server_modules`로 설치된 모듈을 `agent_console_modkit.assemble`에 넘기고, 받은
라우터·WS 토픽·오류 맵을 붙인다. 기본 서비스(플러그인 레지스트리·DB 핸들·비밀 해석)도 설치된
패키지가 modkit 호스트 확장 지점(entry point)으로 알린 것을 쓴다.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import threading
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ModuleInfo
from agent_console_modkit import (
    MODULES_GROUP,
    Assembly,
    BaseServices,
    HostPlugins,
    Module,
    Paths,
    SettingsCompat,
    assemble,
    compat_flags,
    default_paths,
    env_secret_lookup,
    flag_settings,
    load_host_plugins,
    load_installed_modules,
    open_host_database,
    secret_lookup,
)
from agent_console_modkit.host import (
    TOKEN_HEADER,
    QueryRedactingFilter,
    SecurityMiddleware,
    SecurityPolicy,
    include_routers,
    install_error_map,
    install_feature_unavailable,
    install_log_redaction,
    resolve_token,
)

from ._config import (
    DEFAULT_STATE_DIR,
    ConfigError,
    ServerSettings,
    load_settings,
    settings_compat,
)
from ._errors import register_error_handlers
from ._launch import Opener, build_opener, start_ready_watch
from ._module_options import module_options_payload
from ._modules import apply_module_flags, module_info
from ._openapi import build_openapi
from ._rest_host import build_host_router
from ._restkit import API_PREFIX
from ._server_info import redactor, server_info
from ._static import mount_static, resolve_static_dir
from ._ws import websocket_endpoint

_log = logging.getLogger("agent_console_server")

WS_PATH = "/ws"


def server_version() -> str:
    try:
        return version("agent-console-server")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def _resolve_token(settings: ServerSettings, token: str | None) -> str:
    configured = settings.security.token
    return resolve_token(token, configured.get_secret_value() if configured is not None else None)


def installed_modules(group: str = MODULES_GROUP) -> list[Module]:
    """entry point로 설치된 서버 모듈(읽기 실패는 경고 로그만 남기고 건너뛴다)."""
    modules, reports = load_installed_modules(group)
    for report in reports:
        if not report.ok:
            _log.warning("서버 모듈 로드 실패: %s (%s)", report.source, report.error)
    return modules


def create_app(
    settings: ServerSettings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    token: str | None = None,
    modules: Iterable[Module] | None = None,
) -> FastAPI:
    """서버 앱을 만든다. 모듈은 여기서 조립(build)하고, 저장소·런타임 등은 앱 시작(lifespan) 때
    모듈 시작 훅이 만든다.

    Args:
        settings: 서버 설정. None이면 `load_settings()`(설정 파일 + 환경변수).
        environ: 비밀 공급자(`EnvSecretProvider`)가 읽을 환경. 기본 `os.environ`.
        token: 로컬 API 토큰. 없으면 설정 값, 그것도 없으면 무작위.
        modules: 조립할 모듈. None이면 entry point `agent_console.server_modules`로 설치된 것
            (`installed_modules`).

    Returns:
        FastAPI 앱. `app.state.assembly`(조립 결과)를 둔다. 플러그인 레지스트리는
        여기서 한 번 로드해 모든 모듈에 기본 서비스 `registries`로 넘긴다
        (`agent_console_modkit.load_host_plugins` — 묶음 공장·로더는 설치된 패키지가 알린다).
        비밀 해석 함수(환경변수 `secrets.env_prefix` → 플러그인 비밀 공급자)는 기본 서비스
        `secret_resolver`, DB 핸들(`open_host_database`)은 `database`로 넘긴다.
        `GET /health`는 모듈 시작 훅이 끝난 뒤에만 200이다(그 전·종료 중은 503 `not_ready`).

    Raises:
        ConfigError: 루프백이 아닌 주소인데 `security.allow_remote`가 꺼져 있을 때.
    """
    cfg = settings or load_settings(environ=environ)
    if not cfg.is_loopback and not cfg.security.allow_remote:
        raise ConfigError(
            f"루프백이 아닌 주소({cfg.host})에 바인딩하려면 "
            "security.allow_remote: true가 필요합니다"
        )
    env = os.environ if environ is None else environ
    api_token = _resolve_token(cfg, token)
    policy = SecurityPolicy.from_settings(cfg, api_token)
    srv_version = server_version()

    paths = default_paths(
        cfg.base_dir, workspace=cfg.workspace, state=cfg.workspace / DEFAULT_STATE_DIR
    )
    plugins = load_host_plugins(
        enabled=cfg.plugins.enabled,
        paths=paths,
        modules=cfg.plugins.modules,
        options=cfg.modules.options,
    )
    chosen = installed_modules() if modules is None else list(modules)
    assembly = assemble(chosen, cfg.modules, base=_base_services(cfg, env, plugins, paths))
    for warning in assembly.warnings:
        _log.warning("모듈 설정: %s", warning)
    for report in assembly.report:
        if not report.active:
            _log.info("모듈 %s: %s (%s)", report.id, report.state.value, report.reason or "")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # 시작 실패는 서버 기동 실패다(이전과 같음). 이미 시작한 모듈은 역순으로 정리한다.
        try:
            await assembly.start(fail_fast=True)
        except BaseException:
            await assembly.stop()
            raise
        try:
            yield
        finally:
            await assembly.stop()
            if assembly.services.database is not None:
                assembly.services.database.close()

    app = FastAPI(
        title="Agent Console",
        version=srv_version,
        description="Agent Console 로컬 API. 변경 요청은 `X-Console-Token` 헤더가 필요하다.",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
        separate_input_output_schemas=False,
    )
    app.state.settings = cfg
    app.state.policy = policy
    app.state.assembly = assembly

    redact = redactor(assembly)

    # 호스트 수준 처리기를 먼저 걸고 모듈 오류 맵을 뒤에 건다: 같은 예외 형식이면 모듈 것이 이긴다.
    register_error_handlers(app, redact)
    install_feature_unavailable(app, error_status=HTTP_STATUS_BY_ERROR_CODE, redact=redact)
    install_error_map(
        app, assembly.error_map(), error_status=HTTP_STATUS_BY_ERROR_CODE, redact=redact
    )
    app.include_router(
        build_host_router(
            server_version=srv_version,
            token=api_token,
            ready=lambda: assembly.running,
            modules=_modules_payload(assembly),
            module_options=module_options_payload(
                assembly, hide_paths=not cfg.security.expose_paths
            ),
            info=lambda: server_info(
                cfg, server_version=srv_version, reports=plugins.reports, assembly=assembly
            ),
        ),
        prefix=API_PREFIX,
    )
    # 연동 모듈을 먼저 붙인다(연동의 하위 고정 경로가 기능 모듈의 매개변수 경로에 가리지 않게)
    include_routers(app, assembly, prefix=API_PREFIX)
    app.add_api_websocket_route(WS_PATH, websocket_endpoint(assembly.ws_topics(), policy))
    if cfg.web.serve_static:  # 선택 기능(design §2R.13a 단일 실행): 기본 꺼짐
        mount_static(app, resolve_static_dir(cfg.static_path))
    app.add_middleware(
        SecurityMiddleware,
        policy=policy,
        api_prefix=API_PREFIX,
        error_status=HTTP_STATUS_BY_ERROR_CODE,
        access_logger=logging.getLogger("agent_console_server.access"),
    )
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


def _base_services(
    cfg: ServerSettings, environ: Mapping[str, str], plugins: HostPlugins, paths: Paths
) -> BaseServices:
    """모듈 기본 서비스(경로·환경·플러그인 레지스트리·DB 핸들·비밀 해석 함수).

    DB 핸들은 설치된 DB 공장(modkit `HOST_DATABASE_GROUP`)이 설정의 DB 파일로 연다(없으면 DB 없음).
    켜진 모듈의 마이그레이션 계보는 조립(`assemble`)이 올린다. 모든 모듈이 이 핸들 하나를 쓴다.
    """
    return BaseServices(
        database=open_host_database(cfg.database_path),
        environ=environ,
        paths=paths,
        registries=plugins.registries,
        secret_resolver=secret_lookup(
            env_secret_lookup(environ, prefix=cfg.secrets.env_prefix), plugins.secret_providers
        ),
    )


def flag_overrides(
    values: Mapping[str, Any], compat: Mapping[str, SettingsCompat] | None = None
) -> dict[str, Any]:
    """모듈이 선언한 명령행 옵션 값(`{옵션 이름: 값}`, 예: 예제 모듈의 `echo-tag`) →
    `load_settings(overrides=…)`용 dict. 서버·CLI가 같은 규칙을 쓴다.

    Args:
        values: 옵션 이름(앞의 `--` 없이) → 값. None·빈 목록은 무시한다.
        compat: 모듈 설정 호환 선언. None이면 설치된 모듈(`settings_compat()`).

    Raises:
        ConfigError: 어느 모듈도 선언하지 않은 옵션(그 모듈이 설치되지 않음 등).
    """
    rules = settings_compat() if compat is None else compat
    try:
        return flag_settings(values, rules)
    except KeyError as exc:
        raise ConfigError(
            f"명령행 옵션 --{exc.args[0]}을(를) 선언한 서버 모듈이 설치되어 있지 않습니다"
        ) from None


def _modules_payload(assembly: Assembly) -> Callable[[], list[ModuleInfo]]:
    return lambda: [module_info(r) for r in assembly.report]


def serve(
    settings: ServerSettings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    token: str | None = None,
    opener: Opener | None = None,
    modules: Iterable[Module] | None = None,
) -> None:
    """uvicorn으로 실행한다(막힘).

    `modules`는 `create_app(modules=)`에 그대로 넘긴다(None이면 설치된 모듈).

    준비되면(요청을 받기 시작하면) 준비 줄을 로그에 남기고, `web.open.enabled`면 URL을 연다
    (`opener` 주입, 없으면 `build_opener(web.open)` — 기본 브라우저 또는 `web.open.command`).

    토큰은 어떤 로그에도 남지 않는다: HTTP 접근 로그는 쿼리 없이 앱이 남기고(uvicorn 접근 로그 끔),
    uvicorn 로거(WS 연결 줄 등)에는 `QueryRedactingFilter`(비밀성 쿼리 값·토큰 값 가리기)를 건다.
    """
    import uvicorn

    cfg = settings or load_settings(environ=environ)
    app = create_app(cfg, environ=environ, token=token, modules=modules)
    logging.basicConfig(level=cfg.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    config = uvicorn.Config(
        app,
        host=cfg.host,
        port=cfg.port,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        ws_max_size=cfg.security.max_ws_message_bytes + 1024,
        log_level=cfg.log_level.lower(),
    )
    # uvicorn.Config가 로깅을 구성한 뒤에 건다(dictConfig는 기존 로거 필터를 지우지 않는다).
    policy: SecurityPolicy = app.state.policy
    install_log_redaction(QueryRedactingFilter(values=[policy.token]))
    shown = "localhost" if cfg.host in ("127.0.0.1", "::1") else cfg.host
    _log.info(
        "http://%s:%d — 토큰은 같은 출처의 GET %s/bootstrap으로만 제공됩니다(로그에 남기지 않음)",
        shown,
        cfg.port,
        API_PREFIX,
    )
    # uvicorn은 SIGINT로 정상 종료(lifespan 정리)한 뒤 신호를 다시 올린다(오류 아님).
    server = uvicorn.Server(config)
    stop = threading.Event()
    use_opener = (opener or build_opener(cfg.web.open)) if cfg.web.open.enabled else None
    start_ready_watch(server, cfg, opener=use_opener, stop=stop)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            server.run()
    finally:
        stop.set()


def merge_origins(configured: Iterable[str], extra: Iterable[str]) -> list[str]:
    """설정의 허용 출처 뒤에 `extra`를 덧붙인다(순서 유지, 중복·빈 값 제거, 끝의 `/` 무시).

    Args:
        configured: 설정 파일·환경변수에서 읽은 `security.allowed_origins`.
        extra: 명령행 `--allow-origin` 값.

    Returns:
        합친 목록. 비교는 끝의 `/`를 뗀 문자열로 한다(출처에는 경로가 없다).
    """
    merged: list[str] = []
    seen: set[str] = set()
    for origin in (*configured, *extra):
        value = origin.strip().rstrip("/")
        if value and value not in seen:
            seen.add(value)
            merged.append(value)
    return merged


def main(
    argv: Sequence[str] | None = None,
    *,
    prog: str = "agent-console-server",
    modules: Iterable[Module] | None = None,
) -> int:
    """서버 명령행 진입점: 옵션을 해석해 설정을 읽고 서버를 실행한다(막힘).

    `python -m agent_console_server`와 `agent-console serve`가 이 함수 하나를 쓴다. 옵션:
    `[--config PATH] [--host H] [--port N] [--workspace DIR] [--allow-origin ORIGIN …]
    [--open | --no-open] [--enable-module ID …] [--disable-module ID …] [모듈 옵션…]`.
    모듈 옵션(예: 예제 모듈의 `--echo-tag TAG`)은 모듈이 `SettingsCompat.flags`로 알린 것이다
    (서버는 이름을 모른다).

    Args:
        argv: 인자(None이면 `sys.argv[1:]`).
        prog: 도움말·오류 줄에 쓸 명령 이름.
        modules: 옵션을 읽고 조립할 모듈. None이면 설치된 모듈(`installed_modules`).

    Returns:
        종료 코드(0 정상, 2 설정 오류). 옵션 오류·`--help`는 argparse가 `SystemExit`를 낸다.
    """
    mods = installed_modules() if modules is None else list(modules)
    compat = settings_compat(mods)
    parser = _parser(prog, compat)
    module_flags = compat_flags(compat)
    args = parser.parse_args(list(argv) if argv is not None else None)
    overrides: dict[str, Any] = {}
    for key in ("host", "port", "workspace"):
        if getattr(args, key) is not None:
            overrides[key] = getattr(args, key)
    if args.open is not None:
        overrides["web"] = {"open": {"enabled": args.open}}
    try:
        flagged = {f.setting.flag: getattr(args, _flag_dest(f.setting.flag)) for f in module_flags}
        overrides.update(flag_overrides(flagged, compat))
        settings = load_settings(args.config, overrides=overrides, compat=compat)
        if args.allow_origin:
            origins = merge_origins(settings.security.allowed_origins, args.allow_origin)
            overrides["security"] = {"allowed_origins": origins}
            settings = load_settings(args.config, overrides=overrides, compat=compat)
        settings = apply_module_flags(
            settings, enable=args.enable_module, disable=args.disable_module
        )
        if modules is None:
            serve(settings)
        else:
            serve(settings, modules=mods)
    except ConfigError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return 2
    return 0


def _parser(prog: str, compat: Mapping[str, SettingsCompat]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Agent Console 서버를 실행한다(Ctrl-C로 종료). 토큰은 출력하지 않는다 — "
            "클라이언트는 GET /api/v1/bootstrap으로 받는다. "
            "우선순위: 명령행 > AGENT_CONSOLE_* 환경변수 > 설정 파일 > 기본값."
        ),
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        metavar="PATH",
        help="서버 설정 파일(agent-console.yaml). 없으면 AGENT_CONSOLE_CONFIG → 현재 폴더",
    )
    parser.add_argument("--host", default=None, help="바인딩 주소(기본 설정값 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="포트(기본 설정값)")
    parser.add_argument("--workspace", default=None, metavar="DIR", help="정의 YAML 폴더")
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help=(
            "설정의 security.allowed_origins 뒤에 더할 웹 출처(여러 번 가능, 예: "
            "http://127.0.0.1:4173). 설정 파일·환경변수 목록을 지우지 않고 덧붙인다"
        ),
    )
    for flag in compat_flags(compat):
        parser.add_argument(
            f"--{flag.setting.flag}",
            dest=_flag_dest(flag.setting.flag),
            action="append" if flag.setting.repeat else "store",
            default=None,
            metavar=flag.setting.metavar,
            help=f"{flag.setting.help} (모듈 {flag.module_id})",
        )
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "준비되면 웹 화면을 연다(설정 web.open.enabled를 덮어씀). 열 주소·명령은 설정 "
            "web.open.url·command, 주소가 없으면 web.serve_static이 켜졌을 때 서버 주소"
        ),
    )
    parser.add_argument(
        "--enable-module",
        action="append",
        default=[],
        metavar="ID",
        help="켤 서버 모듈 id(여러 번 가능, 설정 modules보다 우선). 목록은 GET /api/v1/modules",
    )
    parser.add_argument(
        "--disable-module",
        action="append",
        default=[],
        metavar="ID",
        help="끌 서버 모듈 id(여러 번 가능, 설정 modules보다 우선, 같은 id면 끄기가 이김)",
    )
    return parser


def _flag_dest(flag: str) -> str:
    return "module_flag_" + flag.replace("-", "_")


__all__ = [
    "TOKEN_HEADER",
    "create_app",
    "flag_overrides",
    "installed_modules",
    "main",
    "merge_origins",
    "serve",
    "server_version",
]
