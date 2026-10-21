"""mod-definitions의 공개 포트·토픽(이름 = 포트, design §3R.1.2·§3R.1.3·§3R.1.5).

제공(소비자는 같은 이름을 자기 ``ports``에 선언해 받는다 — 이 모듈을 import하지 않아도 된다):

- ``definitions.store``: 정의 저장소(``agent_console_store.FileDefinitionStore`` — 읽기·쓰기·버전).
- ``definitions.lookup``: 같은 저장소(읽기 전용으로 쓰는 소비자용 이름).
- ``workspace.settings``: ``() -> WorkspaceSettings``(지금 공통 설정, 파일이 없으면 기본값).
- ``secrets.rules``: ``() -> SecretRules``(기본 규칙 + 설정 ``secrets.extra_*``).
- ``definitions.checks``(여러 제공자): 이 모듈은 공통 설정의 비밀 규칙 검사(위험한 정규식)를 낸다.
- ``server.warnings``(여러 제공자): ``() -> Sequence[Issue]`` — 저장된 정의의 평문 비밀 의심
  (``secret.plain_found``, 정의 저장 때 무효화되는 캐시).
- 토픽 ``definitions.saved``: ``SavedDefinition{kind, id, version_hash}``
  (저장·되돌리기·본문 쓰기마다).

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``definitions.checks``(여러 제공자): 저장 전 검사(``DefinitionCheck``). 없으면 모델 검증만.
- ``graphs.validation``: 팀 구성 목록의 검증 요약(``GraphValidationSource``). 없으면 ``null``.
- ``graphs.entry_labels``: 팀 구성 목록의 입구 이름(``GraphEntryLabels``). 없으면 ``null``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Graph, GraphValidationSummary, Issue, WorkspaceSettings
from agent_console_modkit import PortKey, Topic
from agent_console_secret_rules import SecretRules
from agent_console_store import FileDefinitionStore


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
class GraphEntryLabels(Protocol):
    """팀 구성 하나의 입구 노드 표시 이름(해석할 수 없으면 None)."""

    def entry_labels(self, graph: Graph) -> list[str] | None: ...


@dataclass(frozen=True)
class SavedDefinition:
    """``definitions.saved`` 항목(design §3R.1.5 ``{kind, id, version_hash}``)."""

    kind: str
    id: str
    version_hash: str


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
DEFINITIONS_SAVED: Topic[SavedDefinition] = Topic("definitions.saved")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SAVED",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "GRAPH_ENTRY_LABELS",
    "GRAPH_VALIDATION",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "DefinitionCheck",
    "GraphEntryLabels",
    "GraphValidationSource",
    "SavedDefinition",
    "SecretRulesReader",
    "WarningSource",
    "WorkspaceSettingsReader",
]
