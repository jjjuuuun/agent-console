"""mod-runs의 공개 포트·토픽(이름 = 포트, design §3R.1.2·§3R.1.3·§3R.1.5).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 아래 프로토콜은
이 모듈이 **받는** 쪽의 모양(소비자 프로토콜)이다.

제공:

- ``runs.starter``: 실행 시작·검증·취소(``RunService`` — ``start_run``·``check``·``engine_issues``·
  ``cancel``·``current_services``·``shutdown``).
- ``runs.reader``: Run·NodeRun 조회(저장소 Run 리포지토리 — ``get``·``list``·``list_node_runs``).
- ``runs.events``: 실행 이벤트 조회(저장소 이벤트 리포지토리 — ``list``·``last_seq``·
  ``latest_by_type``·``list_by_actor``).
- ``interactions.port``: 상호작용 조회·응답(``InteractionService``).
- ``secrets.redact``: ``(str) -> str`` 해석한 비밀 값(+ 의심 값) 가리기.
- ``server.warnings``(여러 제공자): 팀 규칙이 없을 때 ``team.rules_unavailable``, 실행 기록 저장소가
  메모리일 때 ``runs.storage_memory``.
- ``server.attributes``(여러 제공자): ``{"recovered_runs": n}``(``GET /server-info`` 속성).
- 토픽 ``runs.event``(``RunEvent``, 저장된 이벤트마다)·``interactions.updated``(``Interaction``).

받음:

- 필수 ``definitions.lookup``: 팀 구성 읽기(``DefinitionLookup`` — ``get``·``get_version``).
- 선택 ``runs.preparers``(여러 제공자): 실행 전 검사·준비(``RunPreparer``). 없으면 엔진 검증만.
  선택 메서드 ``preflight``(``RunPreflight``)가 있으면 실행을 만들기 전 사전 점검을 한다.
  선택 메서드 ``annotate_issues``(``RunIssueAnnotator``)가 있으면 검증 이슈에 해결 버튼 등을 붙인다.
- 선택 ``runs.services``(여러 제공자): 노드 서비스 공급(``RunServiceProvider``).
- 선택 ``runs.scopes``(여러 제공자): 실행 범위(``RunScoper``, 5.2R.34). 실행을 시작할 때 요청의
  ``project_id``(불투명 문자열)로 이 Run에만 더할 노드 서비스·경고를 정한다(예: 프로젝트 설정 층).
  검사·준비보다 먼저 부르므로 준비자도 그 서비스를 본다. 없으면 범위 없이 실행한다.
- 선택 ``runs.resume_handlers``(여러 제공자): 이어 가기 처리기(``ResumeHandler``). 받는 처리기가
  없으면 일반 실행으로 새 Run을 시작한다.
- 선택 ``workspace.settings``: 공통 설정(``secrets.redact_suspected_in_logs``).
- 선택 ``secrets.rules``: 비밀 의심 규칙(``redact_suspected``가 있는 객체를 돌려주는 함수).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from agent_console_contracts import (
    DelegationSettings,
    ErrorInfo,
    FlowSettings,
    Graph,
    Interaction,
    InteractionGrant,
    InteractionSettings,
    Issue,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_modkit import PortKey, Topic
from agent_console_runtime import ResumeStart, ServiceKey, Services

if TYPE_CHECKING:
    from .interactions import InteractionService
    from .service import RunService


class StoredLike(Protocol):
    """정의 원문 하나(``agent_console_store.StoredDefinition``이 만족)."""

    @property
    def document(self) -> Mapping[str, Any]: ...


class VersionLike(Protocol):
    """정의 버전 하나(``agent_console_store`` 버전 기록이 만족)."""

    @property
    def content(self) -> Mapping[str, Any] | None: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기(``definitions.lookup``). 없으면 저장소 예외(``StoreError``)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...

    def get_version(self, kind: str, id: str, version_hash: str) -> VersionLike: ...


@dataclass(frozen=True)
class RunEnvironment:
    """노드 서비스 공급자에게 넘기는 실행 환경(설치자 설정 ``working_directory`` 등).

    Attributes:
        working_directory: 에이전트 작업 폴더(실행 범위의 기준).
        run_files_root: 실행 묶음 파일 폴더(노드마다 ``<root>/<run>/<node>/``).
    """

    working_directory: Path
    run_files_root: Path


@runtime_checkable
class RunServiceProvider(Protocol):
    """``runs.services`` 항목: 노드에 넘길 서비스(키는 노드 플러그인이 정한다, 엔진은 모른다)."""

    def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
        """지금 넘길 서비스. 실행마다 부른다(공통 설정이 바뀌면 값도 바뀔 수 있다)."""
        ...


@dataclass(frozen=True)
class RunPreparation:
    """준비 결과(엔진 시작 인자). 여러 준비자의 결과는 순서대로 합친다(``grants``는 덮어쓰기,
    ``interaction_settings``·``flow_settings``·``delegation_settings``는 None이 아닌 마지막 값,
    ``run_context``는 키별 덮어쓰기)."""

    grants: Mapping[str, InteractionGrant] = field(default_factory=dict)
    interaction_settings: InteractionSettings | None = None
    flow_settings: FlowSettings | None = None
    """반복·실행 한도(``GraphRuntime.start(flow_settings=)``, design §5R.4). None = 엔진 기본값."""
    delegation_settings: DelegationSettings | None = None
    """위임 설정(``GraphRuntime.start(delegation_settings=)``, 실행 중 위임 깊이 한도, design
    §5R.6). None = 엔진 기본값."""
    run_context: Mapping[str, Any] = field(default_factory=dict)
    """``run.started`` payload에 더할 값(``GraphRuntime.start(run_context=)``, 예: Run의 유효 작업
    폴더 ``cwd``, 5.2R.34). 실행 모듈은 뜻을 모른다."""


class PreparationLike(Protocol):
    """준비 결과 모양(``RunPreparation``·``ac-teams.RunPreparation``이 만족).

    선택 속성 ``flow_settings: FlowSettings | None``(5R.5)·``delegation_settings:
    DelegationSettings | None``(5R.6)·``run_context: Mapping[str, Any]``(5.2R.34)은 없어도 된다
    (있으면 실행 서비스가 읽는다).
    """

    @property
    def grants(self) -> Mapping[str, InteractionGrant]: ...

    @property
    def interaction_settings(self) -> InteractionSettings | None: ...


@runtime_checkable
class RunPreparer(Protocol):
    """``runs.preparers`` 항목: 실행 전 검사(엔진 검증 뒤)와 준비."""

    def check(
        self,
        graph: Graph,
        engine_issues: Sequence[Issue],
        services: Services,
        *,
        strict: bool,
    ) -> Sequence[Issue]:
        """엔진 이슈 뒤에 붙일 이슈(엔진 이슈와 같은 뜻이면 빼고 돌려준다).

        Args:
            strict: 참이면(실행 시작) 계산 오류를 그대로 던진다. 거짓이면(검증 응답) 오류를
                기록하고 빈 목록을 돌려줘도 된다.
        """
        ...

    def prepare(self, graph: Graph, services: Services) -> PreparationLike:
        """검사를 통과한 그래프의 시작 인자(허용 상호작용·상호작용 대기 설정)."""
        ...


@runtime_checkable
class RunPreflight(Protocol):
    """``runs.preparers`` 항목의 **선택** 메서드(5.2R.4): 실행을 만들기 직전 사전 점검.

    준비자가 이 메서드를 가지면 실행 시작(일반 실행·이어 가기·대화 턴)마다 차단 이슈 검사 뒤에
    부른다. ``ErrorInfo``를 돌려주면 Run을 만들지 않고 그 오류(``RunPreflightError``, HTTP 상태는
    코드로)를 낸다. 자식 Run(노드의 ``run_child``)은 부르지 않는다(노드 실패로 남는다).
    """

    def preflight(self, graph: Graph, services: Services) -> ErrorInfo | None:
        """막아야 하면 오류 본문(코드·사용자 문구·상세·해결 버튼), 아니면 None."""
        ...


@runtime_checkable
class RunIssueAnnotator(Protocol):
    """``runs.preparers`` 항목의 **선택** 메서드(5.2R.5): 검증 이슈 꾸미기.

    엔진 검증 + 준비자 검사를 모두 모은 뒤(검증 응답·실행 차단 모두) 준비자 순서대로 부른다.
    이슈의 뜻(코드·심각도·위치)은 바꾸지 않고 해결 버튼(``Issue.fix``) 같은 화면 정보만 더한다.
    예외는 기록하고 원래 이슈를 쓴다.
    """

    def annotate_issues(self, graph: Graph, issues: Sequence[Issue]) -> Sequence[Issue]:
        """같은 순서·같은 수의 이슈(꾸민 것)."""
        ...


@dataclass(frozen=True)
class RunScope:
    """실행 범위 결과(``runs.scopes`` 항목이 돌려주는 모양의 예 — 같은 속성이면 무엇이든 된다).

    Attributes:
        services: 이 Run(과 자식 Run)에만 더할 노드 서비스(뒤 공급자가 이긴다).
        warnings: 실행을 막지 않는 경고. Run 이벤트 ``log.warning``으로 남는다.
    """

    services: Mapping[ServiceKey[Any], Any] = field(default_factory=dict)
    warnings: Sequence[Issue] = ()


class RunScopeLike(Protocol):
    """``RunScoper.scope_run`` 결과 모양(``RunScope``가 만족)."""

    @property
    def services(self) -> Mapping[ServiceKey[Any], Any]: ...

    @property
    def warnings(self) -> Sequence[Issue]: ...


@runtime_checkable
class RunScoper(Protocol):
    """``runs.scopes`` 항목: 실행 범위(5.2R.34).

    실행 시작(일반 실행·이어 가기·대화 턴)마다 검사·사전 점검·준비보다 먼저 부른다. 자식 Run은
    부르지 않는다(부모 서비스를 물려받는다). 예외는 기록하고 그 공급자를 건너뛴다(실행은 범위
    없이 계속한다).
    """

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScopeLike | None:
        """이 Run에 더할 서비스·경고. 할 일이 없으면 None.

        Args:
            project_id: 요청의 ``Run.project_id``(불투명 문자열, 없으면 None).
        """
        ...


@runtime_checkable
class ResumeHandler(Protocol):
    """``runs.resume_handlers`` 항목: 특정 Run의 이어 가기를 맡는다(예: 대화 턴)."""

    def accepts(self, run: Run) -> bool:
        """이 Run의 이어 가기를 맡는가."""
        ...

    def resume(self, request: ResumeStart) -> Awaitable[Run]:
        """새 Run을 시작한다(``origin``·``resumed_from`` 기록은 처리기 몫)."""
        ...


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
"""``workspace.settings`` 포트 모양."""


class SuspectedRules(Protocol):
    """``secrets.rules``가 돌려주는 규칙의 쓰는 부분."""

    def redact_suspected(self, text: str) -> str: ...


type SecretRulesReader = Callable[[], SuspectedRules]
"""``secrets.rules`` 포트 모양."""

type Redactor = Callable[[str], str]
"""``secrets.redact`` 포트 모양."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

