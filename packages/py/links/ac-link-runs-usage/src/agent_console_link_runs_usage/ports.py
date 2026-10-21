"""link-runs-usage의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L5).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``runs.reader``: Run·NodeRun 조회(``agent_console_usage.RollupRunSource``).
- 필수 ``runs.events``: 실행 이벤트 조회(``RollupEventSource`` + ``UsageEventQuery``).
- 토픽 ``runs.event``(구독): 이벤트가 생긴 Run의 집계 캐시를 다시 계산하게 표시한다.

제공:

- ``usage.event_query``: 실행 이벤트 조회(``runs.events`` 그대로 — 사용량 출처 맥락).
- ``usage.token_rollups``: 플랫폼 실행분 토큰 집계(``IncrementalTokenRollups``, 증분 캐시).
"""

from __future__ import annotations

from typing import Any, Protocol

from agent_console_modkit import PortKey, Topic


class EventLike(Protocol):
    @property
    def run_id(self) -> str: ...


RUNS_READER: PortKey[Any] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[Any] = PortKey("runs.events", "실행 이벤트 조회")
USAGE_EVENT_QUERY: PortKey[Any] = PortKey("usage.event_query", "실행 이벤트 조회")
USAGE_TOKEN_ROLLUPS: PortKey[Any] = PortKey("usage.token_rollups", "플랫폼 실행분 토큰 집계")
RUNS_EVENT: Topic[EventLike] = Topic("runs.event")

__all__ = [
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "USAGE_EVENT_QUERY",
    "USAGE_TOKEN_ROLLUPS",
    "EventLike",
]
