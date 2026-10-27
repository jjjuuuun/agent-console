"""link-logs-architecture의 포트(이름 = 포트, design §5.5R.3). 제공 모듈을 import하지 않고 같은
이름과 쓰는 모양만 여기 선언한다(프로토콜은 구조 타입이라 모양만 맞으면 다른 제공자도 된다).

받음(모두 필수):

- ``logs.query``: 로그 색인 읽기(``mod-logs``). 필터 읽기(``parse_filter``)·질의 맥락
  (``query_context`` — 분류 체계에서 오류로 표시한 범주)·이벤트 쪽 넘김(``events``)·상세(``event``)·
  토큰 표본(``token_samples``)만 쓴다.
- ``architecture.catalog``: 병합된 구조도 프로필과 조건 연산자(``mod-architecture``). ``catalog()``·
  ``operators()``·``max_scope_events``만 쓴다.

제공:

- ``logs.filter_predicates``(여러 제공자, X28): 필터 ``arch``·``arch_group``·``arch_sources``
  (``ArchitectureFilter``). 이벤트 표가 구조도 칸·연결·묶음으로 걸러진다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from agent_console_architecture import ProfileCatalog
from agent_console_conditions import ConditionOperator
from agent_console_contracts.logs import LogEventDetail, LogEventPage, TokenSample
from agent_console_logs import JsonValue, LogFilter, LogFilterExtension, QueryContext
from agent_console_modkit import PortKey


@runtime_checkable
class LogQueryReader(Protocol):
    """``logs.query`` 중 쓰는 부분(막히는 호출 — 동기 경로·스레드에서 부른다)."""

    def query_context(self, *, tz: str | None = None) -> QueryContext: ...

    def parse_filter(self, params: Mapping[str, JsonValue], *, path: str = "") -> LogFilter: ...

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage: ...

    def event(self, uid: str) -> LogEventDetail | None: ...

    def token_samples(self, flt: LogFilter) -> list[TokenSample]: ...


@runtime_checkable
class ArchitectureCatalogReader(Protocol):
    """``architecture.catalog`` 중 쓰는 부분."""

    max_scope_events: int
    """로그 범위 투영 상한(설치자 값)."""

    def catalog(self) -> ProfileCatalog: ...

    def operators(self) -> Mapping[str, ConditionOperator]: ...


LOGS_QUERY: PortKey[LogQueryReader] = PortKey("logs.query", "로그 색인 읽기")
ARCHITECTURE_CATALOG: PortKey[ArchitectureCatalogReader] = PortKey(
    "architecture.catalog", "구조도 프로필 카탈로그(병합된 프로필·연산자·검사·투영)"
)
LOG_FILTER_PREDICATES: PortKey[LogFilterExtension] = PortKey(
    "logs.filter_predicates", "로그 필터 확장(X28, 이름 묶음 → 이벤트 판정)", multi=True
)

__all__ = [
    "ARCHITECTURE_CATALOG",
    "LOGS_QUERY",
    "LOG_FILTER_PREDICATES",
    "ArchitectureCatalogReader",
    "LogQueryReader",
]
