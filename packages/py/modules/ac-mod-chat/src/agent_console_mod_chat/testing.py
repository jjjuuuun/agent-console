"""단독 실행·테스트용 모듈(공개).

- ``local_definitions_module``: ``definitions.lookup``을 워크스페이스 폴더의 파일 저장소로 주는 작은
  모듈. 단독 실행 ``python -m agent_console_mod_chat``가 ``--with`` 없이 실행되면 이것을 붙인다
  (통합 서버에서는 ``mod-definitions``가 대신한다).
- ``fake_turns_module``: 실행 연결(``chat.turn_launcher``·``chat.runs``·``chat.run_events``·
  ``chat.interactions``)을 ``agent_console_chat.testing``의 가짜로 주는 모듈(테스트용 — 턴은
  ``launcher.finish``로 끝낸다). 통합 서버에서는 ``link-chat-runs``가 대신한다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_chat.testing import FakeLauncher, MemoryEvents, MemoryInteractions, MemoryRuns
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

from .ports import (
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    DEFINITIONS_LOOKUP,
)

LOCAL_DEFINITIONS_ID = "local-definitions"
FAKE_TURNS_ID = "fake-turns"
DEFAULT_WORKSPACE = Path(".agent-console")


def local_definitions_module(
    module_id: str = LOCAL_DEFINITIONS_ID, *, workspace: Path | None = None
) -> Module:
    """``definitions.lookup`` 제공 모듈(워크스페이스 파일 저장소)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        ctx.provide(DEFINITIONS_LOOKUP, FileDefinitionStore(root, DEFAULT_KINDS))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_LOOKUP], on_build=build)


def fake_turns_module(
    module_id: str = FAKE_TURNS_ID,
    *,
    launcher: FakeLauncher | None = None,
    interactions: MemoryInteractions | None = None,
) -> Module:
    """실행 연결 4종을 가짜로 주는 모듈.

    Args:
        launcher: 쓸 가짜 실행기(없으면 새 ``FakeLauncher(MemoryRuns(), MemoryEvents())``).
            ``chat.runs``·``chat.run_events``는 이 실행기의 저장소다.
        interactions: 상호작용 조회(없으면 빈 ``MemoryInteractions``).
    """
    fake = launcher if launcher is not None else FakeLauncher(MemoryRuns(), MemoryEvents())
    found = interactions if interactions is not None else MemoryInteractions()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(CHAT_TURN_LAUNCHER, fake)
        ctx.provide(CHAT_RUNS, fake.runs)
        ctx.provide(CHAT_RUN_EVENTS, fake.events)
        ctx.provide(CHAT_INTERACTIONS, found)
        return ModuleParts()

    return fake_module(
        module_id,
        kind="testing",
        provides=[CHAT_TURN_LAUNCHER, CHAT_RUNS, CHAT_RUN_EVENTS, CHAT_INTERACTIONS],
        on_build=build,
    )


__all__ = [
    "FAKE_TURNS_ID",
    "LOCAL_DEFINITIONS_ID",
    "fake_turns_module",
    "local_definitions_module",
]
