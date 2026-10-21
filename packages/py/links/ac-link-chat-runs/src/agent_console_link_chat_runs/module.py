"""연동 모듈 정의(entry point ``agent_console.server_modules``의 ``link-chat-runs``).

채팅(``mod-chat``)과 실행(``mod-runs``)을 잇는다(design §3R.1.4 L1~L3).

- 필수: ``chat.conversations``·``runs.starter``·``runs.reader``·``runs.events``. 선택:
  ``interactions.port``. 구독: ``runs.event``(대화 요약 알림).
- 제공: ``chat.turn_launcher``(턴 = ``start_run(conversation_id=)``)·``chat.runs``·
  ``chat.run_events``·``chat.interactions``(있을 때, 루트 기준 — 자식 Run 요청 포함),
  ``chat.turn_sessions``(자식 Run 노드 세션을 경로 키로 — 중첩 팀 대화 이어 쓰기),
  ``runs.resume_handlers``(대화 턴 이어 가기).
- 시작: 저장된 채팅 대기열을 ``chat.queue_after_restart``대로 처리한다(``apply_restart_policy``,
  실행 모듈의 미종료 Run 정리 뒤 — 조립 순서상 이 연동은 실행·채팅 모듈 뒤에 시작한다).
- 종료(조립 역순이라 채팅·실행 모듈보다 먼저): 대기열 꺼내기 멈춤(``stop_dispatch``) → 실행
  정리(``runs.starter.shutdown()``을 기다린다 — 끊기는 턴 뒤에 대기열을 꺼내지 않고, 채팅 감시
  정리(``mod-chat`` 종료)보다 먼저 Run이 "끊김"으로 정리되게).
- 이 연동이 꺼지면 대화·기록·대기열은 동작하고 메시지 전송만 409 ``feature_unavailable``이다.
  상호작용 카드·이어 가기는 웹이 숨긴다(역할 ``conversations:runs``).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from agent_console_contracts import CONTRACT_VERSIONS
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts

from .adapters import (
    ConversationNotifier,
    ConversationResume,
    LineageSessions,
    RootInteractions,
    RuntimeTurnLauncher,
)
from .ports import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    CHAT_TURN_SESSIONS,
    INTERACTIONS_PORT,
    RESUME_HANDLERS,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    RUNS_STARTER,
)

MODULE_ID = "link-chat-runs"
WEB_ROLES: tuple[str, ...] = ("conversations:runs",)
"""웹 연동 부분 역할(채팅 메시지 전송·위임 칩·상호작용 카드·턴 이어 가기)."""

_log = logging.getLogger("agent_console_link_chat_runs")


def _version() -> str:
    try:
        return version("agent-console-link-chat-runs")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 소스로 실행
        return "0.0.0"


class ChatRunsLink:
    """채팅 ↔ 실행 연동 모듈."""

    descriptor = ModuleDescriptor(
        id=MODULE_ID,
        version=_version(),
        kind="link",
        title="채팅·실행 연동",
        description="대화 턴 시작·대화 알림·상호작용·턴 이어 가기·재시작 대기열 정책·종료 순서",
        provides=(
            CHAT_TURN_LAUNCHER,
            CHAT_RUNS,
            CHAT_RUN_EVENTS,
            CHAT_INTERACTIONS,
            CHAT_TURN_SESSIONS,
            RESUME_HANDLERS,
        ),
        requires=(CHAT_CONVERSATIONS, RUNS_STARTER, RUNS_READER, RUNS_EVENTS),
        optional=(INTERACTIONS_PORT,),
        contracts={"chat": CONTRACT_VERSIONS["chat"], "runs": CONTRACT_VERSIONS["runs"]},
        web_roles=WEB_ROLES,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        chat = ctx.port(CHAT_CONVERSATIONS)
        starter = ctx.port(RUNS_STARTER)
        runs = ctx.port(RUNS_READER)
        events = ctx.port(RUNS_EVENTS)
        if chat is None or starter is None or runs is None or events is None:
            raise RuntimeError("필수 포트가 없습니다")  # pragma: no cover - 조립기가 보장한다
        interactions = ctx.port(INTERACTIONS_PORT)
        ctx.provide(CHAT_TURN_LAUNCHER, RuntimeTurnLauncher(starter))
        ctx.provide(CHAT_RUNS, runs)
        ctx.provide(CHAT_RUN_EVENTS, events)
        ctx.provide(CHAT_TURN_SESSIONS, LineageSessions(runs, events))
        if interactions is not None:
            ctx.provide(CHAT_INTERACTIONS, RootInteractions(interactions))
        ctx.provide(RESUME_HANDLERS, ConversationResume(lambda: chat))
        ctx.subscribe(RUNS_EVENT, ConversationNotifier(chat, starter))

        async def start() -> None:
            applied = await chat.apply_restart_policy()
            if applied:
                _log.info("재시작 전 대기열이 남은 대화 %d개를 처리했습니다", len(applied))

        async def stop() -> None:
            chat.stop_dispatch()  # 끊기는 턴 뒤에 대기열을 꺼내지 않는다(다음 시작 때 처리)
            try:
                # 실행 정리(한 번만 — 실행 모듈 종료는 같은 결과를 기다린다)
                await starter.shutdown()
            except Exception:
                _log.exception("실행 정리 실패")

        return ModuleParts(startup=[start], shutdown=[stop])


module = ChatRunsLink()
"""entry point가 가리키는 모듈 인스턴스."""

__all__ = ["MODULE_ID", "WEB_ROLES", "ChatRunsLink", "module"]
