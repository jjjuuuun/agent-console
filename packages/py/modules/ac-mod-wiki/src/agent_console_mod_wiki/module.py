"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-wiki``, design §7R.3).

- 제공: ``wiki.service``(위키 서비스), ``definitions.kind_contributions``(정의 종류 두 개 — 위키
  규칙 library·portable·여러 본문 파일, 위키 library=False·portable + 참조 추출 ``rules``),
  ``server.warnings``(사용자 설정 ``wiki`` 섹션 형식 문제·없는 쓰기 검사). 필수 포트 없음(혼자
  켜진다).
- 선택: ``workspace.settings``·``secrets.rules``·``definitions.store``(라이브러리 위키 규칙)·
  ``wiki.spaces``(공간)·``records.spaces``(프로젝트 기록 DB)·``wiki.write_checks``(X50, 여러
  제공자)·``wiki.integrations``(능력 선언, 여러 제공자). 없으면 그 부분만 꺼진다
  (``WikiInfo.capabilities``가 포트 유무로 알린다).
- 경로: ``/wiki/*``(``routes``·``rules_routes``). WS 토픽 ``wiki.changed``(키트 ``LoopPublisher``).
- 저장: 공간 이름이 없는 요청은 단독 루트(설치자 옵션 ``standalone_root``, 기본 워크스페이스 안
  패키지 데이터 폴더 이름)의 정의 저장소·페이지 폴더. 페이지 기록은 계보 ``wiki``(호스트 DB, 없으면
  메모리), 검색 색인은 호스트 상태 폴더. 폴더·파일은 처음 쓸 때 만든다(빈 workspace에서 위키 0개).
- 플러그인: 검색 색인(X48)·쓰기 검사(X50) — ``plugins.load_plugins``가 호스트 묶음에 채운다.
- 주기 일: 시작할 때 단독 공간 위키의 검색 색인을 맞추고, ``scan_interval_seconds``가 0보다 크면 그
  주기로 열어 둔 위키의 외부 변경을 기록한다.
- 실행·프로젝트를 모른다. 프로젝트 공간은 ``link-projects-wiki``, 에이전트 도구는
  ``link-wiki-runs``가 준다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
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
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiChanged, WikiIssue
from agent_console_modkit import (
    KindContribution,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
)
from agent_console_registry import Registry
from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import (
    DEFAULT_MAX_CONTENT_BYTES,
    DefinitionKind,
    FileDefinitionStore,
    LazyVersionRepository,
    versions_for,
)
from agent_console_wiki import WikiSecretRejectedError, definition_kinds

from .errors import ERROR_MAP
from .history import BRANCH, open_host_history
from .plugins import search_registry, write_check_registry
from .ports import (
    DEFINITIONS_STORE,
    KIND_CONTRIBUTIONS,
    RECORDS_SPACES,
    SECRET_RULES,
    SERVER_WARNINGS,
    WIKI_INTEGRATIONS,
    WIKI_SERVICE,
    WIKI_SPACES,
    WIKI_WRITE_CHECKS,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .service import WikiPorts, WikiService
from .settings import SETTINGS_COMPAT, WikiModuleSettings, package_defaults
from .ws import WIKI_TOPIC, change_publisher, changed_message, topic_handlers

MODULE_ID = "mod-wiki"
WEB_ROLES: tuple[str, ...] = ("wiki", "wiki:rules")
"""웹 라우트 역할. 웹의 위키 화면(``wiki``)·공용 구성 위키 규칙 화면(``wiki:rules``)·설정 "위키"
섹션 데이터가 이 역할을 요구한다(모듈이 없으면 화면·섹션 없음)."""

DEFAULT_WORKSPACE = Path(".agent-console")
"""호스트가 경로를 주지 않을 때(테스트 등) 쓰는 워크스페이스 폴더."""

_log = logging.getLogger("agent_console_mod_wiki")


def _version() -> str:
    try:
        return version("agent-console-mod-wiki")
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


def wiki_references(rules_kind: str) -> Callable[[Mapping[str, Any]], Iterable[tuple[str, str]]]:
    """위키 정의가 쓰는 정의(``rules`` → 위키 규칙 종류) — 복사 계획의 참조 닫힘(X44)."""

    def references(document: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
        rules = document.get("rules")
        out: list[tuple[str, str]] = []
        for rule_id in rules if isinstance(rules, list) else ():
            if isinstance(rule_id, str) and rule_id and (rules_kind, rule_id) not in out:
                out.append((rules_kind, rule_id))
        return out

    return references


def open_versions(database: Any | None) -> Any:
    """단독 저장소의 정의 버전 기록소(처음 쓸 때 legacy 계보를 올림). DB가 없으면 메모리."""
    if database is not None:
        database.upgrade()
    return versions_for(database)


def _resolve(path: Path, base: Path | None) -> Path:
    path = path.expanduser()
    if path.is_absolute() or base is None:
        return path
    return base / path


def standalone_root(cfg: WikiModuleSettings, ctx: ModuleContext) -> Path:
    """단독 루트 폴더(옵션 → 없으면 워크스페이스 안 패키지 데이터 폴더 이름)."""
    paths = ctx.paths
    if cfg.standalone_root is not None:
        return _resolve(cfg.standalone_root, paths.base_dir if paths is not None else None)
    workspace = paths.workspace if paths is not None else DEFAULT_WORKSPACE
    return workspace / str(package_defaults()["standalone_dir"])


def standalone_index_dir(ctx: ModuleContext) -> Path | None:
    """단독 공간 검색 색인 폴더(호스트 상태 폴더 안, 경로가 없으면 메모리)."""
    paths = ctx.paths
    if paths is None:
        return None
    return paths.state / str(package_defaults()["index_dir"])


def yaml_guard(rules: Callable[[], SecretRules]) -> Callable[..., None]:
    """단독 저장소 쓰기 전 검사: 정의 YAML에 비밀 의심 값이 있으면 거부.

    422 ``wiki.secret_rejected``(값 없이 위치만)."""

    def guard(
        kind: DefinitionKind, id: str, document: Mapping[str, Any], put: Mapping[str, bytes]
    ) -> None:
        found = rules().find_suspected(dict(document))
        if found:
            raise WikiSecretRejectedError(
                [],
                issues=[
                    WikiIssue(
                        severity="error",
                        code=KnownIssueCodes.WIKI_SECRET_REJECTED,
                        message="비밀로 보이는 값이 있습니다(값은 보이지 않습니다).",
                        path=f.path or "/",
                        details={"reason": f.reason},
                    )
                    for f in found
                ],
            )

    return guard


async def scan_periodically(service: WikiService, interval: float) -> None:
    """``interval``초마다 열어 둔 위키의 외부 변경을 기록한다(실패는 로그만)."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(service.scan_opened)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("위키 외부 변경 확인 실패")


async def open_standalone_once(service: WikiService) -> None:
    """시작할 때 한 번: 단독 공간 위키의 검색 색인을 맞춘다(실패는 로그만)."""
    try:
        await asyncio.to_thread(service.open_standalone)
    except asyncio.CancelledError:
        raise
    except Exception:
        _log.exception("위키 검색 색인 준비 실패")


class WikiModule:
    """위키 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="위키",
        description="서로 링크된 마크다운 페이지를 보고 고치고 링크 관계·기록을 본다",
        provides=(WIKI_SERVICE, KIND_CONTRIBUTIONS, SERVER_WARNINGS),
        optional=(
            WORKSPACE_SETTINGS,
            SECRET_RULES,
            DEFINITIONS_STORE,
            WIKI_SPACES,
            RECORDS_SPACES,
            WIKI_WRITE_CHECKS,
            WIKI_INTEGRATIONS,
        ),
        settings_schema=WikiModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"wiki": CONTRACT_VERSIONS["wiki"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, WikiModuleSettings):
            cfg = WikiModuleSettings()
        kinds = definition_kinds(
            wiki_kind=cfg.wiki_kind,
            wiki_dir=cfg.wiki_dir,
            rules_kind=cfg.rules_kind,
            rules_dir=cfg.rules_dir,
            summary_fields=("description",),
        )
        wiki_kind, rules_kind = kinds

        def secret_rules() -> SecretRules:
            reader = ctx.port(SECRET_RULES)
            try:
                found = reader() if reader is not None else None
            except Exception:
                found = None
            return found if isinstance(found, SecretRules) else default_rules()

        root = standalone_root(cfg, ctx)
        store = FileDefinitionStore(
            root,
            kinds,
            versions=LazyVersionRepository(lambda: open_versions(ctx.database)),
            max_content_bytes=DEFAULT_MAX_CONTENT_BYTES,
            write_guard=yaml_guard(secret_rules),
        )
        history, _kind = open_host_history(ctx.database)
        hub: Any = ctx.ws_hub

        def publish(payload: WikiChanged) -> None:
            hub.publish(WIKI_TOPIC, changed_message(payload))

        publisher = change_publisher(publish)
        clock = ctx.clock

        def now() -> float:
            return clock().timestamp()

        def workspace_settings() -> Any:
            reader = ctx.port(WORKSPACE_SETTINGS)
            return reader() if reader is not None else None

        service = WikiService(
            cfg,
            standalone=store,
            kinds=kinds,
            standalone_pages=root / cfg.pages_dir,
            standalone_index=standalone_index_dir(ctx),
            host_history=history,
            search=search_registry(ctx.registries),
            write_check_plugins=write_check_registry(ctx.registries),
            ports=WikiPorts(
                spaces=lambda: ctx.port(WIKI_SPACES),
                records=lambda: ctx.port(RECORDS_SPACES),
                library=lambda: ctx.port(DEFINITIONS_STORE),
                write_checks=lambda: ctx.ports(WIKI_WRITE_CHECKS),
                integrations=lambda: ctx.ports(WIKI_INTEGRATIONS),
                workspace_settings=workspace_settings,
                secret_rules=secret_rules,
                operators=operators_of(ctx.registries),
                publish=publisher,
            ),
            clock=now,
        )

        ctx.provide(WIKI_SERVICE, service)
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(rules_kind))
        ctx.provide(
            KIND_CONTRIBUTIONS,
            KindContribution(wiki_kind, references=wiki_references(rules_kind.name)),
        )

        def warnings() -> list[Issue]:
            try:
                return service.warnings()
            except Exception:  # 설정을 읽지 못해도 서버 정보는 답한다
                _log.exception("위키 설정 문제를 읽지 못했습니다")
                return []

        ctx.provide(SERVER_WARNINGS, warnings)

        async def start() -> None:
            publisher.bind(asyncio.get_running_loop())

        async def stop() -> None:
            publisher.bind(None)
            await asyncio.to_thread(service.close)

        background: list[Callable[[], Awaitable[None]]] = [lambda: open_standalone_once(service)]
        if cfg.scan_interval_seconds > 0:
            interval = cfg.scan_interval_seconds
            background.append(lambda: scan_periodically(service, interval))

        return ModuleParts(
            routers=[build_router(lambda: service)],
            ws_topics=topic_handlers(hub=hub),
            error_map=dict(ERROR_MAP),
            startup=[start],
            shutdown=[stop],
            background=background,
        )


module = WikiModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "DEFAULT_WORKSPACE",
    "MODULE_ID",
    "WEB_ROLES",
    "WikiModule",
    "module",
    "open_standalone_once",
    "operators_of",
    "scan_periodically",
    "standalone_index_dir",
    "standalone_root",
    "wiki_references",
    "yaml_guard",
]
