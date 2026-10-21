"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-usage``, design §3R.1.3).

- 제공: ``usage.service``. 필수 포트 없음(혼자 켜진다).
- 제공: ``server.warnings``(런타임 출처 id 겹침 ``usage.source_conflict``, 저장된 출처 설정이
  출처 스키마에 맞지 않음 ``usage.source_config_invalid``).
- 제공: ``definitions.checks``(공통 설정 저장 전 출처 설정 검증 — error면 저장 측이 422로 거부.
  저장 시점에 없는 런타임 출처는 건너뛰고 나타나면 경고로 알린다).
- 선택: ``usage.event_query``·``usage.token_rollups``·``workspace.settings``·``usage.sources``
  (multi, 런타임 출처 — 부를 때마다 다시 읽는다)(``ports.py``).
- 저장소: 관측값(``usage_observations``)은 이 모듈이 소유한다(``storage/``). 호스트 DB 핸들
  (``BaseServices.database``)의 엔진 위에 만들고, 마이그레이션 계보 ``usage``는 모듈이 켜질 때만
  올라간다. DB 핸들이 없으면 관측값을 기록·정리하지 않는다(나머지는 동작).
- 출처 레지스트리: 호스트 기본 서비스 ``registries``의 ``usage_sources`` 확장을 쓴다. 호스트가
  레지스트리를 주지 않으면(단독 실행) entry point에서 직접 읽는다.
- 배경 작업: 저장소가 있고 ``retention_seconds``가 정해져 있으면 주기적으로
  정리한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS, Issue, UsageSettings
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_registry import Registry
from agent_console_usage import (
    SETUP_AGENT_CONSOLE_CMD,
    USAGE_SOURCES_EXTENSION,
    UsageService,
    UsageSource,
    as_usage_source,
    load_usage_sources,
    new_usage_sources,
)

