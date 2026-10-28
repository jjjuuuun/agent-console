"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-logs``, design §4R.8).

- 제공: ``logs.query``·``logs.ingest``(``LogsService``)·``server.warnings``. 토픽 ``logs.ingested``,
  WS ``logs``. 경로 ``/logs…``(§4R.10). 필수 포트 없음(혼자 켜진다).
- 선택: ``logs.sources``(런타임 출처, multi)·``workspace.settings``(``logs.*``)·``secrets.rules``
  (가리기)·``logs.source_defaults``(출처 기본 켜기, multi — 설정에 ``enabled``가 없는 출처만)·
  ``logs.scope_kinds``(범위 종류 X27, multi)·``logs.filter_predicates``(필터 확장 X28, multi)
  — ``ports.py``.
- 출처·분류기: 호스트 레지스트리 묶음의 ``log_sources``·``log_classifiers`` 확장(플러그인 로더
  ``plugins.load_plugins``가 entry point X5·X6을 로드). 묶음이 없으면(단독 실행) entry point에서
  직접 읽는다.
- 저장: 계보 ``logs``(``storage.BRANCH``)는 모듈이 켜질 때만 호스트가 올린다. 옵션 ``index_path``면
  그 파일에 같은 계보를 직접 올린다. DB가 없으면 메모리 색인(``logs.storage_memory`` 경고).
- 시작: 런타임 출처를 수집기에 붙이고 이벤트 루프에 연결한다. 배경 작업 하나가 ``startup_scan``이면
  바로, 그 뒤 ``scan_interval_seconds``마다 수집한다(파일 읽기는 스레드). 종료 때 예약 작업을 멈추고
  별도 파일 색인을 닫는다.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from agent_console_contracts import CONTRACT_VERSIONS, Issue, KnownIssueCodes
from agent_console_contracts.logs import LogSettings, LogTaxonomy
from agent_console_contracts.modules import LogsIngestedPayload
from agent_console_logs import LogRegistries, ProjectFolders, load_default_taxonomy
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .plugins import bundle_registries
from .ports import (
    LOG_FILTER_PREDICATES,
    LOG_SCOPE_KINDS,
    LOG_SOURCES,
    LOGS_INGEST,
    LOGS_INGESTED,
    LOGS_QUERY,
    PROJECT_FOLDERS,
    SECRET_RULES,
    SERVER_WARNINGS,
    SOURCE_DEFAULTS,
    WORKSPACE_SETTINGS,
)
from .redaction import LogRedaction
from .routes import build_router
from .service import LogsService
from .settings import LogsModuleSettings
from .source_defaults import apply_source_defaults, collect_source_defaults
from .storage import BRANCH, open_log_storage
from .templates import load_dashboard_templates
from .ws import LOGS_TOPIC, ingested_message, topic_handlers

MODULE_ID = "mod-logs"
WEB_ROLES: tuple[str, ...] = ("logs",)
"""웹 라우트 역할(design §4R.8 표)."""

_log = logging.getLogger("agent_console_mod_logs")


