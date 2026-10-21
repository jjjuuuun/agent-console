"""단독 실행·테스트용 모듈(공개).

``local_runs_module``: ``runs.reader``·``runs.events``를 상태 폴더 DB(호스트 DB 핸들, 없으면
메모리)의 실행 기록으로 주는 작은 모듈. 단독 실행이 ``--with`` 없이 실행되면 이것을 붙인다
(통합 서버에서는 ``mod-runs``가 대신한다).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import InMemoryStorage, SqliteStorage

from .ports import RUNS_EVENTS, RUNS_READER

LOCAL_RUNS_ID = "local-runs"


def local_runs_module(module_id: str = LOCAL_RUNS_ID, *, storage: Any = None) -> Module:
    """``runs.reader``·``runs.events`` 제공 모듈(주어진 저장 묶음, 없으면 호스트 DB·메모리)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        found = storage
        startup: list[Callable[[], Awaitable[None]]] = []
        if found is None and ctx.database is not None:
            database = ctx.database
            found = SqliteStorage(database.engine)

            async def upgrade() -> None:
                database.upgrade()

            startup.append(upgrade)
        found = found if found is not None else InMemoryStorage()
        ctx.provide(RUNS_READER, found.runs)
        ctx.provide(RUNS_EVENTS, found.events)
        return ModuleParts(startup=startup)

    return fake_module(
        module_id, kind="testing", provides=[RUNS_READER, RUNS_EVENTS], on_build=build
    )


__all__ = ["LOCAL_RUNS_ID", "local_runs_module"]
