"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-runs``).

- 제공: ``runs.starter``·``runs.reader``·``runs.events``·``interactions.port``·``secrets.redact``·
  ``server.warnings``·``server.attributes``. 토픽 ``runs.event``(저장된 이벤트마다)·
  ``interactions.updated``. WS ``run:<id>``·``interactions``.
- 필수: ``definitions.lookup``(실행할 팀 구성). 선택: ``runs.preparers``·``runs.services``·
  ``runs.scopes``·``runs.resume_handlers``·``workspace.settings``·``secrets.rules``(``ports.py``).
- 저장: 호스트 DB 핸들의 legacy 테이블(``runs``·``node_runs``·``run_events``·``interactions``),
  없으면 메모리(경고 ``runs.storage_memory``).
- 백엔드 준비 상태·연결 테스트(ux-overhaul §15.8): ``GET /backends/status``·
  ``GET /backends/{id}/status``·``POST /backends/{id}/probe``. 백엔드 선택 능력
  (``status``·``probe``)만 쓰고 id를 모른다. 시간 상한은 설정 ``backend_probe_timeout_max_s``.
- 백엔드 계정 로그인(ux-overhaul §15.9, F14): ``POST /backends/{id}/login``·``…/logout``·
  ``/backends/login/…``. 선택 능력(``login``·``logout``)만 쓰고 id를 모른다. 설정 ``backend_login``
  (``enabled`` 기본 켬, 시간·하트비트·보관·화면 줄 수). 종료 훅에서 진행 중인 세션을 취소한다.
- 조건 연산자(X22): 호스트 묶음의 ``condition_operators`` 레지스트리를 연산자를 쓰는 노드·엣지
  종류에 준다(``bind_condition_operators``), ``GET /condition-operators``가 같은 목록을 낸다.
- 관측 탭 이벤트 접두어(5.5R.13): 설정 ``observe_event_prefixes``(None = 패키지 기본 데이터,
  빈 목록 = 끔) → ``GET /observe-event-prefixes``. 실행·저장은 이 값을 쓰지 않는다.
- 자식 Run(design §5R.7): 엔진 자식 Run 준비자 = ``RunService.prepare_child``(같은 검사·준비).
- 시작: legacy 계보 올리기(멱등) → **이전 프로세스의 미종료 Run 정리**(``recover_unfinished_runs``,
  다른 시작 동작보다 먼저, design §R14.5) → 백엔드 설정 적용(``backends``, 거부되면 시작 실패)
  → ``show_hidden_backends``(환경변수 ``<접두어>SHOW_HIDDEN_BACKENDS``)면 개발·테스트용으로 숨긴
  백엔드(디스크립터 ``ui_hints.hidden``)의 숨김을 푼다(5.2R.105). 꺼져 있으면 화면이 선택지·설정
  카드에서 뺀다(실행·조회 경로는 그대로).
- 종료: 실행 중 Run을 "끊김"으로 정리(``shutdown_timeout``). ``runs.starter.shutdown``을 먼저 부른
  모듈이 있으면 그 결과를 기다린다(한 번만 정리).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from agent_console_contracts import CONTRACT_VERSIONS, Issue, RunEvent
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts
from agent_console_runtime import (
    GraphRuntime,
    InMemoryEventBus,
    Registries,
    load_registries,
    recover_unfinished_runs,
)

from .backends import build_secret_resolver, configure_backends, reveal_hidden_backends
from .errors import ERROR_MAP
from .interactions import InteractionService
from .observe import observe_event_prefixes_of
from .plugins import (
    CONDITION_OPERATORS_EXTENSION,
    bind_condition_operators,
    bind_redactor,
    load_condition_operator_group,
)
from .ports import (
    DEFINITIONS_LOOKUP,
    INTERACTIONS_PORT,
    INTERACTIONS_UPDATED,
    RESUME_HANDLERS,
    RUN_PREPARERS,
    RUN_SCOPES,
    RUN_SERVICES,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    RUNS_STARTER,
    SECRET_REDACT,
    SECRET_RULES,
    SERVER_ATTRIBUTES,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    RunEnvironment,
)
from .readiness import build_login_service, build_readiness_service
from .redaction import SuspectedRedaction
from .routes import build_router
from .service import RunService, team_rules_warning
from .settings import SETTINGS_COMPAT, RunsModuleSettings
from .storage import BRANCH, memory_storage_warning, open_recorder
from .ws import topic_handlers