from .checks import UsageSettingsCheck
from .ports import (
    DEFINITION_CHECKS,
    EVENT_QUERY,
    SERVER_WARNINGS,
    TOKEN_ROLLUPS,
    USAGE_SERVICE,
    USAGE_SOURCES,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .service import UsageReportService
from .settings import SETTINGS_COMPAT, UsageModuleSettings
from .storage import BRANCH, SqliteUsageObservationRepository

MODULE_ID = "mod-usage"
WEB_ROLES: tuple[str, ...] = ("usage",)
"""웹 라우트 역할(design §3R.1.3 표)."""

_log = logging.getLogger("agent_console_mod_usage")

SOURCE_CONFLICT = "usage.source_conflict"
"""``server.warnings`` 이슈 코드: 런타임 출처 id가 다른 출처와 겹쳐 빠졌다."""


def _version() -> str:
    try:
        return version("agent-console-mod-usage")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def usage_sources_of(registries: Any) -> Registry[UsageSource]:
    """호스트 레지스트리 묶음의 ``usage_sources`` 확장.

    묶음이 없으면(단독 실행) entry point에서 새로 읽는다.
    """
    extension = getattr(registries, "extension", None)
    if callable(extension):
        found: Registry[UsageSource] = extension(USAGE_SOURCES_EXTENSION, validator=as_usage_source)
        return found
    registry = new_usage_sources()
    for report in load_usage_sources(registry):
        if not report.ok:
            _log.warning("사용량 출처 로드 실패: %s (%s)", report.source, report.error)
    return registry


def resolve_command(
    command: str, environ: Mapping[str, str], *, extra_dirs: Iterable[str] = ()
) -> str:
    """연결 안내 조각에 넣을 명령(절대 경로). 사용자가 그대로 붙여 넣어 동작해야 한다.

    경로(``/``·``\\`` 포함)면 절대 경로로 바꾸고, 이름이면 주입된 ``PATH``에서, 못 찾으면
    ``extra_dirs``(예: 이 서버를 실행한 파이썬의 폴더)에서 찾는다. 끝내 못 찾으면 이름 그대로.

    >>> resolve_command("/opt/ac/bin/agent-console", {})
    '/opt/ac/bin/agent-console'
    >>> resolve_command("no-such-command-xyz", {"PATH": ""})
    'no-such-command-xyz'
    """
    if "/" in command or "\\" in command:
        return os.path.abspath(command)
    path = environ.get("PATH", "")
    found = shutil.which(command, path=path)
    if not found:
        extra = os.pathsep.join(d for d in extra_dirs if d)
        found = shutil.which(command, path=extra) if extra else None
    return os.path.abspath(found) if found else command


def runtime_usage_sources(items: Iterable[object]) -> tuple[dict[str, UsageSource], list[str]]:
    """``usage.sources`` 포트 목록 → (id → 출처, 겹쳐 빠진 id).

    id는 디스크립터 ``id``다. 같은 id가 여럿이면 먼저 온 것(제공 모듈 id 순)이 이긴다.
    출처 프로토콜을 만족하지 않는 항목은 빼고 경고 로그를 남긴다.
    """
    found: dict[str, UsageSource] = {}
    duplicates: list[str] = []
    for item in items:
        try:
            source = as_usage_source(item)
        except TypeError:
            _log.warning("usage.sources 항목이 사용량 출처가 아닙니다: %s", type(item).__name__)
            continue
        key = source.descriptor.id
        if key in found:
            duplicates.append(key)
            continue
        found[key] = source
    return found, duplicates


def _conflict_issue(source_id: str) -> Issue:
    return Issue(
        severity="warning",
        code=SOURCE_CONFLICT,
        message=(
            f"사용량 출처 id {source_id}가 다른 출처와 겹쳐 하나만 씁니다"
            "(플러그인 출처, 그다음 먼저 연결된 모듈 우선)"
        ),
        details={"source": source_id},
    )


class UsageModule:
    """사용량 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="사용량",
        description="창 스냅샷·토큰 집계·출처 목록(/usage, /usage/sources)",
        provides=(USAGE_SERVICE, SERVER_WARNINGS, DEFINITION_CHECKS),
        optional=(EVENT_QUERY, TOKEN_ROLLUPS, WORKSPACE_SETTINGS, USAGE_SOURCES),
        settings_schema=UsageModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"usage": CONTRACT_VERSIONS["usage"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, UsageModuleSettings):
            cfg = UsageModuleSettings()
        clock = ctx.clock

        def now() -> float:
            return clock().timestamp()

        database = ctx.database
        observations = (
            SqliteUsageObservationRepository(database.engine) if database is not None else None
        )
        runtime_duplicates: set[str] = set()

        def runtime_sources() -> dict[str, UsageSource]:
            # 조립 뒤에 채워지는 포트라 부를 때마다 읽는다(연동 모듈이 mod-usage보다 늦게 만들어짐)
            found, duplicates = runtime_usage_sources(ctx.ports(USAGE_SOURCES))
            runtime_duplicates.update(duplicates)
            return found

        usage = UsageService(
            usage_sources_of(ctx.registries),
            clock=now,
            events=ctx.port(EVENT_QUERY),
            state_dir=ctx.paths.state if ctx.paths is not None else None,
            observations=observations,
            timeout_seconds=cfg.source_timeout_seconds,
            extra_sources=runtime_sources,
            setup_values={
                SETUP_AGENT_CONSOLE_CMD: resolve_command(
                    cfg.agent_console_command,
                    ctx.environ,
                    extra_dirs=[os.path.dirname(sys.executable)],
                )
            },
        )

        reader = ctx.port(WORKSPACE_SETTINGS)

        def user_settings() -> UsageSettings | None:
            return reader().usage if reader is not None else None

        def warnings() -> list[Issue]:
            ids = set(usage.conflicts()) | runtime_duplicates
            found = [_conflict_issue(sid) for sid in sorted(ids)]
            try:
                current = user_settings()
            except Exception:  # 손상된 설정 파일: 정의 모듈이 따로 알린다
                current = None
            return found + usage.config_issues(current, severity="warning")

        service = UsageReportService(
            usage,
            settings=user_settings,
            rollups=ctx.port(TOKEN_ROLLUPS),
            rollup_run_limit=cfg.rollup_run_limit,
            clock=now,
        )
        ctx.provide(USAGE_SERVICE, service)
        ctx.provide(SERVER_WARNINGS, warnings)
        ctx.provide(DEFINITION_CHECKS, UsageSettingsCheck(usage))

        background: list[Callable[[], Awaitable[None]]] = []
        retention = cfg.retention_seconds
        if observations is not None and retention is not None:

            async def prune() -> None:
                while True:
                    try:
                        removed = await asyncio.to_thread(usage.prune, keep_seconds=retention)
                        if removed:
                            _log.info("오래된 사용량 관측값 %d개를 지웠습니다", removed)
                    except Exception:
                        _log.exception("사용량 관측값 정리 실패")
                    await asyncio.sleep(cfg.prune_interval_seconds)

            background.append(prune)

        return ModuleParts(routers=[build_router(lambda: service)], background=background)


module = UsageModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "MODULE_ID",
    "SOURCE_CONFLICT",
    "WEB_ROLES",
    "UsageModule",
    "module",
    "resolve_command",
    "runtime_usage_sources",
    "usage_sources_of",
]
