"""mod-definitions의 공개 포트·토픽(이름 = 포트, design §3R.1.2·§3R.1.3·§3R.1.5).

제공(소비자는 같은 이름을 자기 ``ports``에 선언해 받는다 — 이 모듈을 import하지 않아도 된다):

- ``definitions.store``: 정의 저장소(``agent_console_store.FileDefinitionStore`` — 읽기·쓰기·버전).
- ``definitions.lookup``: 같은 저장소(읽기 전용으로 쓰는 소비자용 이름).
- ``workspace.settings``: ``() -> WorkspaceSettings``(지금 공통 설정, 파일이 없으면 기본값).
- ``secrets.rules``: ``() -> SecretRules``(기본 규칙 + 설정 ``secrets.extra_*``).
- ``definitions.checks``(여러 제공자): 이 모듈은 공통 설정의 비밀 규칙 검사(위험한 정규식)를 낸다.
- ``server.warnings``(여러 제공자): ``() -> Sequence[Issue]`` — 저장된 정의의 평문 비밀 의심
  (``secret.plain_found``, 정의 저장 때 무효화되는 캐시).
- 토픽 ``definitions.saved``: ``SavedDefinition{kind, id, version_hash, space}``
  (저장·되돌리기·본문 쓰기마다). ``space``는 저장소 공간 이름(None = 라이브러리). 공간 저장소의
  알림은 ``definitions.spaces`` 제공자가 같은 토픽에 ``space``를 담아 낸다(33x).

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``definitions.checks``(여러 제공자): 저장 전 검사(``DefinitionCheck``). 없으면 모델 검증만.
- ``graphs.validation``: 팀 구성 목록의 검증 요약(``GraphValidationSource``). 없으면 ``null``.
  공간(``?project=``) 목록은 제공자의 선택 메서드 ``space_summaries``
  (``SpaceGraphValidationSource``)로 계산한다. 그 메서드가 없으면 ``null``(라이브러리 기준
  ``summaries``는 부르지 않는다).
- ``graphs.entry_labels``: 팀 구성 목록의 입구 이름(``GraphEntryLabels``). 없으면 ``null``.
- ``graphs.session_summary``: 팀 구성 목록의 세션 집계(``GraphSessionSummarySource``, 6R.20k).
  없으면 ``null``(위임 방식 등 디스크립터를 아는 연동이 계산한다 — 이 모듈은 세션 값의 뜻을 모른다).
- ``definitions.spaces``: 공간 이름 → 정의 저장소(``agent_console_store.DefinitionSpaces``). 있으면
  에이전트·팀 구성 경로가 ``?project=<이름>``을 받아 그 공간 저장소를 쓴다. 없으면 ``?project=``
  요청은 409 ``feature_unavailable``이고 질의 없는 요청은 지금처럼 라이브러리. 이 모듈은 이름이
  무엇을 가리키는지(프로젝트) 모른다.
- ``definitions.kind_contributions``(여러 제공자, X44, 6R.5): 정의 종류 기여
  (``agent_console_modkit.KindContribution``). ``library=True`` 종류만 라이브러리 저장소에 더한다
  (``library=False`` 종류의 라이브러리 요청은 모르는 종류라 404). 기본 종류와 이름이 같은 기여는
  건너뛴다. 기여의 참조 추출은 이 모듈이 쓰지 않는다 — 복사 계획을 만드는 쪽(프로젝트 모듈)이 같은
  포트에서 직접 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import (
    Graph,
    GraphSessionSummary,
    GraphValidationSummary,
    Issue,
    WorkspaceSettings,
)
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS, KindContribution, PortKey, Topic
from agent_console_secret_rules import SecretRules
from agent_console_store import DEFINITIONS_SPACES_PORT, DefinitionSpaces, FileDefinitionStore


@runtime_checkable
class DefinitionCheck(Protocol):
    """저장 전 정의 검사 하나. 이슈 path는 문서 기준 JSON Pointer, 메시지에 값이 없다."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


