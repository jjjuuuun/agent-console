"""mod-logs가 주고받는 포트·토픽(이름 = 포트, design §3R.1.2·§4R.8).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다(프로토콜은
구조 타입이라 모양만 맞으면 된다).

제공:

- ``logs.query``(``LogQueryPort``): 목록·상세·세션·타임라인·집계·handoff·토큰 표본. 질의 맥락
  (분류 체계·프로젝트 묶기)은 지금 설정으로 만든다.
- ``logs.ingest``(``LogIngestPort``): 런타임 출처 더하기(``add_runtime_source``)·수집 예약
  (``request_scan``)·즉시 수집(``scan``).
- ``server.warnings``(여러 제공자): ``logs.storage_memory``·``logs.redaction_unavailable``·
  출처 실패(``logs.source_failed``·``logs.unknown_classifier``).
- 토픽 ``logs.ingested``(``LogsIngestedPayload``): 수집으로 새 이벤트가 생겼을 때. WS 토픽 ``logs``.

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``logs.sources``(여러 제공자): 런타임 출처(X5r, ``RuntimeLogSource`` — 출처 + 분류기). 없으면
  플러그인 출처(entry point)만 읽는다.
- ``workspace.settings``: 지금 워크스페이스 설정(``logs.*``·``secrets.redact_suspected_in_logs``).
  없으면 기본 설정(출처는 디스크립터 ``default_enabled``, 기본 분류 체계).
- ``secrets.rules``: 비밀 의심 규칙(``redact_value``가 있는 객체를 돌려주는 함수). 없으면 색인을
  가리지 않고 ``logs.redaction_unavailable`` 경고를 낸다.
- ``logs.source_defaults``(여러 제공자): 출처 기본 켜기(``() -> {출처 id: bool}``). 설정에
  ``enabled``가 없는 출처에만 적용한다(``source_defaults``). 없으면 디스크립터 ``default_enabled``.
- ``logs.scope_kinds``(여러 제공자, X27): 범위 종류(``LogScopeKind`` — ``id``·``resolve(value)``).
  필터 ``scope=<id>:<값>``을 세션·run_id 합집합으로 푼다. 없으면 ``scope``는 모두 422.
- ``logs.filter_predicates``(여러 제공자, X28): 필터 확장(``LogFilterExtension`` — ``fields``·
  ``build(values, context)``). 이름이 ``GET /logs/schema`` filters에 실리고 질의 때 이벤트를
  판정한다. 없거나 끄면 그 이름은 422.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import HandoffMatrix, Issue, WorkspaceSettings
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogEventDetail,
    LogEventPage,
    LogScanReport,
    LogSessionSummary,
    LogTaxonomy,
    LogTimeline,
    TokenSample,
)
from agent_console_contracts.modules import LogsIngestedPayload
from agent_console_logs import (
    JsonValue,
    LogClassifier,
    LogFilter,
    LogFilterExtension,
    LogScopeKind,
    LogSource,
    QueryContext,
)
from agent_console_modkit import PortKey, Topic


@runtime_checkable
class RuntimeLogSource(Protocol):
    """``logs.sources`` 포트 한 항목: 다른 모듈의 데이터를 읽는 출처와 그 분류기."""

    @property
    def source(self) -> LogSource: ...

    @property
    def classifier(self) -> LogClassifier: ...


@runtime_checkable
class LogQueryPort(Protocol):
    """``logs.query``: 색인 읽기(막히는 호출 — 비동기 코드에서는 스레드에서 부른다)."""

    def query_context(self, *, tz: str | None = None) -> QueryContext:
        """지금 설정(분류 체계·프로젝트 묶기)으로 만든 질의 맥락."""
        ...

    def parse_filter(self, params: Mapping[str, JsonValue], *, path: str = "") -> LogFilter:
        """쿼리 이름별 값 → ``LogFilter``(등록된 확장 필터 이름도 받는다).

        Raises:
            LogQueryError: 모르는 이름·틀린 값.
        """
        ...

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage: ...

    def event(self, uid: str) -> LogEventDetail | None: ...

    def sessions(self, flt: LogFilter) -> list[LogSessionSummary]: ...

    def timeline(self, session: str, flt: LogFilter | None = None) -> LogTimeline | None: ...

    def aggregate(self, request: LogAggregateRequest) -> list[LogAggregateRow]: ...

    def handoffs(self, flt: LogFilter) -> HandoffMatrix: ...

    def token_samples(self, flt: LogFilter) -> list[TokenSample]: ...

    def taxonomy(self) -> LogTaxonomy: ...


@runtime_checkable
class LogIngestPort(Protocol):
    """``logs.ingest``: 수집 쪽."""

    def add_runtime_source(self, source: LogSource, *, classifier: LogClassifier) -> None:
        """런타임 출처를 더한다(id가 겹치면 ``ValueError``)."""
        ...

    def request_scan(
        self, source_ids: Collection[str] | None = None, *, ref_hint: str | None = None
    ) -> None:
        """수집을 예약한다(막히지 않음, 어느 스레드에서든). 시작 전이면 시작 때 한다."""
        ...

    async def scan(self, source_ids: Collection[str] | None = None) -> LogScanReport:
        """지금 수집한다(진행 중인 수집이 요청을 덮으면 그 결과를 기다린다)."""
        ...


class SuspectedRules(Protocol):
    """비밀 의심 규칙(``agent_console_secret_rules.SecretRules``가 만족)."""

    def redact_value(self, value: Any) -> Any: ...


type SecretRulesReader = Callable[[], SuspectedRules]
"""``secrets.rules`` 포트 모양."""

type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
"""``workspace.settings`` 포트 모양."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

LOGS_QUERY: PortKey[LogQueryPort] = PortKey("logs.query", "로그 색인 읽기")
LOGS_INGEST: PortKey[LogIngestPort] = PortKey("logs.ingest", "로그 수집(런타임 출처·수집 예약)")
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
LOG_SOURCES: PortKey[RuntimeLogSource] = PortKey(
    "logs.sources", "런타임 로그 출처(출처 + 분류기)", multi=True
)
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")

SOURCE_DEFAULTS: PortKey[Callable[[], Mapping[str, bool]]] = PortKey(
    "logs.source_defaults", "로그 출처 기본 켜기(출처 id → bool)", multi=True
)

LOG_SCOPE_KINDS: PortKey[LogScopeKind] = PortKey(
    "logs.scope_kinds", "로그 범위 종류(X27, scope=<종류>:<값>)", multi=True
)
LOG_FILTER_PREDICATES: PortKey[LogFilterExtension] = PortKey(
    "logs.filter_predicates", "로그 필터 확장(X28, 이름 묶음 → 이벤트 판정)", multi=True
)

LOGS_INGESTED: Topic[LogsIngestedPayload] = Topic("logs.ingested")
"""수집으로 새 이벤트가 색인됐을 때(``source_ids``·``count``·``max_seq``)."""

__all__ = [
    "LOGS_INGEST",
    "LOGS_INGESTED",
    "LOGS_QUERY",
    "LOG_FILTER_PREDICATES",
    "LOG_SCOPE_KINDS",
    "LOG_SOURCES",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "SOURCE_DEFAULTS",
    "WORKSPACE_SETTINGS",
    "LogIngestPort",
    "LogQueryPort",
    "RuntimeLogSource",
    "SecretRulesReader",
    "SuspectedRules",
    "WarningSource",
    "WorkspaceSettingsReader",
]
