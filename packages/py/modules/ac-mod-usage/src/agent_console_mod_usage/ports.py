"""mod-usage가 주고받는 포트(이름 = 포트, design §3R.1.2). 다른 모듈은 이 파일을 import하지 않고
같은 이름을 선언해 연결한다.

- 제공: ``usage.service``(``UsageReportService``), ``server.warnings``(여러 제공자 — 출처 id 겹침
  ``usage.source_conflict``, 저장된 출처 설정이 출처 스키마에 맞지 않음
  ``usage.source_config_invalid``), ``definitions.checks``(여러 제공자 — 공통 설정 저장 전에
  ``usage.sources[].config``를 그 출처 ``config_schema``로 검증, error면 저장 거부 422).
- 관측값 저장소는 포트가 아니라 이 모듈의 것이다(``storage/``, 3R.11). 호스트 DB 핸들이 없으면
  기록하지 않는다.
- 선택(없으면 그 부분만 꺼진다):
    - ``usage.event_query``: 실행 이벤트 조회(``agent_console_usage.UsageEventQuery``). 출처 맥락에
      넘긴다. 없으면 실행 이벤트를 쓰는 출처는 빈 목록이다.
    - ``usage.token_rollups``: 플랫폼 실행분 토큰 집계(``TokenRollups``). 없으면 ``rollups``는
      빈 목록이다(사용량은 외부 출처만 보인다).
    - ``workspace.settings``: 지금 워크스페이스 설정(``() -> WorkspaceSettings``). 출처 켜기·설정
      (``usage.sources``)을 여기서 읽는다. 없으면 등록된 출처 전부 켜짐 + 빈 설정.
    - ``usage.sources``(여러 제공자): 런타임 사용량 출처(``agent_console_usage.UsageSource``,
      예: ``link-logs-usage``의 ``local-logs``). 출처 id = 디스크립터 ``id``. 플러그인(레지스트리)
      출처와 id가 겹치면 레지스트리가 이기고 ``server.warnings``로 알린다. 없으면 플러그인 출처만.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import tzinfo
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from agent_console_contracts import Issue, TokenRollupRow, WorkspaceSettings
from agent_console_modkit import PortKey
from agent_console_usage import UsageEventQuery, UsageSource

if TYPE_CHECKING:
    from .service import UsageReportService


@runtime_checkable
class TokenRollups(Protocol):
    """플랫폼 실행분 토큰 집계(소비자 쪽 프로토콜). 제공자는 실행 기록을 읽는다."""

    def rollups(self, *, limit: int, tz: tzinfo) -> Sequence[TokenRollupRow]:
        """최근 Run ``limit``개 범위의 집계(일 단위는 ``tz`` 기준). 막히는 호출이어도 된다
        (모듈이 스레드에서 부른다)."""
        ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """저장 전 정의 검사(``definitions.checks`` 모양 — 제공 쪽 선언). 이슈 path는 문서 기준."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
"""지금 워크스페이스 설정을 돌려주는 함수(``workspace.settings`` 포트 모양)."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

USAGE_SERVICE: PortKey[UsageReportService] = PortKey(
    "usage.service", "사용량 보고 서비스(창 스냅샷·토큰 집계·출처 목록)"
)
EVENT_QUERY: PortKey[UsageEventQuery] = PortKey("usage.event_query", "실행 이벤트 조회")
TOKEN_ROLLUPS: PortKey[TokenRollups] = PortKey("usage.token_rollups", "플랫폼 실행분 토큰 집계")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
USAGE_SOURCES: PortKey[UsageSource] = PortKey(
    "usage.sources", "런타임 사용량 출처(X13)", multi=True
)
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)

__all__ = [
    "DEFINITION_CHECKS",
    "EVENT_QUERY",
    "SERVER_WARNINGS",
    "TOKEN_ROLLUPS",
    "USAGE_SERVICE",
    "USAGE_SOURCES",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "TokenRollups",
    "WarningSource",
    "WorkspaceSettingsReader",
]
