"""단독 실행·테스트용 모듈(공개).

``local_logs_module``: ``logs.query``(이벤트 목록)를 주어진 로그 색인
(``agent_console_logs.LogIndex``, 없으면 빈 메모리 색인)으로 주는 작은 모듈. 단독 실행이
``--with`` 없이 실행되면 이것을 붙인다(통합 서버·실제 데이터는 ``--with mod-logs``가 대신한다).
"""

from __future__ import annotations

from agent_console_contracts.logs import LogEventPage
from agent_console_logs import LogFilter, LogIndex, QueryContext
from agent_console_logs.testing import MemoryLogIndex
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import LOGS_QUERY

LOCAL_LOGS_ID = "local-logs"


class IndexEventReader:
    """``LogIndex`` → ``logs.query``의 ``events`` 모양(질의 맥락은 고정값).

    Args:
        index: 로그 색인.
        ctx: 질의 맥락(없으면 기본값).
    """

    def __init__(self, index: LogIndex, ctx: QueryContext | None = None) -> None:
        self._index = index
        self._ctx = ctx if ctx is not None else QueryContext()

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage:
        return self._index.query_events(flt, self._ctx, with_total=with_total)


def local_logs_module(module_id: str = LOCAL_LOGS_ID, *, index: LogIndex | None = None) -> Module:
    """``logs.query`` 제공 모듈(주어진 색인, 없으면 빈 메모리 색인)."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(LOGS_QUERY, IndexEventReader(index if index is not None else MemoryLogIndex()))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[LOGS_QUERY], on_build=build)


__all__ = ["LOCAL_LOGS_ID", "IndexEventReader", "local_logs_module"]