MODULE_ID = "mod-runs"
WEB_ROLES: tuple[str, ...] = ("runs",)
"""웹 라우트 역할(design §3R.1.3 표)."""

DEFAULT_BASE_DIR = Path(".")
DEFAULT_STATE_DIR = Path(".agent-console") / ".state"
"""호스트가 경로를 주지 않을 때(테스트 등) 쓰는 기준·상태 폴더."""

_log = logging.getLogger("agent_console_mod_runs")


def _version() -> str:
    try:
        return version("agent-console-mod-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


def _registries(found: Any) -> Registries:
    """호스트 레지스트리(없으면 설치된 entry point로 새로 읽은 것 — 단독 실행용).

    어느 쪽이든 연산자를 쓰는 노드·엣지 종류에 묶음의 조건 연산자 레지스트리를 준다(플러그인을
    다 읽은 뒤라 명시 플러그인이 더한 연산자도 들어 있다).
    """
    if isinstance(found, Registries):
        registries = found
    else:
        registries = Registries()
        load_registries(registries)
    if CONDITION_OPERATORS_EXTENSION not in registries.extensions:
        # 호스트 플러그인 로더가 돌지 않은 묶음(단독 실행·테스트): 설치된 연산자를 읽는다
        load_condition_operator_group(registries)
    bind_condition_operators(registries)
    return registries


def _resolve(base: Path, path: Path) -> Path:
    return path if path.is_absolute() else base / path


class PublishingSink:
    """엔진 이벤트 발행: WS용 버스에 넣고, 저장된 이벤트마다 ``on_event``를 부른다(예외는 기록)."""

    def __init__(self, bus: InMemoryEventBus, on_event: Callable[[RunEvent], None]) -> None:
        self._bus = bus
        self._on_event = on_event

    def publish(self, event: RunEvent) -> None:
        self._bus.publish(event)
        try:
            self._on_event(event)
        except Exception:
            _log.exception("실행 이벤트 알림 실패: %s", event.type)


class RunsModule:
    """실행 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="실행",
        description=(
            "실행 엔진·Run·이벤트·상호작용 경로, WS run:·interactions, 재시작 복구·이어 가기"
        ),
        provides=(
            RUNS_STARTER,
            RUNS_READER,
            RUNS_EVENTS,
            INTERACTIONS_PORT,
            SECRET_REDACT,
            SERVER_WARNINGS,
            SERVER_ATTRIBUTES,
        ),
        requires=(DEFINITIONS_LOOKUP,),
        optional=(
            RUN_PREPARERS,
            RUN_SERVICES,
            RUN_SCOPES,
            RESUME_HANDLERS,
            WORKSPACE_SETTINGS,
            SECRET_RULES,
        ),
        settings_schema=RunsModuleSettings,
        settings_compat=SETTINGS_COMPAT,
        contracts={"runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        cfg = ctx.settings
        if not isinstance(cfg, RunsModuleSettings):
            cfg = RunsModuleSettings()
        lookup = ctx.port(DEFINITIONS_LOOKUP)
        if lookup is None:  # pragma: no cover - 필수 포트는 조립기가 보장한다
            raise RuntimeError("definitions.lookup이 없습니다")
        registries = _registries(ctx.registries)
        base_dir = ctx.paths.base_dir if ctx.paths is not None else DEFAULT_BASE_DIR
        state_dir = ctx.paths.state if ctx.paths is not None else DEFAULT_STATE_DIR
        environment = RunEnvironment(
            working_directory=_resolve(base_dir, cfg.working_directory or Path(".")),
            run_files_root=_resolve(state_dir, cfg.run_files_dir),
        )
        recorder, in_memory = open_recorder(ctx.database)
        bus = InMemoryEventBus(maxsize=cfg.runtime.event_queue_size)
        redaction = SuspectedRedaction(
            lambda: ctx.port(WORKSPACE_SETTINGS), lambda: ctx.port(SECRET_RULES)
        )
        secrets = build_secret_resolver(
            lookup=ctx.secret_resolver,
            environ=ctx.environ,
            registries=registries,
            min_redact_chars=cfg.min_redact_chars,
            extra_redact=redaction.redact_text,
        )
        readiness = build_readiness_service(
            registries,
            secrets,
            ctx.environ,
            rules=lambda: ctx.port(SECRET_RULES),
            probe_timeout_max_s=cfg.backend_probe_timeout_max_s,
            min_chars=cfg.min_redact_chars,
        )
        login_cfg = cfg.backend_login
        login = (
            build_login_service(
                registries,
                secrets,
                ctx.environ,
                rules=lambda: ctx.port(SECRET_RULES),
                timeout_s=login_cfg.timeout_s,
                timeout_max_s=login_cfg.timeout_max_s,
                heartbeat_s=login_cfg.heartbeat_s,
                retain_s=login_cfg.retain_s,
                screen_max_lines=login_cfg.screen_max_lines,
                min_chars=cfg.min_redact_chars,
            )
            if login_cfg.enabled
            else None
        )
        # 조건 판정 근거는 자르기 전에 엔진 가림을 건다(잘린 비밀 조각이 기록에 남지 않게)
        bind_redactor(registries, secrets.redact)
        holder: list[InteractionService] = []

        def on_event(event: RunEvent) -> None:
            ctx.publish(RUNS_EVENT, event)
            for interactions in holder:
                interactions.on_event(event)

        runtime = GraphRuntime(
            registries,
            recorder,
            PublishingSink(bus, on_event),
            secrets=secrets,
            max_concurrency=cfg.runtime.max_concurrency,
            cancel_grace=cfg.runtime.cancel_grace,
        )
        interactions = InteractionService(
            recorder.interactions,
            runtime,
            hub=ctx.ws_hub,
            notify=lambda item: ctx.publish(INTERACTIONS_UPDATED, item),
        )
        holder.append(interactions)
        service = RunService(
            runtime,
            recorder.runs,
            recorder.events,
            lookup,
            environment=environment,
            preparers=lambda: ctx.ports(RUN_PREPARERS),
            providers=lambda: ctx.ports(RUN_SERVICES),
            scopes=lambda: ctx.ports(RUN_SCOPES),
            resume_handlers=lambda: ctx.ports(RESUME_HANDLERS),
            before_use=redaction.refresh,
            resume_origin=cfg.resume_origin,
            shutdown_timeout=cfg.runtime.shutdown_timeout,
        )

        def warnings() -> list[Issue]:
            found: list[Issue] = []
            if not service.has_preparers:
                found.append(team_rules_warning())
            if in_memory:
                found.append(memory_storage_warning())
            return found

        ctx.provide(RUNS_STARTER, service)
        ctx.provide(RUNS_READER, recorder.runs)
        ctx.provide(RUNS_EVENTS, recorder.events)
        ctx.provide(INTERACTIONS_PORT, interactions)
        ctx.provide(SECRET_REDACT, lambda text: str(secrets.redact(text)))
        ctx.provide(SERVER_WARNINGS, warnings)
        ctx.provide(SERVER_ATTRIBUTES, lambda: {"recovered_runs": len(service.recovered)})
        database = ctx.database
        backend_options = cfg.backends
        show_hidden_backends = cfg.show_hidden_backends

        async def start() -> None:
            if database is not None:
                await asyncio.to_thread(database.upgrade)  # legacy 계보(실행 기록 표), 멱등
            # 1) 이전 프로세스의 Run·대기 상호작용 정리를 가장 먼저(design §R14.5)
            service.recovered = recover_unfinished_runs(recorder, sink=bus)
            configure_backends(registries, backend_options, secrets=secrets, environ=ctx.environ)
            if show_hidden_backends:  # 개발·테스트용 백엔드도 선택지·설정 카드에 보인다
                reveal_hidden_backends(registries)
            redaction.refresh()
            if not service.has_preparers:
                _log.warning("%s", team_rules_warning().message)
            _log.info(
                "실행 모듈 시작: 노드 타입 %d, 백엔드 %d, 복구한 Run %d",
                len(registries.node_types),
                len(registries.backends),
                len(service.recovered),
            )

        async def stop() -> None:
            if login is not None:  # 진행 중인 로그인 하위 과정을 남기지 않는다
                await login.aclose()
            await service.shutdown()

        return ModuleParts(
            routers=[
                build_router(
                    lambda: service,
                    lambda: interactions,
                    runs=lambda: recorder.runs,
                    events=lambda: recorder.events,
                    activity_limit=cfg.activity_limit,
                    readiness=lambda: readiness,
                    login=(lambda: login) if login is not None else None,
                    observe_event_prefixes=observe_event_prefixes_of(cfg.observe_event_prefixes),
                )
            ],
            ws_topics=topic_handlers(
                service, bus=bus, events=recorder.events, interactions=interactions, hub=ctx.ws_hub
            ),
            error_map=dict(ERROR_MAP),
            startup=[start],
            shutdown=[stop],
        )


module = RunsModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "PublishingSink", "RunsModule", "module"]