type AttributeSource = Callable[[], Mapping[str, Any]]
"""``server.attributes`` 포트 모양(``GET /server-info`` ``attributes``에 더해진다)."""


RUNS_STARTER: PortKey[RunService] = PortKey("runs.starter", "실행 시작·검증·취소")
RUNS_READER: PortKey[Any] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[Any] = PortKey("runs.events", "실행 이벤트 조회")
INTERACTIONS_PORT: PortKey[InteractionService] = PortKey("interactions.port", "상호작용 조회·응답")
SECRET_REDACT: PortKey[Redactor] = PortKey("secrets.redact", "해석한 비밀 값 가리기")
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
SERVER_ATTRIBUTES: PortKey[AttributeSource] = PortKey(
    "server.attributes", "서버 정보 속성", multi=True
)
DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
RUN_PREPARERS: PortKey[RunPreparer] = PortKey("runs.preparers", "실행 전 검사·준비", multi=True)
RUN_SERVICES: PortKey[RunServiceProvider] = PortKey("runs.services", "노드 서비스 공급", multi=True)
RUN_SCOPES: PortKey[RunScoper] = PortKey("runs.scopes", "실행 범위(요청 project_id)", multi=True)
RESUME_HANDLERS: PortKey[ResumeHandler] = PortKey(
    "runs.resume_handlers", "이어 가기 처리기", multi=True
)
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")

