"""실행 서비스(``runs.starter``): 검증 → 사전 점검 → 준비 → ``GraphRuntime.start``, 취소, 이어 가기,
종료.

엔진은 노드 타입·백엔드·팀 의미를 모른다. 팀 규칙은 ``runs.preparers``, 노드 서비스는
``runs.services``, 대화 턴 이어 가기 같은 특수 경로는 ``runs.resume_handlers``로 들어온다.
준비자가 하나도 없으면 엔진 검증만으로 실행한다(``team.rules_unavailable`` 경고).

자식 Run(노드의 ``ctx.run_child``, design §5R.7)도 같은 검사·준비를 거친다: 서비스가 엔진의
자식 Run 준비자(``GraphRuntime.child_preparer``)에 ``prepare_child``를 꽂는다.

정의 조회 출처(5.7R.33y): ``runs.scopes`` 항목의 선택 메서드 ``run_definitions``가 Run의 출처를 주면
루트 그래프(현재·버전)를 그 출처에서 읽고, 노드 서비스 공급자에게 ``RunEnvironment.definitions``로,
노드·준비자·자식 Run에게 서비스 ``RUN_DEFINITIONS``로 넘긴다. 출처를 준 공급자가 없으면
``definitions.lookup`` 그대로다(서비스 ``RUN_DEFINITIONS`` 없음).

기록 자리(5.7R.33y2): ``records``(``SpaceRecorder``)가 공간 포트를 가졌으면 ``project_id``가 있는
Run은 그 프로젝트 기록 DB에 쓴다. 시작 전에 그 기록 DB를 쓸 수 있는지 확인하고(못 쓰면 409
``project.records_unavailable``, 모르는 프로젝트 404 ``project.not_found`` - Run을 만들지 않는다,
앱 DB로 대신 쓰지 않는다), 조회·이어 가기·[끊긴 것으로 표시]는 ``project_id``로 그 공간을 본다.
"""

from __future__ import annotations

import asyncio
import builtins
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from agent_console_conditions import operator_descriptors
from agent_console_contracts import (
    BackendDescriptor,
    ConditionOperatorDescriptor,
    DelegationSettings,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    ErrorCodes,
    ErrorInfo,
    FlowSettings,
    Graph,
    InteractionGrant,
    InteractionKindDescriptor,
    InteractionSettings,
    Issue,
    NodeTypeDescriptor,
    Run,
)
from agent_console_graph import graph_hash
from agent_console_runtime import (
    ChildRunPreparation,
    ChildRunRequest,
    GraphRuntime,
    GraphValidationError,
    Registries,
    ResumeService,
    ResumeStart,
    RunHandle,
    ServiceKey,
    Services,
    edge_type_descriptors,
    node_type_descriptors,
)
from agent_console_store import NotFound, RecordsUnavailable, StoreError, UnknownSpace

from .errors import DefinitionReadError, RunPreflightError, issues_from_errors
from .plugins import condition_operators
from .ports import (
    RUN_DEFINITIONS,
    DefinitionLookup,
    DefinitionSource,
    ResumeHandler,
    RunDefinitionsScoper,
    RunEnvironment,
    RunIssueAnnotator,
    RunPreflight,
    RunPreparer,
    RunScoper,
    RunServiceProvider,
)
from .records import UNFINISHED, SpaceRecorder, interrupt_run

GRAPH_KIND = "graph"
"""정의 저장소에서 팀 구성 종류 이름(``agent_console_store.GRAPH_KIND.name``과 같다)."""

MARK_INTERRUPTED_MESSAGE = "사용자가 끊긴 것으로 표시했습니다"
"""[끊긴 것으로 표시]로 정리한 Run의 ``error.message``."""

TEAM_RULES_UNAVAILABLE = "team.rules_unavailable"
"""경고 코드: 실행 전 준비자(팀 규칙)가 없어 엔진 검증만으로 실행한다."""

_log = logging.getLogger("agent_console_mod_runs")


@dataclass(frozen=True)
class _Prepared:
    """준비자 결과를 합친 값(엔진 시작 인자)."""

    grants: dict[str, InteractionGrant]
    interaction: InteractionSettings | None
    flow: FlowSettings | None
    delegation: DelegationSettings | None
    context: dict[str, Any]


