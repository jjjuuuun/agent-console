"""link-runs-usage의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L5).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``runs.reader``: Run·NodeRun 조회(``agent_console_usage.RollupRunSource``).
- 필수 ``runs.events``: 실행 이벤트 조회(``RollupEventSource`` + ``UsageEventQuery``).
- 토픽 ``runs.event``(구독): 이벤트가 생긴 Run의 집계 캐시를 다시 계산하게 표시한다.
- 선택 ``projects.lookup``·``records.spaces``(요청 11/07): 등록 프로젝트 목록과 그 기록 DB. 둘 다
  있으면 ``usage.event_query``가 프로젝트 기록의 이벤트도 합친다(계정 창은 계정 단위). 없으면 앱
  기록만 읽는다.

제공:

- ``usage.event_query``: 실행 이벤트 조회(``MergedEventQuery`` — 앱 기록 ``runs.events`` + 등록
  프로젝트 기록 DB의 ``latest_by_type``을 ts 내림차순으로 합친 것, 사용량 출처 맥락).
- ``usage.token_rollups``: 플랫폼 실행분 토큰 집계(``IncrementalTokenRollups``, 증분 캐시).
"""

from __future__ import annotations

from typing import Any, Protocol

from agent_console_modkit import PortKey, Topic
from agent_console_store import RECORDS_SPACES_PORT, RecordsSpaces

from .events import ProjectListing


class EventLike(Protocol):
    @property
    def run_id(self) -> str: ...


RUNS_READER: PortKey[Any] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[Any] = PortKey("runs.events", "실행 이벤트 조회")
USAGE_EVENT_QUERY: PortKey[Any] = PortKey("usage.event_query", "실행 이벤트 조회")
USAGE_TOKEN_ROLLUPS: PortKey[Any] = PortKey("usage.token_rollups", "플랫폼 실행분 토큰 집계")
RUNS_EVENT: Topic[EventLike] = Topic("runs.event")
PROJECTS_LOOKUP: PortKey[ProjectListing] = PortKey("projects.lookup", "프로젝트 읽기")
RECORDS_SPACES: PortKey[RecordsSpaces] = PortKey(
    RECORDS_SPACES_PORT, "공간 이름 → 프로젝트 기록 DB 핸들"
)

__all__ = [
    "PROJECTS_LOOKUP",
    "RECORDS_SPACES",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "USAGE_EVENT_QUERY",
    "USAGE_TOKEN_ROLLUPS",
    "EventLike",
]
