"""NodeContext: 노드 구현이 실행 중 쓰는 모든 서비스의 통로(design §3.3)."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import BaseModel

from agent_console_contracts import (
    EdgeSpec,
    Graph,
    InteractionGrant,
    NodeRunStatus,
    NodeSpec,
    Run,
    RunEvent,
)
from agent_console_registry import Registry

from ._cancel import CancelToken
from ._children import ChildRunResult
from ._interactions import InteractionOutcome, InteractionRequest
from ._interfaces import Clock, ExecutionBackend, Incoming, NodeRunView
from ._journal import RunJournal
from ._registries import Registries
from ._replies import emit_replies
from ._secrets import SecretResolver
from ._services import ServiceKey, Services

RESERVED_EVENT_PREFIXES = ("run.", "node.", "edge.", "interaction.")
"""엔진만 내는 이벤트 type 접두어. 노드·백엔드는 이 이벤트를 직접 낼 수 없다."""

type RequestOpener = Callable[[NodeContext, InteractionRequest], Awaitable[InteractionOutcome]]
"""엔진이 `NodeContext`에 주는 상호작용 열기 함수(내부 연결용)."""


class NodeInvoker(Protocol):
    """엔진이 `NodeContext`에 주는 대상 노드 호출 함수(`ctx.invoke_node`의 구현, 내부 연결용)."""

    def __call__(
        self,
        ctx: NodeContext,
        node_id: str,
        inputs: Mapping[str, Any],
        *,
        by_edge: str,
        max_depth: int | None,
        tool_use_id: str | None = None,
    ) -> Awaitable[NodeRunView]: ...


class ChildRunner(Protocol):
    """엔진이 `NodeContext`에 주는 자식 Run 실행 함수(`ctx.run_child`의 구현, 내부 연결용)."""

    def __call__(
        self,
        ctx: NodeContext,
        graph: Graph,
        input: Mapping[str, Any] | None,
        *,
        graph_version: str | None,
        services: Mapping[ServiceKey[Any], Any] | None,
    ) -> Awaitable[ChildRunResult]: ...


class NodeContext:
    """노드 1회 실행 맥락. 노드는 전역·환경변수·파일 시스템 대신 이것만 쓴다.

    Attributes:
        run: 이 노드가 속한 Run(시작 시점 사본).
        graph: 실행 중인 그래프(Run 시작 시 고정된 버전).
        node: 노드 정의. `config`는 `node.config`(검증 통과).
        attempt, iteration: NodeRun 키. `iteration`은 반복 회차(0부터, 사이클 연결이 영역을 다시
            열 때마다 1씩 는다, design §5R.4).
        registries: 레지스트리 묶음(`backends`, `extension(name)` 등).
        services: 앱이 주입한 타입드 서비스(`services.require(KEY)`).
        secrets: 비밀 참조 해석기(`secrets.resolve("secret://name")`).
        cancel: Run 취소 토큰.
        clock: 시각 함수.
        actor: 이 노드 자리의 에이전트 정의 id(노드 타입 `actor_of` 훅, 없으면 None).
        interaction_grant: 이 노드가 열 수 있는 상호작용(Run 시작 때 받은 grant, 없으면 None).
            엔진은 이 값을 강제하지 않는다. 노드가 백엔드에 넘길 때 쓴다.
        previous_session_id: 같은 노드 직전 회차가 남긴 백엔드 세션 id(`NodeResult.
            backend_session_id`). 첫 회차이거나 없으면 None. 다음 회차가 같은 세션을 이어 쓸 때
            쓴다(design §5R.4 "대화 이어 쓰기", 이어 쓸지는 노드가 정한다). 위임자가 부른 노드면
            같은 Run에서 그 노드를 직전에 부른 호출의 세션 id다.
        call: 호출 회차(위임자가 `invoke_node`로 부른 NodeRun이면 0부터, 스케줄 실행은 0).
        invoked_by: 위임자가 불렀으면 위임자의 노드 경로, 스케줄 실행이면 None.

    `InteractivePort`(`request_input`)와 `BackendEventSink`(`emit`)를 만족한다.
    """

    def __init__(
        self,
        *,
        run: Run,
        graph: Graph,
        node: NodeSpec,
        attempt: int,
        iteration: int,
        registries: Registries,
        services: Services,
        secrets: SecretResolver,
        cancel: CancelToken,
        clock: Clock,
        journal: RunJournal,
        actor: str | None = None,
        interaction_grant: InteractionGrant | None = None,
        open_request: RequestOpener | None = None,
        incoming: Sequence[Incoming] = (),
        previous_session_id: str | None = None,
        node_path: Sequence[str] | None = None,
        call: int = 0,
        invoked_by: Sequence[str] | None = None,
        invoke: NodeInvoker | None = None,
        run_child: ChildRunner | None = None,
    ) -> None:
        self.run = run
        self.graph = graph
        self.node = node
        self.attempt = attempt
        self.iteration = iteration
        self.registries = registries
        self.services = services
        self.secrets = secrets
        self.cancel = cancel
        self.clock = clock
        self.actor = actor
        self.interaction_grant = interaction_grant
        self._journal = journal
        self._open_request = open_request
        self._incoming = tuple(incoming)
        self.previous_session_id = previous_session_id
        self._path = tuple(node_path) if node_path is not None else (node.id,)
        self.call = call
        self.invoked_by = list(invoked_by) if invoked_by is not None else None
        self._invoke = invoke
        self._run_child = run_child

    @property
    def config(self) -> Mapping[str, Any]:
        """노드 config."""
        return self.node.config

    @property
    def node_path(self) -> list[str]:
        """이 노드 이벤트의 `node_path`.

        스케줄 실행이면 `[node.id]`, 위임자가 부른 노드면 `[...위임자 경로, node.id]`.
        """
        return list(self._path)

    def child_path(self, node_id: str) -> list[str]:
        """이 노드 실행 안에서 부른 대상 노드의 `node_path`(`[이 노드, node_id]`, design §R3.4)."""
        return [*self.node_path, node_id]

    def incoming(self, port: str | None = None) -> list[Incoming]:
        """이 노드로 들어온 값(통과한 엣지마다 하나, 들어오는 엣지 목록 순서).

        `execute`의 `inputs`는 포트마다 첫 값만 담는다(호환). 같은 포트로 여러 엣지가 들어온 경우
        (join `all` 합류 등) 보낸 노드·엣지별 값을 모두 보려면 이것을 쓴다.

        Args:
            port: 입력 포트 이름. None이면 모든 포트.
        """
        return [i for i in self._incoming if port is None or i.port == port]

    @property
    def backends(self) -> Registry[ExecutionBackend]:
        """실행 백엔드 레지스트리."""
        return self.registries.backends

    def now(self) -> float:
        """현재 시각(주입된 clock)."""
        return self.clock()

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        raw: Any = None,
        evidence: str = "observed",
        actor: str | None = None,
        node_path: Sequence[str] | None = None,
    ) -> RunEvent:
        """이 노드의 이벤트를 낸다(`agent.*`, `log.warning`, 플러그인 type 등).

        머리 필드(run_id·seq·ts·attempt)는 엔진이 채운다. 저장 후 발행되며,
        이 호출은 기록 줄에 넣고 바로 돌아온다.

        Args:
            actor: 이벤트를 낸 에이전트 정의 id. 생략하면 이 노드의 `actor`.
            node_path: 생략하면 `node_path`. 하위 에이전트(위임 대상) 이벤트는
                `child_path(대상)`처럼                 이 노드 경로로 시작하는 더 긴 경로를 준다.

        Raises:
            ValueError: 엔진 예약 type(`run.*`, `node.*`, `edge.*`, `interaction.*`)이거나,
                `node_path`가 이 노드 경로로 시작하지 않을 때.
            pydantic.ValidationError: 알려진 type의 payload 형식이 틀렸을 때.
        """
        if type.startswith(RESERVED_EVENT_PREFIXES):
            raise ValueError(f"이벤트 type {type!r}는 엔진 전용입니다")
        path = self._own_path(node_path)
        return self._journal.event(
            type,
            payload,
            node_path=path,
            attempt=self.attempt,
            actor=actor if actor is not None else self.actor,
            raw=raw,
            evidence=evidence,
        )

    async def request_input(self, req: InteractionRequest) -> InteractionOutcome:
        """사용자에게 요청을 열고 닫힐 때까지 기다린다(live wait, design §R14.5).

        기다리는 동안 노드는 waiting이고 동시 실행 슬롯을 반납한다. 열린 요청이 모두 닫히면 슬롯을
        다시 얻고 running으로 돌아온 뒤 결과를 돌려준다. 한 노드가 여러 요청을 동시에 열 수 있다.
        만료·취소도 예외가 아니라 결과(`status`)다. 응답 원문은 메모리에서만 돌려주고
        저장·이벤트에는 비밀을 가린 값이 남는다.

        Args:
            req: 요청. `kind`는 `registries.interaction_kinds`에 등록된 종류여야 한다.
                서브에이전트 요청이면 `actor`와 `node_path=child_path(대상)`을 준다.

        Raises:
            UnknownExtensionError: 등록되지 않은 종류.
            InvalidSchemaError: 응답 스키마가 잘못되었다.
            ValueError: `node_path`가 이 노드 경로로 시작하지 않는다.
            RuntimeError: 엔진 밖에서 만든 맥락이라 요청을 열 수 없다.
        """
        if self._open_request is None:
            raise RuntimeError("이 맥락은 상호작용을 열 수 없습니다(엔진이 만든 맥락이 아님)")
        return await self._open_request(self, req)

    async def emit_replies(
        self,
        node_id: str,
        outputs: Mapping[str, Any],
        *,
        status: NodeRunStatus = "succeeded",
        actor: str | None = None,
    ) -> list[RunEvent]:
        """이 노드가 실행 안에서 부른 대상 노드(`node_id`)의 답변 연결을 평가해 `run.reply`를 낸다.

        대상은 스케줄되지 않으므로 엔진 대신 위임 방식이 결과마다 부른다
        (예: 서브에이전트 결과마다 답변, design §R3.1b).
        답변 연결 = 대상에서 나가는 `scheduling = exit` 엣지.
        이벤트의 `node_path`는 `child_path(node_id)`, actor는 주어진 값.

        Args:
            node_id: 대상 노드 id. 이 노드에서 `invocation`이 있는 연결을 따라 닿는 노드여야 한다.
            outputs: 대상 결과(포트 이름 → 값). 답변 엣지 타입이 소스 포트 값을 꺼낸다.
            status: 대상 결과 상태(엣지 타입이 보는 값).

        Returns:
            낸 `run.reply` 이벤트(통과한 답변 엣지가 없으면 빈 목록).

        Raises:
            ValueError: `node_id`가 이 노드의 호출 대상이 아닐 때.
        """
        if node_id not in self._invoked_nodes():
            raise ValueError(f"노드 {node_id!r}는 노드 {self.node.id!r}의 호출 대상이 아닙니다")
        spec = next(n for n in self.graph.nodes if n.id == node_id)
        view = NodeRunView(
            node_id=node_id,
            node_type=spec.type,
            status=status,
            outputs=MappingProxyType(dict(outputs)),
        )
        return emit_replies(
            self._journal,
            self.registries,
            [e for e in self.graph.edges if e.source.node == node_id and self._is_exit(e)],
            view,
            node_path=self.child_path(node_id),
            attempt=self.attempt,
            actor=actor,
        )

    async def invoke_node(
        self,
        node_id: str,
        inputs: Mapping[str, Any],
        *,
        by_edge: str,
        max_depth: int | None = None,
        tool_use_id: str | None = None,
    ) -> NodeRunView:
        """호출 대상 노드를 **자기 NodeRun**으로 실행하고 결과를 기다린다.

        위임 방식(X12, 예: 독립 위임 `host`)이 대상을 실행할 때 쓴다. 대상 노드 타입의 `execute`가
        스케줄되는 노드와 같은 길(설정·상호작용·이벤트·기록·취소)로 돈다.

        - 대상 NodeRun: `iteration` = 이 노드의 회차, `call` = 이 Run에서 그 노드를 부른
          순번(0부터), `invoked_by` = 이 노드 경로. 이벤트 `node_path` = `child_path(node_id)`.
        - 대상의 나가는 답변(`scheduling = exit`) 연결은 엔진이 평가해 `run.reply`를 낸다.
        - 같은 대상은 한 번에 하나씩(직렬) 돈다. 다른 대상은 동시에 돌 수 있다(런타임
          `max_concurrency` 안). 기다리는 동안 이 노드는 동시 실행 슬롯을 내놓는다.
        - 대상이 상호작용을 기다리고 이 노드에 다른 일이 없으면 Run은 `waiting`이다.
        - 취소는 이 Run의 취소 토큰을 따른다(대상 NodeRun은 `cancelled`).
        - 대상의 실패는 예외가 아니라 결과(`status = failed`)다. Run 실패로 세지 않는다(위임자가
          판단한다). 깊이 한도(`max_depth`·설정 `delegation.max_depth` 중 작은 값)를 넘거나
          위임 경로에 이미 있는 노드를 부르면 실행하지 않고 `failed` 결과
          (`error.code` = `delegation.depth_exceeded`·`delegation.cycle`)를 돌려준다.

        Args:
            node_id: 대상 노드 id.
            inputs: 대상 입력(포트 이름 → 값).
            by_edge: 이 노드 → 대상 연결 id. 디스크립터에 `invocation`이 있는 연결이어야 한다.
            max_depth: 위임 방식이 정한 깊이 한도(디스크립터 `max_depth`, None = 제한 없음).
            tool_use_id: 선택. 이 호출을 일으킨 위임 도구 호출 id(백엔드가 알려 준 값). 주면 대상
                NodeRun의 `node.*` 이벤트 payload `tool_use_id`에 실려, 위임자의 도구 호출 이벤트와
                대상 실행이 명시 id로 이어진다(design §5.5R.1 C7). 모르면 None.

        Returns:
            대상 NodeRun 결과(메모리 원본). 상태는 `succeeded`·`failed`·`skipped`·`waiting`·
            `cancelled`.

        Raises:
            ValueError: `by_edge`가 이 노드에서 `node_id`로 가는 `invocation` 연결이 아니거나 대상이
                실행할 수 없는 노드일 때.
            RuntimeError: 엔진 밖에서 만든 맥락이라 노드를 부를 수 없다.
        """
        if self._invoke is None:
            raise RuntimeError("이 맥락은 노드를 부를 수 없습니다(엔진이 만든 맥락이 아님)")
        return await self._invoke(
            self, node_id, inputs, by_edge=by_edge, max_depth=max_depth, tool_use_id=tool_use_id
        )

    async def run_child(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        *,
        graph_version: str | None = None,
        services: Mapping[ServiceKey[Any], Any] | None = None,
    ) -> ChildRunResult:
        """다른 그래프를 **자식 Run**으로 실행하고 끝날 때까지 기다린다(design §5R.7).

        중첩 팀 노드처럼 그래프 안에서 그래프를 실행하는 노드가 쓴다. 자식 Run은 일반 Run과 같은
        엔진·저장소·이벤트 발행·동시 실행 한도를 쓰고, 앱이 준 자식 Run 준비자
        (`GraphRuntime(child_preparer=)`)가 있으면 그것으로 준비한다(없으면 부모 값을 물려받음).

        - 자식 Run: `parent_run_id` = 이 Run, `parent_node_id` = 이 노드, `root_run_id` = 맨 위
          Run(손자도 루트 id). 대화 턴이 아니므로 `conversation_id`는 비우고, 자식 Run 안의
          상호작용에는 루트 대화 id와 `root_run_id`가 들어간다.
        - 부모 Run 이벤트 `run.child_started{child_run_id, node_id, graph_id}`·
          `run.child_finished{child_run_id, node_id, status}`(`node_path` = 이 노드 경로).
        - 기다리는 동안 이 노드는 동시 실행 슬롯을 내놓는다. 자식 Run이 상호작용만 기다리면
          부모 Run도 `waiting`이다. 부모 Run이 취소·끊기면 자식 Run도 취소·끊긴다.
        - 자식의 실패는 예외가 아니라 결과(`status`)다. 중첩 깊이(`delegation.max_nesting`,
          부모 Run 설정)를 넘거나(`team.nesting_exceeded`) 이미 경로에 있는 그래프를 다시 넣으면
          (`team.recursive`), 또는 준비·검증이 실패하면(`validation_failed`) 자식 Run을 만들지
          않고 `failed` 결과(`run_id = None`)를 돌려준다.
        - 사용량은 `ChildRunResult.totals`로 돌려준다. 부모 합계에 넣으려면 노드가
          `NodeResult.usage`로 돌려준다.

        Args:
            graph: 자식 그래프.
            input: 자식 Run 입력(입구 연결로 들어간다). 생략 = 빈 입력.
            graph_version: 주면 `graph_hash(graph)`와 같아야 한다(버전 고정 확인).
            services: 자식 Run에 더할(같은 키면 바꿀) 노드 서비스(예: 이어 쓸 세션). 부모 Run
                서비스 위에 얹은 것이 준비자 요청의 `services`다.

        Raises:
            ValueError: `graph_version`이 그래프 해시와 다르다.
            RuntimeError: 엔진 밖에서 만든 맥락이라 자식 Run을 만들 수 없다.
        """
        if self._run_child is None:
            raise RuntimeError("이 맥락은 자식 Run을 만들 수 없습니다(엔진이 만든 맥락이 아님)")
        return await self._run_child(
            self, graph, input, graph_version=graph_version, services=services
        )

    def _own_path(self, node_path: Sequence[str] | None) -> list[str]:
        own = self.node_path
        if node_path is None:
            return own
        path = list(node_path)
        if path[: len(own)] != own:
            raise ValueError(f"node_path {path!r}는 이 노드 경로 {own!r}로 시작해야 합니다")
        return path

    def _descriptor_of(self, edge: EdgeSpec) -> Any:
        try:
            return self.registries.edge_types.get(edge.kind).descriptor
        except Exception:
            return None

    def _is_exit(self, edge: EdgeSpec) -> bool:
        desc = self._descriptor_of(edge)
        return desc is not None and desc.scheduling == "exit"

    def _invoked_nodes(self) -> set[str]:
        """이 노드에서 `invocation` 연결을 따라 닿는 노드(이 노드 제외)."""
        found: set[str] = set()
        work = deque([self.node.id])
        while work:
            current = work.popleft()
            for edge in self.graph.edges:
                if edge.source.node != current or edge.target.node in found:
                    continue
                desc = self._descriptor_of(edge)
                if desc is not None and desc.invocation is not None:
                    found.add(edge.target.node)
                    work.append(edge.target.node)
        found.discard(self.node.id)
        return found
