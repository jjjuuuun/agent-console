"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-definitions``).

- 제공: ``definitions.store``·``definitions.lookup``(같은 저장소)·``workspace.settings``·
  ``secrets.rules``·``definitions.checks``(공통 설정 비밀 규칙 검사)·``server.warnings``(평문 점검).
  토픽 ``definitions.saved``를 낸다(저장마다, 저장소 쓰기 잠금 안 동기 호출, 구독자 예외 격리).
- 선택: ``definitions.checks``(여러 제공자 — 저장 전 검사), ``graphs.validation``·
  ``graphs.entry_labels``(팀 구성 목록의 검증 요약·입구 이름, 없으면 null).
- 저장소: 워크스페이스 폴더(``BaseServices.paths.workspace``)의 YAML. 버전 기록은 호스트 DB 핸들
  (``BaseServices.database``)의 legacy 테이블, 없으면 메모리(``server.warnings``에
  ``definitions.versions_memory`` 경고). 시작 때 legacy 계보를 올리고(멱등)
  평문 점검을 한 번 해 개수를 로그에 남긴다(값은 남기지 않는다).
- 평문 점검 캐시는 ``definitions.saved``(저장)와 삭제 때 버린다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from agent_console_contracts import CONTRACT_VERSIONS, Issue
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import ERROR_MAP
from .plain_scan import PlainSecretScan, scan_store
from .ports import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SAVED,
    DEFINITIONS_STORE,
    GRAPH_ENTRY_LABELS,
    GRAPH_VALIDATION,
    SECRET_RULES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    SavedDefinition,
)
from .routes import build_router
from .service import DefinitionService
from .settings import SETTINGS_COMPAT, DefinitionModuleSettings
from .store import DefinitionFileStore, LazyVersionRepository, build_store, versions_for
from .workspace import SecretRuleCheck, WorkspaceState

MODULE_ID = "mod-definitions"
WEB_ROLES: tuple[str, ...] = ("definitions:agent", "definitions:graph", "settings")
"""웹 라우트 역할(design §3R.1.3 표)."""

DEFAULT_WORKSPACE = Path(".agent-console")
"""호스트가 경로를 주지 않을 때(테스트 등) 쓰는 워크스페이스 폴더."""

VERSIONS_MEMORY = "definitions.versions_memory"
"""경고 코드: DB 핸들이 없어 정의 버전 기록을 메모리에만 둔다(재시작하면 사라진다)."""

_log = logging.getLogger("agent_console_mod_definitions")


def versions_memory_warning() -> Issue:
    return Issue(
        severity="warning",
        code=VERSIONS_MEMORY,
        message="DB가 없어 정의 버전 기록을 메모리에만 둡니다(재시작하면 사라집니다)",
    )


def _version() -> str:
    try:
        return version("agent-console-mod-definitions")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class DefinitionsModule:
    """정의 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="정의",
        description="에이전트·팀 구성·공통 설정 저장소와 CRUD, 워크스페이스 설정·비밀 규칙",
        provides=(
            DEFINITIONS_STORE,
            DEFINITIONS_LOOKUP,
            WORKSPACE_SETTINGS,
            SECRET_RULES,
            DEFINITION_CHECKS,
            SERVER_WARNINGS,
        ),
        optional=(DEFINITION_CHECKS, GRAPH_VALIDATION, GRAPH_ENTRY_LABELS),
        settings_schema=DefinitionModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"definitions": CONTRACT_VERSIONS["definitions"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, DefinitionModuleSettings):
            cfg = DefinitionModuleSettings()
        root = ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE
        scans: list[PlainSecretScan] = []

        def saved(kind: str, item_id: str, version_hash: str) -> None:
            ctx.publish(DEFINITIONS_SAVED, SavedDefinition(kind, item_id, version_hash))

        def deleted(_kind: str, _item_id: str) -> None:
            for scan in scans:
                scan.invalidate()

        store: DefinitionFileStore = build_store(
            root,
            versions=LazyVersionRepository(lambda: versions_for(ctx.database)),
            on_saved=saved,
            on_deleted=deleted,
            max_content_bytes=cfg.max_content_bytes,
        )
        state = WorkspaceState(store)
        codes = frozenset(cfg.plain_secret_issue_codes)
        scan = PlainSecretScan(
            lambda: scan_store(
                store,
                checks=lambda: ctx.ports(DEFINITION_CHECKS),
                rules=state.rules,
                plain_codes=codes,
            )
        )
        scans.append(scan)
        ctx.subscribe(DEFINITIONS_SAVED, lambda _item: scan.invalidate())

        ctx.provide(DEFINITIONS_STORE, store)
        ctx.provide(DEFINITIONS_LOOKUP, store)
        ctx.provide(WORKSPACE_SETTINGS, state.settings)
        ctx.provide(SECRET_RULES, state.rules)
        ctx.provide(DEFINITION_CHECKS, SecretRuleCheck())
        in_memory = ctx.database is None

        def warnings() -> list[Issue]:
            found = list(scan.warnings())
            if in_memory:
                found.append(versions_memory_warning())
            return found

        ctx.provide(SERVER_WARNINGS, warnings)

        service = DefinitionService(
            store,
            checks=lambda: ctx.ports(DEFINITION_CHECKS),
            validation=lambda: ctx.port(GRAPH_VALIDATION),
            entry_labels=lambda: ctx.port(GRAPH_ENTRY_LABELS),
        )
        database = ctx.database

        async def start() -> None:
            root.mkdir(parents=True, exist_ok=True)
            if database is not None:
                await asyncio.to_thread(database.upgrade)  # legacy 계보(정의 버전 표), 멱등
            if len(ctx.ports(DEFINITION_CHECKS)) <= 1:  # 자기 비밀 규칙 검사뿐
                _log.warning(
                    "저장 전 검사(definitions.checks)를 주는 모듈이 없어 리소스 검사 없이 "
                    "저장합니다(모델 검증·비밀 규칙 검사만)"
                )
            found = await asyncio.to_thread(scan.warnings)
            if found:
                _log.warning(
                    "평문 비밀로 의심되는 값 %d곳: GET /server-info warnings 참고", len(found)
                )

        startup: list[Callable[[], Awaitable[None]]] = [start]
        return ModuleParts(
            routers=[build_router(lambda: service)],
            error_map=dict(ERROR_MAP),
            startup=startup,
        )


module = DefinitionsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_WORKSPACE",
    "MODULE_ID",
    "VERSIONS_MEMORY",
    "WEB_ROLES",
    "DefinitionsModule",
    "module",
    "versions_memory_warning",
]