def blocks_run(issue: Issue) -> bool:
    """실행을 막는 이슈인가: ``issue.blocks_run``, 없으면 severity가 error인지(계약 규칙)."""
    return issue.blocks_run if issue.blocks_run is not None else issue.severity == "error"


class RunService:
    """실행 시작·검증·취소·이어 가기·종료(``runs.starter``).

    Args:
        runtime: 엔진(레지스트리·저장소·이벤트 발행이 붙어 있다).
        runs: Run 조회(저장소 Run 리포지토리).
        events: 이벤트 조회(저장소 이벤트 리포지토리, 이어 가기 선택지).
        lookup: 팀 구성 읽기(``definitions.lookup``).
        environment: 노드 서비스 공급자에게 넘길 실행 환경.
        preparers: 지금 실행 전 준비자 목록을 돌려주는 함수(``runs.preparers``).
        providers: 지금 노드 서비스 공급자 목록(``runs.services``).
        scopes: 지금 실행 범위 공급자 목록(``runs.scopes``, 요청 ``project_id`` → 이 Run의 서비스·
            경고).
        resume_handlers: 지금 이어 가기 처리기 목록(``runs.resume_handlers``).
        before_use: 검증·시작 직전에 부르는 함수(예: 기록 가리기 규칙 갱신).
        resume_origin: 처리기가 맡지 않은 이어 가기 Run의 ``origin``.
        shutdown_timeout: 종료 때 실행 중 Run 정리를 기다리는 최대 초.
        records: 기록 자리(``SpaceRecorder``, 엔진에 넘긴 것과 같은 객체). None이면 ``runs``만 본다.
    """

    def __init__(
        self,
        runtime: GraphRuntime,
        runs: Any,
        events: Any,
        lookup: DefinitionLookup,
        *,
        environment: RunEnvironment,
        preparers: Callable[[], Sequence[RunPreparer]] = list,
        providers: Callable[[], Sequence[RunServiceProvider]] = list,
        scopes: Callable[[], Sequence[RunScoper]] = list,
        resume_handlers: Callable[[], Sequence[ResumeHandler]] = list,
        before_use: Callable[[], None] = lambda: None,
        resume_origin: str = "resume",
        shutdown_timeout: float = 10.0,
        records: SpaceRecorder | None = None,
    ) -> None:
        self.runtime = runtime
        self.records = records
        self._events = events
        self._runs = runs
        self._lookup = lookup
        self.environment = environment
        self._preparers = preparers
        self._providers = providers
        self._scopes = scopes
        self._resume_handlers = resume_handlers
        self._before_use = before_use
        self._resume_origin = resume_origin
        self._shutdown_timeout = shutdown_timeout
        self._closed: asyncio.Future[bool] | None = None
        self.recovered: list[str] = []
        """시작 때 정리한 이전 프로세스의 Run id(``recover_unfinished_runs``)."""
        self.resume = ResumeService(
            runs,
            events,
            graph_of=self.graph_of_run,
            node_types=self.node_types,
            starter=self._start_resumed,
        )
        """끊긴 실행 이어 가기(선택지·새 Run 시작, design §2R.10)."""
        runtime.child_preparer = self.prepare_child

    @property
    def registries(self) -> Registries:
        return self.runtime.registries

    # ------------------------------------------------------------ 정의

    def definitions_for(self, project_id: str | None, graph_id: str) -> DefinitionSource | None:
        """Run의 정의 조회 출처(``runs.scopes``의 선택 메서드 ``run_definitions``, 뒤 공급자가
        이긴다).

        None이면 ``project_id``가 없거나 정한 공급자가 없다(``definitions.lookup``을 쓴다). 공급자
        예외는 기록하고 건너뛴다.

        Raises:
            RunPreflightError: 공급자가 오류 본문을 돌려줬다(Run을 만들지 않는다).
        """
        if not project_id:
            return None
        found: DefinitionSource | None = None
        for scoper in self._scopes():
            if not isinstance(scoper, RunDefinitionsScoper):
                continue
            try:
                result = scoper.run_definitions(project_id, graph_id)
            except Exception:
                _log.exception("정의 출처 계산 실패: %s", type(scoper).__name__)
                continue
            if isinstance(result, ErrorInfo):
                raise RunPreflightError(result)
            if result is not None:
                found = result
        return found

    def load_graph(
        self, graph_id: str, version_hash: str | None = None, *, project_id: str | None = None
    ) -> Graph:
        """팀 구성(현재 또는 그 버전). ``project_id``가 있으면 그 Run의 정의 출처에서 읽는다.

        Raises:
            DefinitionReadError: 없거나(``not_found``) 읽을 수 없거나 계약에 맞지 않는다.
            RunPreflightError: 정의 출처 공급자가 막았다.
        """
        source = self.definitions_for(project_id, graph_id)
        return self._read_graph(source or self._lookup, graph_id, version_hash)

    @staticmethod
    def _read_graph(source: DefinitionLookup, graph_id: str, version_hash: str | None) -> Graph:
        try:
            if version_hash is None:
                document: Mapping[str, Any] = source.get(GRAPH_KIND, graph_id).document
            else:
                content = source.get_version(GRAPH_KIND, graph_id, version_hash).content
                document = content or {}
            return Graph.model_validate(document)
        except StoreError as exc:
            raise DefinitionReadError(exc.code, str(exc)) from None
        except ValidationError as exc:
            issues = issues_from_errors(exc.errors(include_input=False, include_url=False))
            raise DefinitionReadError(
                ErrorCodes.VALIDATION_FAILED, "팀 구성 파일이 계약 형식에 맞지 않습니다", issues
            ) from None

    def find_graph(self, graph_id: str, *, project_id: str | None = None) -> Graph | None:
        """지금 팀 구성(읽을 수 없거나 출처 공급자가 막으면 None)."""
        try:
            return self.load_graph(graph_id, project_id=project_id)
        except (DefinitionReadError, RunPreflightError):
            return None

    def graph_of_run(self, run: Run) -> Graph | None:
        """Run 당시 팀 구성(버전 이력). 이력에 없으면 현재 정의가 같은 버전일 때만 그것을 쓴다.

        Run에 ``project_id``가 있으면 그 Run의 정의 출처(``definitions_for``)에서 찾는다.
        """
        try:
            scoped = self.definitions_for(run.project_id, run.graph_id)
        except RunPreflightError:
            return None
        source = scoped or self._lookup
        try:
            version = source.get_version(GRAPH_KIND, run.graph_id, run.graph_version)
            if version.content is not None:
                return Graph.model_validate(version.content)
        except (NotFound, StoreError, ValueError):
            pass
        try:
            current: Graph | None = self._read_graph(source, run.graph_id, None)
        except DefinitionReadError:
            current = None
        if current is not None and graph_hash(current) == run.graph_version:
            return current
        return None

    # ------------------------------------------------------------ 서비스·검증

    def current_services(self, definitions: DefinitionSource | None = None) -> Services:
        """지금 노드 서비스(공급자들의 값을 순서대로 합친 것, 뒤 공급자가 이긴다).

        Args:
            definitions: 이 Run의 정의 조회 출처(``definitions_for``). 있으면 공급자에게
                ``RunEnvironment.definitions``로 넘기고 서비스 ``RUN_DEFINITIONS``를 더한다(엔진
                기본 서비스는 바꾸지 않는다). None이면 지금과 같다.
        """
        self._before_use()
        env = (
            self.environment
            if definitions is None
            else replace(self.environment, definitions=definitions)
        )
        items: dict[ServiceKey[Any], Any] = {}
        for provider in self._providers():
            try:
                items.update(provider.services(env))
            except Exception:
                _log.exception("노드 서비스 공급자 실패: %s", type(provider).__name__)
        if definitions is not None:
            items[RUN_DEFINITIONS] = definitions
            return Services(items)
        services = Services(items)
        self.runtime.services = services
        return services

    @property
    def has_preparers(self) -> bool:
        """실행 전 준비자(팀 규칙 등)가 있는가."""
        return bool(self._preparers())

    def engine_issues(self, graph: Graph, services: Services | None = None) -> list[Issue]:
        """엔진 그래프 검증(등록된 타입 기준)."""
        return self.runtime.validate(graph, services=services or self.current_services())

    def _issues(self, graph: Graph, services: Services, *, strict: bool) -> list[Issue]:
        engine = self.runtime.validate(graph, services=services)
        extra: list[Issue] = []
        for preparer in self._preparers():
            try:
                extra.extend(preparer.check(graph, engine, services, strict=strict))
            except Exception:
                if strict and not any(blocks_run(i) for i in engine):
                    raise  # 검사 없이 시작하지 않는다
                _log.exception("실행 전 검사 실패: %s", graph.id)
        return self._annotate(graph, [*engine, *extra])

    def _annotate(self, graph: Graph, issues: list[Issue]) -> list[Issue]:
        """준비자의 선택 메서드 ``annotate_issues``로 이슈를 꾸민다(해결 버튼 등, 실패는 기록만)."""
        for preparer in self._preparers():
            if not isinstance(preparer, RunIssueAnnotator):
                continue
            try:
                annotated = list(preparer.annotate_issues(graph, issues))
            except Exception:
                _log.exception("검증 이슈 꾸미기 실패: %s", graph.id)
                continue
            if len(annotated) == len(issues):
                issues = annotated
        return issues

    def check(self, graph: Graph) -> list[Issue]:
        """저장 전·후 검증: 엔진 검증 + 준비자 검사(이슈가 있어도 돌려준다)."""
        return self._issues(graph, self.current_services(), strict=False)

    def _raise_blockers(self, graph: Graph, services: Services) -> None:
        blockers = [i for i in self._issues(graph, services, strict=True) if blocks_run(i)]
        if blockers:
            raise GraphValidationError(blockers)

    def preflight(self, graph: Graph, services: Services | None = None) -> ErrorInfo | None:
        """실행을 만들기 전 사전 점검(준비자의 선택 메서드 ``preflight``, 첫 오류).

        점검 계산이 예외를 내면 기록하고 건너뛴다(실행은 노드 단계에서 원래대로 실패한다).
        """
        current = services if services is not None else self.current_services()
        for preparer in self._preparers():
            if not isinstance(preparer, RunPreflight):
                continue
            try:
                error = preparer.preflight(graph, current)
            except Exception:
                _log.exception("실행 전 사전 점검 실패: %s", graph.id)
                continue
            if error is not None:
                return error
        return None

    def _raise_preflight(self, graph: Graph, services: Services) -> None:
        error = self.preflight(graph, services)
        if error is not None:
            raise RunPreflightError(error)

    def scope(
        self, graph: Graph, services: Services, project_id: str | None
    ) -> tuple[Services, list[Issue]]:
        """실행 범위 공급자(``runs.scopes``)들의 서비스를 더한 사본과 경고(순서대로, 실패는 기록하고
        건너뛴다).

        Raises:
            RunPreflightError: 공급자 결과의 선택 속성 ``errors``(X26 거부, 5.7R.33g)에 오류가
                있다(첫 오류). Run을 만들지 않는다.
        """
        warnings: list[Issue] = []
        for scoper in self._scopes():
            try:
                found = scoper.scope_run(graph, services, project_id=project_id)
            except Exception:
                _log.exception("실행 범위 계산 실패: %s", type(scoper).__name__)
                continue
            if found is None:
                continue
            errors = getattr(found, "errors", None) or ()  # 선택 속성(5.7R.33g)
            for error in errors:
                if isinstance(error, ErrorInfo):
                    raise RunPreflightError(error)
            for key, value in found.services.items():
                services = services.with_(key, value)
            warnings.extend(found.warnings)
        return services, warnings

    def _prepare(self, graph: Graph, services: Services) -> _Prepared:
        """준비자들의 결과를 순서대로 합친다(``grants``·``run_context``는 덮어쓰기, 설정은 None이
        아닌 마지막 값)."""
        grants: dict[str, InteractionGrant] = {}
        interaction: InteractionSettings | None = None
        flow: FlowSettings | None = None
        delegation: DelegationSettings | None = None
        context: dict[str, Any] = {}
        for preparer in self._preparers():
            prep = preparer.prepare(graph, services)
            grants.update(prep.grants)
            if prep.interaction_settings is not None:
                interaction = prep.interaction_settings
            # 선택 속성(5R.5 이전 준비자에는 없다)
            prep_flow = getattr(prep, "flow_settings", None)
            if isinstance(prep_flow, FlowSettings):
                flow = prep_flow
            prep_delegation = getattr(prep, "delegation_settings", None)  # 선택 속성(5R.6)
            if isinstance(prep_delegation, DelegationSettings):
                delegation = prep_delegation
            prep_context = getattr(prep, "run_context", None)  # 선택 속성(5.2R.34)
            if isinstance(prep_context, Mapping):
                context.update(prep_context)
        return _Prepared(grants, interaction, flow, delegation, context)

    def prepare_child(self, request: ChildRunRequest) -> ChildRunPreparation:
        """자식 Run 준비(엔진 ``ChildRunPreparer``, design §5R.7): 일반 Run과 같은 검사·준비.

        서비스는 엔진이 넘긴 것(부모 Run 서비스 + ``run_child(services=)``)을 그대로 쓴다. 차단
        이슈가 있으면 ``GraphValidationError``(노드는 ``validation_failed`` 실패 결과를 받는다).
        준비자가 정하지 않은 설정은 None이라 엔진이 부모 Run 값을 물려준다.
        """
        services = request.services
        self._raise_blockers(request.graph, services)
        prep = self._prepare(request.graph, services)
        return ChildRunPreparation(
            interaction_grants=prep.grants,
            interaction_settings=prep.interaction,
            flow_settings=prep.flow,
            delegation_settings=prep.delegation,
            checked=True,
            run_context=prep.context or None,
        )

    # ------------------------------------------------------------ 실행

    async def start_graph(
        self,
        graph_id: str,
        input: Mapping[str, Any] | None = None,
        *,
        version_hash: str | None = None,
        origin: str = "api",
        project_id: str | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> RunHandle:
        """저장된 팀 구성을 id로 실행한다(``POST /runs``): 정의 출처를 정하고 그 출처에서 그래프를
        읽은 뒤 ``start_run``과 같이 시작한다(출처는 한 번만 정한다). ``labels`` = 루트 Run의
        ``Run.labels``(6R.12, 상한 검사는 ``CreateRunRequest``가 했다).

        Raises:
            DefinitionReadError: 그래프를 읽지 못했다(그 출처에 없으면 ``not_found``).
            RunPreflightError: 정의 출처 공급자·준비자 사전 점검이 막았다.
            GraphValidationError: 실행을 막는 이슈.
        """
        source = self.definitions_for(project_id, graph_id)
        graph = self._read_graph(source or self._lookup, graph_id, version_hash)
        return await self._start(
            graph, input, origin=origin, project_id=project_id, definitions=source, labels=labels
        )

    async def start_run(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = "api",
        conversation_id: str | None = None,
        extra_services: Mapping[ServiceKey[Any], Any] | None = None,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        resumed_from: str | None = None,
        project_id: str | None = None,
        run_context: Mapping[str, Any] | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> RunHandle:
        """팀 구성을 실행한다: 검증(차단 이슈) → 준비(``runs.preparers``) → ``GraphRuntime.start``.

        Args:
            extra_services: 이 Run에만 더할 노드 서비스(예: 대화 턴의 이어 쓸 세션).
            seed: 이어 가기(§2R.10) 노드 입력. ``resumed_from``: 원래 Run id.
            project_id: ``Run.project_id``로 기록한다(불투명 문자열, 자식 Run은 부모 값을 받는다).
                실행 범위 공급자(``runs.scopes``)에 넘겨 이 Run의 서비스·경고를 정한다.
            run_context: ``run.started`` payload에 더할 호출자 값(예: 대화 턴의 세션 이어 가기
                안내 ``chat_sessions``, 5.7R.33y3). 같은 키는 준비자 값이 이긴다.
            labels: 루트 Run 라벨 ``Run.labels``(6R.12). 상한은 호출자가 검사한다
                (``run_label_problems``).

        Raises:
            GraphValidationError: 실행을 막는 이슈. Run을 만들지 않는다.
            RunPreflightError: 준비자 사전 점검(예: ``backend.unresolved``)이나 정의 출처 공급자가
                막았다. Run을 만들지 않는다.
        """
        source = self.definitions_for(project_id, graph.id)
        return await self._start(
            graph,
            input,
            origin=origin,
            conversation_id=conversation_id,
            extra_services=extra_services,
            seed=seed,
            resumed_from=resumed_from,
            project_id=project_id,
            definitions=source,
            run_context=run_context,
            labels=labels,
        )

    async def _start(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None,
        *,
        origin: str,
        conversation_id: str | None = None,
        extra_services: Mapping[ServiceKey[Any], Any] | None = None,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        resumed_from: str | None = None,
        project_id: str | None = None,
        definitions: DefinitionSource | None = None,
        run_context: Mapping[str, Any] | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> RunHandle:
        services, scope_warnings = self.scope(graph, self.current_services(definitions), project_id)
        self.check_records(project_id)
        self._raise_blockers(graph, services)
        self._raise_preflight(graph, services)
        prep = self._prepare(graph, services)
        if extra_services:
            for key, value in extra_services.items():
                services = services.with_(key, value)
        return await self.runtime.start(
            graph,
            input,
            origin=origin,
            conversation_id=conversation_id,
            services=services,
            validate=False,  # 위에서 같은 검증을 했다
            interaction_grants=prep.grants,
            interaction_settings=prep.interaction,
            seed=seed,
            resumed_from=resumed_from,
            flow_settings=prep.flow,
            delegation_settings=prep.delegation,
            project_id=project_id,
            run_context={**(run_context or {}), **prep.context},
            start_warnings=scope_warnings,
            labels=labels,
        )

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        """실행 중 Run 취소 요청(처음 요청이면 True)."""
        return self.runtime.cancel(run_id, reason)

    def check_records(self, project_id: str | None) -> None:
        """그 프로젝트 기록 DB를 쓸 수 있는지 확인한다(없으면 만들고 계보를 올린다).

        ``project_id``가 없거나 기록 공간 포트가 없으면 아무것도 하지 않는다(호스트 DB).

        Raises:
            RunPreflightError: 쓸 수 없다(409 ``project.records_unavailable``, ``details.reason``)
                또는 모르는 프로젝트(404 ``project.not_found``). Run을 만들지 않는다.
        """
        records = self.records
        if not project_id or records is None or not records.spaced or records.records is None:
            return
        try:
            records.records.ensure_writable(project_id)
        except RecordsUnavailable as exc:
            raise RunPreflightError(
                ErrorInfo(
                    code=ErrorCodes.PROJECT_RECORDS_UNAVAILABLE,
                    message="이 프로젝트의 기록을 저장할 수 없어 실행을 시작하지 않았습니다",
                    details={**exc.details(), "project_id": project_id},
                )
            ) from None
        except (UnknownSpace, LookupError):
            raise RunPreflightError(
                ErrorInfo(
                    code=ErrorCodes.PROJECT_NOT_FOUND,
                    message="프로젝트를 찾을 수 없습니다",
                    details={"project_id": project_id},
                )
            ) from None

    def reader(self, project_id: str | None = None) -> Any:
        """읽기: ``project_id``가 있고 기록 공간이 있으면 그 공간에 묶인 읽기(``SpaceReader``),
        아니면 ``runs``(호스트 또는 기억한 자리)."""
        if self.records is not None:
            return self.records.for_project(project_id)
        return self._runs

    def current_run(self, run_id: str, project_id: str | None = None) -> Run | None:
        """실행 중이면 손잡이의 Run, 아니면 저장본(없으면 None). ``project_id``가 있으면 그 공간."""
        handle = self.runtime.get(run_id)
        if handle is not None:
            return handle.run
        if project_id is not None and self.records is not None:
            found_in: Run | None = self.records.for_project(project_id).get(run_id)
            return found_in
        found: Run | None = self._runs.get(run_id)
        return found

    def resume_for(self, project_id: str | None) -> ResumeService:
        """그 프로젝트 공간의 Run을 이어 가는 서비스(없으면 호스트 기본 ``resume``)."""
        if project_id is None or self.records is None or not self.records.spaced:
            return self.resume
        reader = self.records.for_project(project_id)
        return ResumeService(
            _ScopedRuns(reader),
            _ScopedEvents(reader),
            graph_of=self.graph_of_run,
            node_types=self.node_types,
            starter=self._start_resumed,
        )

    def mark_interrupted(self, run_id: str, project_id: str | None = None) -> Run | None:
        """끝나지 않은 Run을 끊긴 것으로 표시한다(다른 앱의 Run 포함, K33-30). 이 프로세스에서
        돌고 있으면 끊는다. 이미 끝났으면 그대로. 없으면 None.

        Raises:
            RunPreflightError: 그 공간에 쓸 수 없다(409 ``project.records_unavailable``).
        """
        handle = self.runtime.get(run_id)
        if handle is not None:
            handle.interrupt(MARK_INTERRUPTED_MESSAGE)
            return handle.run
        run = self.current_run(run_id, project_id)
        if run is None or run.status not in UNFINISHED:
            return run
        if project_id is not None and self.records is not None and self.records.spaced:
            self.check_records(project_id)
            assert self.records.records is not None
            storage = self.records.records.writer(project_id)
            done = interrupt_run(storage, run_id, message=MARK_INTERRUPTED_MESSAGE)
            return self.records.for_project(project_id).view(done) if done is not None else None
        host = self.records.host if self.records is not None else None
        if host is None:
            return run
        return interrupt_run(host, run_id, message=MARK_INTERRUPTED_MESSAGE)

    async def _start_resumed(self, request: ResumeStart) -> Run:
        for handler in self._resume_handlers():
            if handler.accepts(request.run):
                return await handler.resume(request)
        handle = await self.start_run(
            request.graph,
            request.run.input,
            origin=self._resume_origin,
            seed=request.seed,
            resumed_from=request.run.id,
            project_id=request.run.project_id,
        )
        return handle.run

    async def shutdown(self) -> None:
        """실행 중 Run을 "끊김"으로 정리한다(한 번만, 여러 번 불러도 같은 결과를 기다린다).

        정상 종료도 재시작 복구와 같은 결과(Run ``interrupted``, 대기 요청 ``expired``)라 채팅에서
        이어 갈 수 있다(§R14.5).
        """
        if self._closed is None:
            self._closed = asyncio.get_running_loop().create_future()
            try:
                done = await self.runtime.shutdown(
                    "서버가 종료되어 실행이 중단되었습니다",
                    timeout=self._shutdown_timeout,
                    interrupt=True,
                )
                if not done:
                    _log.warning(
                        "실행 정리가 %.1f초 안에 끝나지 않아 남은 Run을 강제 취소했습니다",
                        self._shutdown_timeout,
                    )
                self._closed.set_result(done)
            except BaseException as exc:
                self._closed.set_exception(exc)
                raise
            return
        await asyncio.shield(self._closed)

    # ------------------------------------------------------------ 디스크립터

    def node_types(self) -> list[NodeTypeDescriptor]:
        return node_type_descriptors(self.registries)

    def edge_types(self) -> list[EdgeTypeDescriptor]:
        return edge_type_descriptors(self.registries)

    def strategies(self) -> list[DelegationStrategyDescriptor]:
        return [e.item.descriptor for e in self.registries.delegation_strategies.list()]

    def interaction_kinds(self) -> list[InteractionKindDescriptor]:
        return [e.item.descriptor for e in self.registries.interaction_kinds.list()]

    def backends(self) -> list[BackendDescriptor]:
        return [e.item.descriptor for e in self.registries.backends.list()]

    def condition_operators(self) -> list[ConditionOperatorDescriptor]:
        """조건 연산자(X22) 디스크립터(id 순). 모듈은 연산자 이름을 모른다."""
        return operator_descriptors(condition_operators(self.registries))


class _ScopedRuns:
    """``ResumeService``가 쓰는 Run 읽기(공간에 묶인 읽기 위)."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    def get(self, run_id: str) -> Run | None:
        found: Run | None = self._reader.get(run_id)
        return found

    def list(self, **filters: Any) -> builtins.list[Run]:
        found: builtins.list[Run] = self._reader.list(**filters)
        return found

    def list_node_runs(self, run_id: str) -> builtins.list[Any]:
        found: builtins.list[Any] = self._reader.list_node_runs(run_id)
        return found


class _ScopedEvents:
    """``ResumeService``가 쓰는 이벤트 읽기(공간에 묶인 읽기 위)."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    def list(self, run_id: str, **filters: Any) -> builtins.list[Any]:
        found: builtins.list[Any] = self._reader.events(run_id, **filters)
        return found

    def last_seq(self, run_id: str) -> int:
        return int(self._reader.last_seq(run_id))


def team_rules_warning() -> Issue:
    """``team.rules_unavailable`` 경고(``GET /server-info``·시작 로그)."""
    return Issue(
        severity="warning",
        code=TEAM_RULES_UNAVAILABLE,
        message=(
            "실행 전 팀 규칙 검사(runs.preparers)를 주는 모듈이 없어 엔진 검증만으로 실행합니다"
        ),
    )


__all__ = [
    "GRAPH_KIND",
    "MARK_INTERRUPTED_MESSAGE",
    "TEAM_RULES_UNAVAILABLE",
    "RunService",
    "blocks_run",
    "team_rules_warning",
]
