"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-sdd``, design §6R.3).

- 제공: ``sdd.service``(스펙 서비스), ``definitions.kind_contributions``(정의 종류 두 개 — 문서 틀
  library·portable + 참조 추출, 스펙 library=False·portable), ``server.warnings``(사용자 설정
  ``sdd`` 섹션 형식 문제). 필수 포트 없음(혼자 켜진다).
- 선택: ``workspace.settings``·``secrets.rules``·``definitions.store``(라이브러리 문서 틀)·
  ``sdd.spaces``(공간)·``sdd.integrations``(X43, 여러 제공자)·``sdd.verification_sources``(X42, 여러
  제공자). 없으면 그 부분만 꺼진다(``SddInfo.capabilities``가 포트 유무로 알린다).
- 경로: ``/sdd/*``(``routes``). WS 토픽 ``sdd.changed``. 토픽 ``definitions.saved``(스펙 종류)를
  받아 다른 길로 저장된 스펙도 알린다.
- 저장: 공간 이름이 없는 요청은 단독 루트(설치자 옵션 ``standalone_root``, 기본 워크스페이스 안
  패키지 데이터 폴더 이름)의 정의 저장소. 버전 기록은 호스트 DB(legacy 표, 없으면 메모리). 폴더는
  처음 쓸 때 만든다.
- 검증 출처 플러그인(X42): 호스트 묶음의 ``sdd_verification_sources``
  확장(``plugins.load_plugins``가
  채운다). 사용자 설정 ``sdd.verification_sources``로 켠다.
- 실행·프로젝트를 모른다. 실행 연동은 ``link-runs-sdd``, 프로젝트 공간은 ``link-projects-sdd``가
  준다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agent_console_conditions import (
    CONDITION_OPERATORS_EXTENSION,
    ConditionOperator,
    as_condition_operator,
    default_operators,
    load_condition_operators,
    operator_map,
)
from agent_console_contracts import CONTRACT_VERSIONS, Issue
from agent_console_contracts.sdd import SddChanged
from agent_console_modkit import (
    KindContribution,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
    Topic,
)
from agent_console_modkit.host import is_loopback_host
from agent_console_registry import Registry
from agent_console_sdd import definition_kinds
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import (
    DEFAULT_MAX_CONTENT_BYTES,
    GRAPH_KIND,
    DefinitionKind,
    FileDefinitionStore,
    LazyVersionRepository,
    versions_for,
)

from .errors import ERROR_MAP
from .plugins import plugin_sources, source_registry
from .ports import (
    DEFINITIONS_STORE,
    KIND_CONTRIBUTIONS,
    SDD_INTEGRATIONS,
    SDD_SERVICE,
    SDD_SPACES,
    SDD_VERIFICATION_SOURCES,
    SECRET_RULES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .secrets import SecretRejectedError, document_issues
from .service import SddPorts, SddService
from .settings import SETTINGS_COMPAT, SddModuleSettings, package_defaults
from .ws import SDD_TOPIC, ChangePublisher, changed_message, topic_handlers

MODULE_ID = "mod-sdd"
WEB_ROLES: tuple[str, ...] = ("sdd",)
"""웹 라우트 역할. 웹의 스펙 화면·문서 틀 화면·설정 "스펙" 섹션 데이터가 이 역할을 요구한다(모듈이
없으면 화면·섹션 없음)."""

DEFAULT_WORKSPACE = Path(".agent-console")
"""호스트가 경로를 주지 않을 때(테스트 등) 쓰는 워크스페이스 폴더."""

SPEC_KIND_TITLE = "스펙"
"""스펙 정의 종류의 표시 이름(종류 기여 ``title`` → 복사 대화상자 ``CopyKindInfo.title``)."""

TEMPLATE_KIND_TITLE = "문서 틀"
"""문서 틀 정의 종류의 표시 이름(종류 기여 ``title``)."""

DEFINITIONS_SAVED: Topic[Any] = Topic("definitions.saved")
"""정의 저장 알림 토픽(정의·프로젝트 모듈이 낸다, 항목 ``{kind, id, version_hash, space}``)."""


def _version() -> str:
    try:
        return version("agent-console-mod-sdd")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def operators_of(registries: Any) -> Callable[[], Mapping[str, ConditionOperator]]:
    """조건 연산자를 돌려주는 함수(호스트 묶음이 있으면 그 확장, 없으면 설치된 연산자 한 번)."""
    extension = getattr(registries, "extension", None)
    if callable(extension):
        registry: Registry[ConditionOperator] = extension(
            CONDITION_OPERATORS_EXTENSION, validator=as_condition_operator
        )
        if not registry.list():
            load_condition_operators(registry)
        return lambda: operator_map(registry)
    found, _reports = default_operators()
    return lambda: found


def template_references(document: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """문서 틀·스펙이 쓰는 정의(실행 프로필의 팀 구성 id) — 복사 계획의 참조 닫힘(X25와 같은 뜻)."""
    rules = document.get("rules")
    profiles = rules.get("run_profiles") if isinstance(rules, Mapping) else None
    out: list[tuple[str, str]] = []
    for profile in profiles if isinstance(profiles, list) else ():
        graph = profile.get("graph") if isinstance(profile, Mapping) else None
        if isinstance(graph, str) and graph and (GRAPH_KIND.name, graph) not in out:
            out.append((GRAPH_KIND.name, graph))
    return out


def open_versions(database: Any | None) -> Any:
    """단독 저장소의 버전 기록소. 처음 쓸 때 legacy 계보(정의 버전 표)를 올리고(멱등) 연다 — 스펙을
    쓰지 않으면 DB 파일을 만들지 않는다. DB가 없으면 메모리."""
    if database is not None:
        database.upgrade()
    return versions_for(database)


def standalone_root(cfg: SddModuleSettings, ctx: ModuleContext) -> Path:
    """단독 루트 폴더(옵션 → 없으면 워크스페이스 안 패키지 데이터 폴더 이름)."""
    paths = ctx.paths
    if cfg.standalone_root is not None:
        root = cfg.standalone_root.expanduser()
        if root.is_absolute() or paths is None:
            return root
        return paths.base_dir / root
    workspace = paths.workspace if paths is not None else DEFAULT_WORKSPACE
    return workspace / str(package_defaults()["standalone_dir"])


def yaml_guard(rules: Callable[[], SecretRules]) -> Callable[..., None]:
    """단독 저장소 쓰기 전 검사: 정의 YAML에 비밀 의심 값이 있으면 거부(본문은 설정
    ``secret_scan``)."""

    def guard(
        kind: DefinitionKind, id: str, document: Mapping[str, Any], put: Mapping[str, bytes]
    ) -> None:
        found = document_issues(rules(), document)
        if found:
            raise SecretRejectedError(found)

    return guard


class SddModule:
    """스펙(SDD) 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="스펙",
        description="스펙 문서를 쓰고 작업 목록·계획·추적 표로 본다",
        provides=(SDD_SERVICE, KIND_CONTRIBUTIONS, SERVER_WARNINGS),
        optional=(
            WORKSPACE_SETTINGS,
            SECRET_RULES,
            DEFINITIONS_STORE,
            SDD_SPACES,
            SDD_INTEGRATIONS,
            SDD_VERIFICATION_SOURCES,
        ),
        settings_schema=SddModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"sdd": CONTRACT_VERSIONS["sdd"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, SddModuleSettings):
            cfg = SddModuleSettings()
        kinds = definition_kinds(
            spec_kind=cfg.spec_kind,
            spec_directory=cfg.spec_dir,
            template_kind=cfg.template_kind,
            template_directory=cfg.template_dir,
        )

        def secret_rules() -> SecretRules:
            reader = ctx.port(SECRET_RULES)
            try:
                found = reader() if reader is not None else None
            except Exception:
                found = None
            return found if isinstance(found, SecretRules) else default_rules()

        store = FileDefinitionStore(
            standalone_root(cfg, ctx),
            kinds,
            versions=LazyVersionRepository(lambda: open_versions(ctx.database)),
            max_content_bytes=DEFAULT_MAX_CONTENT_BYTES,
            write_guard=yaml_guard(secret_rules),
        )
        hub: Any = ctx.ws_hub

        def publish(payload: SddChanged) -> None:
            hub.publish(SDD_TOPIC, changed_message(payload))

        publisher = ChangePublisher(publish)
        registry = source_registry(ctx.registries)

        def workspace_settings() -> Any:
            reader = ctx.port(WORKSPACE_SETTINGS)
            return reader() if reader is not None else None

        server_host = cfg.server_host or "127.0.0.1"

        def loopback() -> bool:
            return is_loopback_host(server_host)

        service = SddService(
            cfg,
            standalone=store,
            kinds=kinds,
            ports=SddPorts(
                spaces=lambda: ctx.port(SDD_SPACES),
                library=lambda: ctx.port(DEFINITIONS_STORE),
                integrations=lambda: ctx.ports(SDD_INTEGRATIONS),
                sources=lambda: ctx.ports(SDD_VERIFICATION_SOURCES),
                plugin_sources=lambda: plugin_sources(registry),
                workspace_settings=workspace_settings,
                secret_rules=secret_rules,
                operators=operators_of(ctx.registries),
                publish=publisher,
                loopback=loopback,
            ),
            standalone_max_bytes=DEFAULT_MAX_CONTENT_BYTES,
        )

        spec_kind, template_kind = kinds
        ctx.provide(SDD_SERVICE, service)
        ctx.provide(
            KIND_CONTRIBUTIONS,
            KindContribution(
                template_kind, references=template_references, title=TEMPLATE_KIND_TITLE
            ),
        )
        ctx.provide(
            KIND_CONTRIBUTIONS,
            KindContribution(spec_kind, references=template_references, title=SPEC_KIND_TITLE),
        )

        def warnings() -> list[Issue]:
            return service.warnings()

        ctx.provide(SERVER_WARNINGS, warnings)
        ctx.subscribe(DEFINITIONS_SAVED, service.on_saved)

        async def start() -> None:
            publisher.bind(asyncio.get_running_loop())

        async def stop() -> None:
            publisher.bind(None)

        return ModuleParts(
            routers=[build_router(lambda: service)],
            ws_topics=topic_handlers(hub=hub),
            error_map=dict(ERROR_MAP),
            startup=[start],
            shutdown=[stop],
            label_display=[
                d.model_dump(mode="json", exclude_none=True) for d in service.label_display()
            ],
        )


module = SddModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_WORKSPACE",
    "MODULE_ID",
    "WEB_ROLES",
    "SddModule",
    "module",
    "operators_of",
    "standalone_root",
    "template_references",
]
