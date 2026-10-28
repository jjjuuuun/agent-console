"""서버 모듈 정의(entry point ``agent_console.server_modules``의 ``mod-chat``).

- 제공: ``chat.conversations``(``ChatService``)·``server.warnings``. 토픽 ``conversations.updated``.
  WS ``conversation:<id>``. 경로 ``/conversations…``(대화·턴·메시지·대기열).
- 필수 포트 없음. 선택: ``chat.turn_launcher``·``chat.runs``·``chat.run_events``·
  ``chat.interactions``·``chat.turn_sessions``(실행 연결 — 보통 ``link-chat-runs``가 준다),
  ``definitions.lookup``,
  ``workspace.settings``(``ports.py``).
- 저장: 이 모듈이 소유한 ``conversations``·``chat_queue``(``storage/``)를 호스트 DB 핸들의 엔진
  위에 둔다. 마이그레이션 계보 ``chat``은 모듈이 켜질 때만 올라간다(테이블은 legacy 0002·0003이
  만들었다). DB가 없으면 메모리(경고 ``chat.storage_memory``).
- 시작: 실행 연결을 서비스에 붙인다(``ChatService.connect`` — 연결
  모듈은 이 모듈의 포트가 필요해 조립 순서상 뒤에 빌드되므로 시작 때 읽는다). 재시작 대기열 정책은
  턴 실행기를 주는 연동 모듈이 시작할 때 적용한다.
- 종료: 채팅 감시 정리(``aclose``). 대기열 꺼내기 멈춤·실행 정리는 그보다 먼저 연동 모듈이 한다
  (종료 훅은 조립 역순).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_console_chat import ChatService, layered_chat_settings
from agent_console_contracts import CONTRACT_VERSIONS, ChatSettings, ConversationSummary, Issue
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .errors import error_map
from .graphs import PortGraphLookup
from .ports import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    CHAT_TURN_SESSIONS,
    CONVERSATIONS_UPDATED,
    DEFINITIONS_LOOKUP,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
)
from .routes import build_router
from .storage import BRANCH, memory_storage_warning, open_chat_storage
from .ws import conversation_topic, topic_handlers, updated_message

MODULE_ID = "mod-chat"
WEB_ROLES: tuple[str, ...] = ("conversations",)
"""웹 라우트 역할(design §3R.1.3 표)."""

_log = logging.getLogger("agent_console_mod_chat")


def _version() -> str:
    try:
        return version("agent-console-mod-chat")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ChatModule:
    """채팅 기능 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="feature",
        title="채팅",
        description=(
            "대화·턴·메시지·대기열 경로, WS conversation:. 턴 실행·상호작용은 포트로 받는다"
        ),
        provides=(CHAT_CONVERSATIONS, SERVER_WARNINGS),
        optional=(
            CHAT_TURN_LAUNCHER,
            CHAT_RUNS,
            CHAT_RUN_EVENTS,
            CHAT_INTERACTIONS,
            CHAT_TURN_SESSIONS,
            DEFINITIONS_LOOKUP,
            WORKSPACE_SETTINGS,
        ),
        contracts={"chat": CONTRACT_VERSIONS["chat"]},
        web_roles=WEB_ROLES,
        migrations=(BRANCH,),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        storage = open_chat_storage(ctx.database)
        graphs = PortGraphLookup(lambda: ctx.port(DEFINITIONS_LOOKUP))
        hub: Any = ctx.ws_hub

        def common() -> ChatSettings:
            reader = ctx.port(WORKSPACE_SETTINGS)
            return reader().chat if reader is not None else ChatSettings()

        def publish(summary: ConversationSummary) -> None:
            hub.publish(conversation_topic(summary.id), updated_message(summary))
            ctx.publish(CONVERSATIONS_UPDATED, summary)

        service = ChatService(
            storage.conversations,
            graphs,
            settings=layered_chat_settings(common),
            listener=publish,
            queue=storage.queue,
        )

        def warnings() -> list[Issue]:
            return [memory_storage_warning()] if storage.in_memory else []

        def require_graphs() -> None:
            if not graphs.available:
                raise ctx.unavailable(DEFINITIONS_LOOKUP, "팀 구성을 읽을 수 없습니다")

        ctx.provide(CHAT_CONVERSATIONS, service)
        ctx.provide(SERVER_WARNINGS, warnings)

        async def start() -> None:
            service.connect(
                launcher=ctx.port(CHAT_TURN_LAUNCHER),
                runs=ctx.port(CHAT_RUNS),
                events=ctx.port(CHAT_RUN_EVENTS),
                interactions=ctx.port(CHAT_INTERACTIONS),
                sessions=ctx.port(CHAT_TURN_SESSIONS),
            )
            if not service.can_send:
                _log.info("턴 실행기가 없어 대화 메시지 전송이 꺼져 있습니다(대화·대기열은 동작)")

        async def stop() -> None:
            await service.aclose()

        return ModuleParts(
            routers=[
                build_router(
                    lambda: service,
                    require_graphs=require_graphs,
                    projects=lambda: storage.projects,
                )
            ],
            ws_topics=topic_handlers(service, hub=hub),
            error_map=error_map(MODULE_ID),
            startup=[start],
            shutdown=[stop],
        )


module = ChatModule()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "ChatModule", "module"]
