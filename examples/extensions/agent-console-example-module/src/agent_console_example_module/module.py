"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-example-notes``).

서버 모듈 하나가 갖추는 것을 한 파일에 모았다.

- 서술자(``ModuleDescriptor``): id·제목·설명, 제공·선택 포트, 설치자 옵션 스키마, 설정 호환 선언
  (명령행 옵션), 마이그레이션 계보(``scopes=("app", "project")``), 웹 역할.
- ``build(ctx)``: 설정을 읽고 서비스를 만들고 포트를 제공한 뒤 서버에 붙일 부분(라우터·오류 맵)을
  돌려준다. 전역 상태 없음 — 모듈 객체 하나로 여러 앱을 조립해도 서로 섞이지 않는다.

필수 포트가 없어 혼자 켜진다. 선택 포트가 없으면 그 동작만 409 ``feature_unavailable``이다. 모듈을
끄면(``modules.disabled``) 경로가 아예 붙지 않아 404이고, 다른 모듈은 그대로 동작한다.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sqlalchemy import Engine

from agent_console_contracts import Issue
from agent_console_modkit import KindContribution, ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_store import DefinitionKind

from .models import NoteTemplate
from .ports import (
    DEFINITIONS_LOOKUP,
    KIND_CONTRIBUTIONS,
    NOTES_READER,
    RECORDS_SPACES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .service import (
    MODULE_ID,
    NoteNotFoundError,
    NoteRejectedError,
    NotesDeps,
    NotesService,
    TemplateNotFoundError,
)
from .settings import SETTINGS_COMPAT, NotesModuleSettings
from .storage import BRANCH, memory_engine

STORAGE_MEMORY = "example_notes.storage_memory"
"""DB가 없어 앱 노트를 메모리에만 둔다는 경고 코드."""

WEB_ROLES: tuple[str, ...] = ("example-notes",)
"""웹 라우트 역할(이 역할을 요구하는 화면은 모듈이 켜졌을 때만 보인다). 이 예제는 화면이 없다."""


def _version() -> str:
    try:
        return version("agent-console-example-module")
    except PackageNotFoundError:  # 설치 없이 소스로 실행(예제 테스트)
        return "0.0.0"


def template_kind(options: NotesModuleSettings) -> DefinitionKind:
    """기여할 정의 종류(이름·폴더는 설치자 옵션). 라이브러리·프로젝트 공간 모두에 둘 수 있다."""
    return DefinitionKind(
        name=options.template_kind, directory=options.template_dir, model=NoteTemplate
    )


class NotesModule:
    """노트 예제 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="노트(예제)",
        description="짧은 노트를 적고 읽는다",
        provides=(NOTES_READER, KIND_CONTRIBUTIONS, SERVER_WARNINGS),
        optional=(WORKSPACE_SETTINGS, DEFINITIONS_LOOKUP, RECORDS_SPACES),
        settings_schema=NotesModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings if isinstance(ctx.settings, NotesModuleSettings) else None
        options = cfg or NotesModuleSettings()
        database = ctx.database

        def app_engine() -> Engine:
            # 호스트 DB가 있으면 호스트가 이 모듈의 계보를 이미 올렸다(켜질 때, build 직전).
            return database.engine if database is not None else memory_engine()

        def workspace_settings() -> Any:
            reader = ctx.port(WORKSPACE_SETTINGS)
            return reader() if reader is not None else None

        service = NotesService(
            options,
            NotesDeps(
                app_engine=app_engine,
                records=lambda: ctx.port(RECORDS_SPACES),
                templates=lambda: ctx.port(DEFINITIONS_LOOKUP),
                workspace_settings=workspace_settings,
                clock=ctx.clock,
            ),
        )

        def warnings() -> list[Issue]:
            found = service.warnings()
            if database is None:
                found.append(
                    Issue(
                        severity="info",
                        code=STORAGE_MEMORY,
                        message="DB가 없어 앱 노트를 메모리에만 둡니다(재시작하면 사라집니다)",
                    )
                )
            return found

        ctx.provide(NOTES_READER, service)
        ctx.provide(
            KIND_CONTRIBUTIONS,
            KindContribution(template_kind(options), summary_fields=("category",)),
        )
        ctx.provide(SERVER_WARNINGS, warnings)
        return ModuleParts(
            routers=[build_router(service, options.route)],
            error_map={
                NoteNotFoundError: "not_found",
                TemplateNotFoundError: "not_found",
                NoteRejectedError: "validation_failed",
            },
        )


module = NotesModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["STORAGE_MEMORY", "WEB_ROLES", "NotesModule", "module", "template_kind"]