@runtime_checkable
class GraphValidationSource(Protocol):
    """팀 구성 목록의 검증 요약(엔진 + 팀 규칙). 계산할 수 없는 그래프는 None."""

    def summaries(
        self, graph_ids: Sequence[str]
    ) -> Mapping[str, GraphValidationSummary | None]: ...


@runtime_checkable
class SpaceGraphValidationSource(Protocol):
    """``graphs.validation`` 제공자의 **선택** 메서드: 공간(``?project=``) 목록의 검증 요약.

    공간 이름은 이 모듈이 뜻을 모르는 불투명 문자열이다(제공자가 실행의 ``project_id`` 등으로 쓴다).
    """

    def space_summaries(
        self, space: str, graph_ids: Sequence[str], *, lookup: Any = None
    ) -> Mapping[str, GraphValidationSummary | None]:
        """그 공간의 팀 구성 요약(계산할 수 없는 그래프는 None).

        Args:
            space: 공간 이름.
            graph_ids: 그 공간 저장소의 팀 구성 id.
            lookup: 그 공간의 정의 저장소(캐시 개정 지문 재료로 써도 된다).
        """
        ...


@runtime_checkable
class GraphEntryLabels(Protocol):
    """팀 구성 하나의 입구 노드 표시 이름(해석할 수 없으면 None)."""

    def entry_labels(self, graph: Graph) -> list[str] | None: ...


@runtime_checkable
class GraphSessionSummarySource(Protocol):
    """팀 구성 하나의 세션 집계(계산할 수 없거나 세션 값이 있는 연결이 없으면 None)."""

    def session_summary(self, graph: Graph) -> GraphSessionSummary | None: ...


@dataclass(frozen=True)
class SavedDefinition:
    """``definitions.saved`` 항목(design §3R.1.5 ``{kind, id, version_hash}`` + 공간 이름).

    Attributes:
        space: 저장소 공간 이름(``?project=`` 값). None = 라이브러리(앱 workspace).
    """

    kind: str
    id: str
    version_hash: str
    space: str | None = None


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
"""``workspace.settings`` 포트 모양."""

type SecretRulesReader = Callable[[], SecretRules]
"""``secrets.rules`` 포트 모양."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양(``GET /server-info``의 ``warnings``에 더해진다)."""

DEFINITIONS_STORE: PortKey[FileDefinitionStore] = PortKey("definitions.store", "정의 저장소")
DEFINITIONS_LOOKUP: PortKey[FileDefinitionStore] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
SERVER_WARNINGS: PortKey[WarningSource] = PortKey(
    "server.warnings", "서버 정보 경고(평문 비밀 점검 등)", multi=True
)
GRAPH_VALIDATION: PortKey[GraphValidationSource] = PortKey(
    "graphs.validation", "팀 구성 목록 검증 요약"
)
GRAPH_ENTRY_LABELS: PortKey[GraphEntryLabels] = PortKey("graphs.entry_labels", "팀 구성 입구 이름")
GRAPH_SESSION_SUMMARY: PortKey[GraphSessionSummarySource] = PortKey(
    "graphs.session_summary", "팀 구성 목록 세션 집계"
)
DEFINITIONS_SPACES: PortKey[DefinitionSpaces] = PortKey(
    DEFINITIONS_SPACES_PORT, "공간 이름 → 정의 저장소"
)
DEFINITIONS_SAVED: Topic[SavedDefinition] = Topic("definitions.saved")
KIND_CONTRIBUTIONS: PortKey[KindContribution[Any]] = DEFINITION_KIND_CONTRIBUTIONS
"""``definitions.kind_contributions``(키트의 같은 포트, X44)."""

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_SPACES",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "GRAPH_ENTRY_LABELS",
    "GRAPH_SESSION_SUMMARY",
    "GRAPH_VALIDATION",
    "KIND_CONTRIBUTIONS",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "GraphEntryLabels",
    "GraphSessionSummarySource",
    "GraphValidationSource",
    "SavedDefinition",
    "SecretRulesReader",
    "SpaceGraphValidationSource",
    "WarningSource",
    "WorkspaceSettingsReader",
]
