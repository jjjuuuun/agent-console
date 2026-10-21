"""link-runs-teams의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L4).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다. 모양은 계약 테스트가 확인한다):

- 필수 ``runs.starter``: 실행 검증(``RunChecker`` — 엔진 + 모든 준비자 ``check``, 팀 구성 읽기).
- 필수 ``definitions.lookup``: 정의 읽기(``DefinitionLookup``).
- 선택 ``workspace.settings``: 지금 공통 설정. 없으면 기본값.
- 선택 ``resources.lookup``·``resources.types``: 리소스 조회·종류. 없으면 리소스 검사·노드
  서비스 ``RESOURCE_LOOKUP`` 없이.
- 선택 ``definitions.checks``(여러 제공자): 저장 전 정의 검사(``DefinitionCheck``). 검증 경로가
  그 경고·정보 이슈(예: 프로젝트 범위 경고)를 엔진·팀 규칙 이슈 뒤에 붙인다. 없으면 붙이지 않는다.
- 토픽 ``definitions.saved``(구독): 검증 요약 캐시를 버린다.

제공:

- ``runs.preparers``: 팀 규칙 검사(엔진 이슈와 같은 뜻은 뺀다)·실행 준비(허용 상호작용·
  상호작용 설정).
- ``runs.services``: 노드 서비스(``ac-nodes-core`` 키 — 에이전트·리소스 조회, 공통 설정,
  기본 백엔드, 작업 폴더, 실행 파일 폴더).
- ``graphs.validation``: 팀 구성 목록 검증 요약(워크스페이스 지문 캐시).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Graph, GraphValidationSummary, Issue, WorkspaceSettings
from agent_console_modkit import PortKey, Topic
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType


class StoredLike(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기. 없으면 저장소 예외(``NotFound`` 등)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """``definitions.checks`` 모양: 저장 전 정의 검사 하나(이슈 path는 문서 기준)."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


@runtime_checkable
class RunChecker(Protocol):
    """``runs.starter``에서 쓰는 부분."""

    def check(self, graph: Graph) -> list[Issue]:
        """엔진 검증 + 실행 전 검사(이슈가 있어도 돌려준다)."""
        ...

    def load_graph(self, graph_id: str, version_hash: str | None = None) -> Graph:
        """저장된 팀 구성(없으면 모듈 오류 — 그 모듈의 오류 맵이 404로 바꾼다)."""
        ...


@runtime_checkable
class ValidationSource(Protocol):
    """``graphs.validation`` 모양."""

    def summaries(
        self, graph_ids: Sequence[str]
    ) -> Mapping[str, GraphValidationSummary | None]: ...


class SavedLike(Protocol):
    """``definitions.saved`` 항목에서 쓰는 부분."""

    @property
    def kind(self) -> str: ...


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
type GraphLoader = Callable[[str, str | None], Graph]
"""팀 구성 읽기(id, 버전 해시 | None = 지금). 없으면 예외(``RunChecker.load_graph`` 모양)."""

RUNS_STARTER: PortKey[RunChecker] = PortKey("runs.starter", "실행 시작·검증·취소")
DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
RESOURCES_LOOKUP: PortKey[ResourceLookup] = PortKey("resources.lookup", "리소스 정의·본문 조회")
RESOURCE_TYPES: PortKey[Registry[ResourceType]] = PortKey("resources.types", "리소스 종류")
RUN_PREPARERS: PortKey[Any] = PortKey("runs.preparers", "실행 전 검사·준비", multi=True)
RUN_SERVICES: PortKey[Any] = PortKey("runs.services", "노드 서비스 공급", multi=True)
GRAPH_VALIDATION: PortKey[ValidationSource] = PortKey("graphs.validation", "팀 구성 목록 검증 요약")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
DEFINITIONS_SAVED: Topic[SavedLike] = Topic("definitions.saved")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SAVED",
    "DEFINITION_CHECKS",
    "GRAPH_VALIDATION",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "RUNS_STARTER",
    "RUN_PREPARERS",
    "RUN_SERVICES",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "DefinitionLookup",
    "GraphLoader",
    "RunChecker",
    "SavedLike",
    "StoredLike",
    "ValidationSource",
    "WorkspaceSettingsReader",
]