def _version() -> str:
    try:
        return version("agent-console-mod-logs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def log_registries_of(registries: Any) -> LogRegistries:
    """호스트 묶음의 출처·분류기 레지스트리.

    묶음이 없으면(단독 실행) entry point에서 새로 읽는다.
    """
    found = bundle_registries(registries)
    if found is not None:
        return found
    fresh = LogRegistries()
    for group, reports in fresh.load().items():
        for report in reports:
            if not report.ok:
                _log.warning("%s 로드 실패: %s (%s)", group, report.source, report.error)
    return fresh


def _resolve(path: Path | None, base: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute() or base is None:
        return path
    return base / path


def base_taxonomy_of(option: Path | Literal[False] | None, base: Path | None) -> LogTaxonomy | None:
    """설치자 옵션 ``base_taxonomy_file`` → 기본 분류 체계.

    Args:
        option: None = 패키지 기본(None을 돌려 ``LogsService``가 읽게 한다), False = 빈 분류,
            경로 = 그 파일(상대 경로는 ``base`` 기준).
        base: 설정 파일 폴더.

    Returns:
        분류 체계 또는 None(패키지 기본). 파일이 없으면 경고를 남기고 빈 분류 체계.

    Raises:
        ValueError·pydantic.ValidationError: 파일 내용이 분류 체계 형식이 아닐 때.
    """
    if option is None:
        return None
    if option is False:
        return LogTaxonomy()
    path = option if option.is_absolute() or base is None else base / option
    if not path.is_file():
        _log.warning("기본 분류 체계 파일이 없어 빈 분류를 씁니다: %s", path)
    return load_default_taxonomy(path)


def storage_memory_warning() -> Issue:
    return Issue(
        severity="warning",
        code=KnownIssueCodes.LOGS_STORAGE_MEMORY,
        message="DB가 없어 로그 색인을 메모리에만 둡니다(재시작하면 다시 수집합니다)",
    )


def redaction_unavailable_warning() -> Issue:
    return Issue(
        severity="warning",
        code=KnownIssueCodes.LOGS_REDACTION_UNAVAILABLE,
        message="비밀 의심 규칙이 없어 로그 색인을 가리지 않고 저장합니다",
    )


class LogsModule:
    """로그 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="로그",
        description=(
            "로그 출처 수집(배경·수동)·색인 질의(/logs…)·대시보드 템플릿, WS logs. "
            "런타임 출처·설정·가림 규칙은 포트로 받는다"
        ),
        provides=(LOGS_QUERY, LOGS_INGEST, SERVER_WARNINGS),
        optional=(
            LOG_SOURCES,
            WORKSPACE_SETTINGS,
            SECRET_RULES,
            SOURCE_DEFAULTS,
            LOG_SCOPE_KINDS,
            LOG_FILTER_PREDICATES,
            PROJECT_FOLDERS,
        ),
        settings_schema=LogsModuleSettings,
        contracts={"logs": CONTRACT_VERSIONS["logs"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, LogsModuleSettings):
            cfg = LogsModuleSettings()
        paths = ctx.paths
        base = paths.base_dir if paths is not None else None
        storage = open_log_storage(ctx.database, index_path=_resolve(cfg.index_path, base))
        registries = log_registries_of(ctx.registries)
        clock = ctx.clock
        hub: Any = ctx.ws_hub

        def now() -> float:
            return clock().timestamp()

        def log_settings() -> LogSettings | None:
            reader = ctx.port(WORKSPACE_SETTINGS)
            current = reader().logs if reader is not None else None
            # 다른 모듈이 정한 출처 기본 켜기(설정에 enabled가 없는 출처만, 설정 파일은 그대로)
            defaults = collect_source_defaults(ctx.ports(SOURCE_DEFAULTS))
            return apply_source_defaults(current, defaults)

        def project_folders() -> ProjectFolders:
            # 앱에 등록된 프로젝트 폴더만 수집한다. 포트가 없으면 등록된 프로젝트 없음(빈 범위).
            reader = ctx.port(PROJECT_FOLDERS)
            if reader is None:
                return ProjectFolders()
            try:
                value = reader()
                return ProjectFolders(
                    current=tuple(Path(p) for p in value.current),
                    registered=tuple(Path(p) for p in value.registered),
                )
            except Exception:  # 프로젝트를 읽지 못하면 이번 수집은 빈 범위
                _log.exception("등록된 프로젝트 폴더를 읽지 못했습니다")
                return ProjectFolders()

        redaction = LogRedaction(
            workspace=lambda: ctx.port(WORKSPACE_SETTINGS), rules=lambda: ctx.port(SECRET_RULES)
        )
        templates_dir = _resolve(cfg.dashboard_templates_dir, base)

        def on_ingested(payload: LogsIngestedPayload) -> None:
            hub.publish(LOGS_TOPIC, ingested_message(payload))
            ctx.publish(LOGS_INGESTED, payload)

        service = LogsService(
            storage.index,
            registries,
            settings=log_settings,
            redact=redaction,
            clock=now,
            environ=ctx.environ,
            paths=(
                {"base_dir": paths.base_dir, "workspace": paths.workspace, "state": paths.state}
                if paths is not None
                else {}
            ),
            budget_bytes=cfg.scan_budget_bytes,
            batch_size=cfg.batch_size,
            retention_days=cfg.retention_days,
            max_detail_bytes=cfg.max_detail_bytes,
            timeline_limit=cfg.timeline_limit,
            templates=lambda: load_dashboard_templates(templates_dir),
            on_ingested=on_ingested,
            archive_max_events=cfg.archive_max_events,
            archive_max_bytes=cfg.archive_max_bytes,
            session_title_rules=cfg.title_rules(),
            base_taxonomy=base_taxonomy_of(cfg.base_taxonomy_file, base),
            scope_kinds=lambda: ctx.ports(LOG_SCOPE_KINDS),
            filter_predicates=lambda: ctx.ports(LOG_FILTER_PREDICATES),
            projects=project_folders,
        )
        runtime_problems: list[Issue] = []

        def warnings() -> list[Issue]:
            out: list[Issue] = []
            if storage.kind == "memory":
                out.append(storage_memory_warning())
            if not redaction.available and redaction.wanted():
                out.append(redaction_unavailable_warning())
            out.extend(runtime_problems)
            try:
                out.extend(service.source_issues())
            except Exception:  # 설정을 읽지 못해도 서버 정보는 답한다
                _log.exception("로그 출처 상태를 읽지 못했습니다")
            return out

        ctx.provide(LOGS_QUERY, service)
        ctx.provide(LOGS_INGEST, service)
        ctx.provide(SERVER_WARNINGS, warnings)

        async def start() -> None:
            for item in ctx.ports(LOG_SOURCES):
                try:
                    service.add_runtime_source(item.source, classifier=item.classifier)
                except (ValueError, AttributeError) as exc:
                    sid = getattr(
                        getattr(getattr(item, "source", None), "descriptor", None), "id", "?"
                    )
                    _log.warning("런타임 로그 출처 %s를 붙이지 못했습니다: %s", sid, exc)
                    runtime_problems.append(
                        Issue(
                            severity="warning",
                            code=KnownIssueCodes.LOGS_SOURCE_FAILED,
                            message=f"런타임 로그 출처 {sid}를 붙이지 못했습니다(id 겹침 등)",
                            details={
                                "source": str(sid),
                                "error_code": "logs.runtime_source_rejected",
                            },
                        )
                    )
            service.start()

        async def stop() -> None:
            await service.stop()
            storage.close()

        background: list[Callable[[], Awaitable[None]]] = []
        if cfg.startup_scan or cfg.scan_interval_seconds > 0:
            interval, startup = cfg.scan_interval_seconds, cfg.startup_scan
            background.append(lambda: service.run_periodic(interval, startup=startup))

        return ModuleParts(
            routers=[
                build_router(
                    lambda: service,
                    archive_file_prefix=cfg.archive_file_prefix,
                    archive_title=cfg.archive_title,
                )
            ],
            ws_topics=topic_handlers(hub=hub),
            error_map=dict(ERROR_MAP),
            startup=[start],
            shutdown=[stop],
            background=background,
        )


module = LogsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "MODULE_ID",
    "WEB_ROLES",
    "LogsModule",
    "base_taxonomy_of",
    "log_registries_of",
    "module",
    "redaction_unavailable_warning",
    "storage_memory_warning",
]
