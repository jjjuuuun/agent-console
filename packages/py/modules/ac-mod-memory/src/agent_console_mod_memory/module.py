"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-memory``, design §5.7R.2).

- 제공: ``memory.service``(저장소·범위 종류·설정·도구 묶음), ``server.warnings``(저장소 메모리
  모드·전문 검색 폴백·저장된 ``memory`` 섹션 문제). 필수 포트 없음(혼자 켜진다).
- 선택: ``workspace.settings``(사용자 설정 ``memory`` 섹션). 없으면 기본값.
- 선택: ``memory.spaces``(5.7R.33z, 공간 이름 → 저장소). 있으면 REST ``?project=<id>``와
  ``POST /memory/copy``가 그 공간을 쓰고, ``memory.service``의 ``space(name)``이 공간 서비스를 준다.
  없으면 공간 이름이 온 요청은 409 ``feature_unavailable``(라이브러리만).
- 경로: ``/memory/*``(범위 종류·범위·태그·항목 CRUD·버전·정리·설정 검사·내보내기/가져오기).
  WS 토픽 ``memory.changed``.
- 저장: 계보 ``memory``(``storage.BRANCH``)는 모듈이 켜질 때만 호스트가 올린다.
  옵션 ``store_path``면 그 파일에 같은 계보를 올리고, 없으면 호스트 DB 파일, DB가 없으면 메모리(경고
  ``memory.storage_memory``).
- 정리 스케줄: ``retention_interval_seconds``마다 저장된 정리 규칙을 적용한다(0 = 끔, 규칙이 없으면
  아무것도 하지 않는다). 대상은 사용자 설정 ``memory.retention.auto``(공용, 그리고
  ``memory.spaces`` 제공자의 선택 메서드 ``existing()``이 준 공간 — 5.7R.46). 제공자가 없으면
  공용만.
- 범위 종류 플러그인(X29): 호스트 묶음의 ``memory_scope_kinds`` 확장(``plugins.load_plugins``가
  채운다). 묶음이 없으면(단독 실행) entry point에서 직접 읽는다.
- 조건 연산자(X22, 정리 규칙): 호스트 묶음의 ``condition_operators`` 확장(비어 있으면 설치된
  연산자로 채운다). 묶음이 없으면 새로 읽는다.
- 실행·로그를 모른다. 에이전트 도구는 실행 연동(``link-memory-runs``)이 ``memory.service``로 만든다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
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
from agent_console_contracts.memory import MemoryChanged
from agent_console_memory import MemoryPolicy, MemoryStore, QueryHasher, query_hasher_from_env
from agent_console_modkit import (
    DEFAULT_WORK_WAIT,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
    WorkGate,
)
from agent_console_registry import Registry

from .config import section_of
from .errors import ERROR_MAP
from .plugins import plugin_kinds, scope_kind_registry
from .ports import MEMORY_SERVICE, MEMORY_SPACES, SERVER_WARNINGS, WORKSPACE_SETTINGS
from .retention import RetentionCycleResult, run_retention_cycle
from .routes import build_router
from .service import MemoryService
from .settings import MemoryModuleSettings
from .spaces import MemorySpaceServices
from .storage import BRANCH, open_memory_storage
from .ws import MEMORY_TOPIC, LoopPublisher, changed_message, topic_handlers

MODULE_ID = "mod-memory"
WEB_ROLES: tuple[str, ...] = ("memory",)
"""웹 라우트 역할. 웹의 메모리 화면·사이드바 항목·설정 "메모리" 섹션 데이터가 이 역할을 요구한다
(모듈이 없으면 화면·섹션 없음)."""

_log = logging.getLogger("agent_console_mod_memory")


def _version() -> str:
    try:
        return version("agent-console-mod-memory")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def _resolve(path: Path | None, base: Path | None) -> Path | None:
    if path is None:
        return None
    path = path.expanduser()
    if path.is_absolute() or base is None:
        return path
    return base / path


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


async def run_retention_periodically(
    service: MemoryService,
    interval: float,
    *,
    gate: WorkGate | None = None,
    stop_wait: float = DEFAULT_WORK_WAIT,
) -> None:
    """``interval``초마다 자동 정리 한 주기(``run_retention_cycle``)를 돈다.

    대상은 사용자 설정 ``memory.retention.auto``(공용 → 메모리가 있는 공간). 규칙이 없으면 아무것도
    열지 않고, 공간마다 실패는 로그만 남기고 건너뛴다. 한 주기가 끝나야 다음 주기를 기다린다(동시에
    두 번 돌지 않음).

    취소되면(서버 종료) ``gate``를 닫아 남은 공간을 하지 않게 하고(빈·부분 결과), 하던 공간이
    끝나기를 최대 ``stop_wait``초 기다린 뒤 취소를 다시 던진다. 조립기는 종료 훅보다 배경 작업
    취소를 먼저 하므로, 메모리 공간 풀·저장소가 닫히기 전에 정리 스레드가 끝난다.
    """
    work = gate if gate is not None else WorkGate()

    def cycle() -> RetentionCycleResult:
        return run_retention_cycle(service, should_stop=lambda: work.closed)

    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(work.run, cycle, RetentionCycleResult)
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("Memory auto-cleanup failed")
    except asyncio.CancelledError:
        if not await work.close_and_wait(stop_wait):
            _log.warning(
                "The memory auto-cleanup thread didn't finish within %.0f seconds", stop_wait
            )
        raise


def search_query_hasher(cfg: MemoryModuleSettings, environ: Mapping[str, str]) -> QueryHasher:
    """설치자 설정 → 검색어 해셔(``query_hash``, 솔트는 ``query_hash_salt_env`` 환경변수).

    솔트 값은 로그·응답에 내지 않는다. 변수가 없거나 비면 무작위 솔트(서버를 켤 때마다 바뀐다).
    """
    return query_hasher_from_env(cfg.query_hash, salt_env=cfg.query_hash_salt_env, environ=environ)


class MemoryModule:
    """공유 메모리 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="공유 메모리",
        description="에이전트가 함께 쓰는 메모리를 기록·검색·정리한다",
        provides=(MEMORY_SERVICE, SERVER_WARNINGS),
        optional=(WORKSPACE_SETTINGS, MEMORY_SPACES),
        settings_schema=MemoryModuleSettings,
        contracts={"memory": CONTRACT_VERSIONS["memory"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, MemoryModuleSettings):
            cfg = MemoryModuleSettings()
        paths = ctx.paths
        base = paths.base_dir if paths is not None else None
        clock = ctx.clock

        def now() -> float:
            return clock().timestamp()

        storage = open_memory_storage(
            ctx.database,
            store_path=_resolve(cfg.store_path, base),
            policy=MemoryPolicy(limits=cfg.limits()),
            use_fts=cfg.full_text_search,
            busy_timeout_seconds=cfg.busy_timeout_seconds,
            clock=now,
        )
        registry = scope_kind_registry(ctx.registries)
        hub: Any = ctx.ws_hub

        def publish(payload: MemoryChanged) -> None:
            hub.publish(MEMORY_TOPIC, changed_message(payload))

        publisher = LoopPublisher(publish)

        def user_section() -> Any:
            # 부를 때 포트를 찾는다(설정 제공 모듈이 이 모듈보다 늦게 만들어질 수 있다).
            reader = ctx.port(WORKSPACE_SETTINGS)
            return section_of(reader()) if reader is not None else None

        spaces_ref: list[MemorySpaceServices] = []
        # 검색어 해셔는 프로세스 하나에 하나(라이브러리·공간 서비스가 같은 솔트를 쓴다)
        hasher = search_query_hasher(cfg, ctx.environ)

        def make_service(
            store: MemoryStore,
            context: Mapping[str, str] | None = None,
            name: str | None = None,
        ) -> MemoryService:
            return MemoryService(
                store,
                section=user_section,
                plugins=lambda: plugin_kinds(registry),
                operators=operators_of(ctx.registries),
                limits=cfg.limits(),
                transfer_limits=cfg.transfer_limits(),
                on_change=publisher,
                clock=now,
                max_page_size=cfg.max_page_size,
                max_tag_list=cfg.max_tag_list,
                max_search_results=cfg.max_search_results,
                query_hash=hasher,
                context_overrides=context,
                spaces=spaces_ref[0] if spaces_ref else None,
                space_name=name,
            )

        spaces = MemorySpaceServices(
            lambda: ctx.port(MEMORY_SPACES),
            lambda store, context: make_service(store, context),
        )
        spaces_ref.append(spaces)
        service = make_service(storage.store)
        spaces.library = service

        def warnings() -> list[Issue]:
            out = list(storage.warnings())
            try:
                out.extend(service.warnings())
            except Exception:  # 설정을 읽지 못해도 서버 정보는 답한다
                _log.exception("Couldn't read memory settings problems")
            return out

        ctx.provide(MEMORY_SERVICE, service)
        ctx.provide(SERVER_WARNINGS, warnings)

        retention_gate = WorkGate()

        async def start() -> None:
            retention_gate.reopen()
            publisher.bind(asyncio.get_running_loop())

        async def stop() -> None:
            # 정리 스레드가 저장소를 쓰는 동안 닫지 않는다
            if not await retention_gate.close_and_wait():
                _log.warning(
                    "Closing the store while the memory auto-cleanup thread is still running"
                )
            publisher.bind(None)
            storage.close()

        background: list[Callable[[], Awaitable[None]]] = []
        if cfg.retention_interval_seconds > 0:
            interval = cfg.retention_interval_seconds
            background.append(
                lambda: run_retention_periodically(service, interval, gate=retention_gate)
            )

        return ModuleParts(
            routers=[build_router(lambda: service)],
            ws_topics=topic_handlers(hub=hub),
            error_map=dict(ERROR_MAP),
            startup=[start],
            shutdown=[stop],
            background=background,
        )


module = MemoryModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = [
    "MODULE_ID",
    "WEB_ROLES",
    "MemoryModule",
    "module",
    "operators_of",
    "run_retention_periodically",
    "search_query_hasher",
]
