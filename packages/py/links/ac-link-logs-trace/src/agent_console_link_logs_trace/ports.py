"""link-logs-trace의 포트(이름 = 포트, design §3R.1.2·§4R.8).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``logs.query``: 로그 색인 읽기 중 이벤트 목록(``LogEventReader.events`` — 키셋 페이지).
  ``mod-logs``가 준다. 모양만 맞으면 다른 제공자도 된다.

제공: 없음(경로만 — ``/logs/sessions/{id}/trace``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_console_contracts.logs import LogEventPage
from agent_console_logs import LogFilter
from agent_console_modkit import PortKey


@runtime_checkable
class LogEventReader(Protocol):
    """``logs.query`` 중 쓰는 부분(막히는 호출)."""

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage: ...


LOGS_QUERY: PortKey[LogEventReader] = PortKey("logs.query", "로그 색인 읽기")

__all__ = ["LOGS_QUERY", "LogEventReader"]