RUNS_EVENT: Topic[RunEvent] = Topic("runs.event")
"""저장이 끝난 실행 이벤트(전부). 구독자는 필요한 것만 거른다."""
INTERACTIONS_UPDATED: Topic[Interaction] = Topic("interactions.updated")
"""상호작용이 열리거나 닫힐 때(저장본)."""

__all__ = [
    "DEFINITIONS_LOOKUP",
    "INTERACTIONS_PORT",
    "INTERACTIONS_UPDATED",
    "RESUME_HANDLERS",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "RUNS_STARTER",
    "RUN_PREPARERS",
    "RUN_SCOPES",
    "RUN_SERVICES",
    "SECRET_REDACT",
    "SECRET_RULES",
    "SERVER_ATTRIBUTES",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "AttributeSource",
    "DefinitionLookup",
    "PreparationLike",
    "Redactor",
    "ResumeHandler",
    "RunEnvironment",
    "RunIssueAnnotator",
    "RunPreflight",
    "RunPreparation",
    "RunPreparer",
    "RunScope",
    "RunScopeLike",
    "RunScoper",
    "RunServiceProvider",
    "SecretRulesReader",
    "StoredLike",
    "SuspectedRules",
    "VersionLike",
    "WarningSource",
    "WorkspaceSettingsReader",
]
