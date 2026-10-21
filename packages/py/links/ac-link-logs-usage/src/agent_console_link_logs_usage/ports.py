"""link-logs-usage의 포트·토픽(이름 = 포트, design §3R.1.2·§4R.8).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``logs.query``: 로그 색인 읽기 중 ``token_samples(flt)``만 쓴다(``LogTokenQuery``).
- 필수 ``usage.service``: 존재 확인용(사용량 모듈이 꺼져 있으면 이 연동도 꺼진다). 쓰지 않는다.
- 선택 ``logs.ingest``: ``scan(source_ids)``만 쓴다(첫 조회가 진행 중인 수집을 기다림).
- 토픽 ``logs.ingested``(구독): 새 로그가 색인되면 표본 캐시를 버린다.

제공:

- ``usage.sources``(여러 제공자): 런타임 사용량 출처 ``local-logs``(``LocalLogsUsageSource``).
- ``logs.source_defaults``(여러 제공자): 이 PC에 로그가 있는 출처의 기본 켜기(``autoenable``).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts.logs import TokenSample
from agent_console_logs import LogFilter
from agent_console_modkit import PortKey, Topic
from agent_console_usage import UsageSource


@runtime_checkable
class LogTokenQuery(Protocol):
    """``logs.query`` 중 이 연동이 쓰는 부분(막히는 호출 — 스레드에서 부른다)."""

    def token_samples(self, flt: LogFilter) -> Sequence[TokenSample]:
        """필터에 맞는 응답별 토큰 표본(시각순, 같은 응답은 한 번)."""
        ...


@runtime_checkable
class LogIngest(Protocol):
    """``logs.ingest`` 중 이 연동이 쓰는 부분."""

    async def scan(self, source_ids: Collection[str] | None = None) -> Any:
        """지금 수집한다(진행 중인 수집이 요청을 덮으면 그 결과를 기다린다)."""
        ...


class IngestedLike(Protocol):
    """``logs.ingested`` 페이로드 중 쓰는 부분(``LogsIngestedPayload``)."""

    @property
    def source_ids(self) -> Sequence[str]: ...


LOGS_QUERY: PortKey[LogTokenQuery] = PortKey("logs.query", "로그 색인 읽기")
USAGE_SERVICE: PortKey[Any] = PortKey("usage.service", "사용량 서비스(존재 확인)")
USAGE_SOURCES: PortKey[UsageSource] = PortKey(
    "usage.sources", "런타임 사용량 출처(X13)", multi=True
)
LOGS_INGEST: PortKey[LogIngest] = PortKey("logs.ingest", "로그 수집(첫 조회 대기)")
SOURCE_DEFAULTS: PortKey[Callable[[], Mapping[str, bool]]] = PortKey(
    "logs.source_defaults", "로그 출처 기본 켜기(출처 id → bool)", multi=True
)
LOGS_INGESTED: Topic[Any] = Topic("logs.ingested")
"""로그 수집으로 새 이벤트가 색인됨(``source_ids``·``count``·``max_seq``)."""

__all__ = [
    "LOGS_INGEST",
    "LOGS_INGESTED",
    "LOGS_QUERY",
    "SOURCE_DEFAULTS",
    "USAGE_SERVICE",
    "USAGE_SOURCES",
    "IngestedLike",
    "LogIngest",
    "LogTokenQuery",
]
