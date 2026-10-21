"""끊긴 실행 이어 가기(design §2R.10): 끊긴 노드 찾기·다시 실행 가능 검사·새 Run 시작 조립.

엔진은 노드 이름을 모른다. "다시 실행해도 되는가"는 노드 타입 디스크립터 `rerunnable`이 정하고,
새 Run을 어떻게 시작할지(대화 턴인지, 어떤 검증을 거칠지)는 주입받은 `ResumeStarter`가 정한다.
저장소는 아래 작은 프로토콜로만 읽는다(`agent_console_store` 저장소가 그대로 만족한다).
"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, cast, get_args

from agent_console_contracts import (
    ErrorCodes,
    Graph,
    Issue,
    NodeRun,
    NodeRunStatus,
    NodeTypeDescriptor,
    ResumeNodeOption,
    ResumeOptions,
    Run,
    RunEvent,
)

from ._runtime import RuntimeErrorCodes
from ._validation import GraphValidationError

INTERRUPTED_RUN_STATUS: Final = "interrupted"
"""이어 갈 수 있는 Run 상태(서버 재시작·정상 종료로 끊김)."""

_UNFINISHED: Final = frozenset({"pending", "queued", "running", "waiting"})
_NODE_STATUSES: Final = frozenset(get_args(NodeRunStatus.__value__))
_NODE_EVENT_PREFIX: Final = "node."


class ResumeIssueCodes:
    """`resume`가 거부할 때 내는 `Issue.code`(노드별, 422)."""

    UNKNOWN_NODE: Final = "resume.unknown_node"
    """끊긴 노드 목록에 없는 노드."""
    NOT_RERUNNABLE: Final = "resume.not_rerunnable"
    """노드 타입 디스크립터가 `rerunnable = false`(또는 노드 타입을 모름)."""


class ResumeError(Exception):
    """이어 가기 거부. `code`는 계약 `ErrorCodes` 값(전송 계층이 HTTP 상태로 바꾼다)."""

    code: str = ErrorCodes.BAD_REQUEST

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class ResumeRunNotFoundError(ResumeError):
    """Run이 없다."""

    code = ErrorCodes.NOT_FOUND


class RunNotResumableError(ResumeError):
    """끊긴 Run이 아니거나, 자식 Run이거나, 이미 이어 갔거나, 실행 당시 팀 구성을 찾을 수 없다
    (409)."""

    code = ErrorCodes.RUN_NOT_RESUMABLE


class ResumeRunSource(Protocol):
    """Run 조회(`agent_console_store` Run 리포지토리가 만족)."""

    def get(self, run_id: str) -> Run | None: ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...

    def list(self, *, resumed_from: str | None = None) -> builtins.list[Run]:
        """`resumed_from`을 주면 그 Run을 이어 간 Run들."""
        ...


class ResumeEventSource(Protocol):
    """Run 이벤트 조회(seq 순)."""

    def list(self, run_id: str) -> list[RunEvent]: ...


@dataclass(frozen=True, slots=True)
class ResumeStart:
    """새 Run을 시작하라는 요청(`ResumeStarter`가 받는다).

    Attributes:
        run: 끊긴 원래 Run(새 Run의 `resumed_from`·입력·대화 id의 근거).
        graph: 실행할 팀 구성(원래 Run 당시 버전).
        seed: 노드 id → 저장된 입력(`GraphRuntime.start(seed=)`).
    """

    run: Run
    graph: Graph
    seed: dict[str, dict[str, Any]]


type ResumeStarter = Callable[[ResumeStart], Awaitable[Run]]
"""새 Run을 시작하고 돌려준다(예: 대화 턴이면 `ChatService.resume_turn`, 아니면 `start_run`).
`origin`·`resumed_from`을 Run에 기록하는 것도 시작하는 쪽 몫이다."""


def interrupted_status(node_run: NodeRun, events: Iterable[RunEvent]) -> NodeRunStatus | None:
    """노드가 끊겼으면 끊기기 직전 상태를, 아니면 None.

    끊긴 노드 = 상태가 끝나지 않았거나(`waiting` 등), `cancelled`이고 `error.code`가
    `interrupted`인 노드. 끊기기 직전 상태는 그 노드의 마지막 `node.*` 이벤트 중 `cancelled`가
    아닌 것의 `status`(없으면 `running`). 반복 회차(design §5R.4)가 있으면 payload `iteration`이
    이 NodeRun 회차와 같은 이벤트만 본다(`iteration`이 없는 옛 이벤트는 회차 0). 호출 NodeRun
    이면 `node_path`가 `invoked_by + [노드]`이고 payload `call`이 같은 이벤트만 본다.
    """
    if node_run.status in _UNFINISHED:
        return node_run.status
    if node_run.status != "cancelled" or (
        node_run.error is None or node_run.error.code != RuntimeErrorCodes.INTERRUPTED
    ):
        return None
    last: NodeRunStatus = "running"
    path = [*(node_run.invoked_by or []), node_run.node_id]
    for event in sorted(events, key=lambda e: e.seq):
        if not event.type.startswith(_NODE_EVENT_PREFIX) or event.node_path != path:
            continue
        if (event.payload.get("iteration") or 0) != node_run.iteration:
            continue
        if (event.payload.get("call") or 0) != node_run.call:
            continue
        status = event.payload.get("status")
        if status in _NODE_STATUSES and status != "cancelled":
            last = cast("NodeRunStatus", status)
    return last


def resume_options(
    run: Run,
    node_runs: Sequence[NodeRun],
    events: Sequence[RunEvent],
    *,
    graph: Graph | None,
    node_types: Iterable[NodeTypeDescriptor],
) -> ResumeOptions:
    """끊긴 Run의 다시 실행할 수 있는 지점 목록(순수 함수). 끊긴 Run이 아니면 빈 목록.

    자식 Run(`root_run_id`가 있음, design §5R.7)도 빈 목록이다: 자식 Run은 부모 노드가 만든
    실행이라 따로 이어 가지 않고, 루트 Run을 이어 가면 부른 노드가 자식을 새로 만든다.

    Args:
        run: 대상 Run.
        node_runs: 그 Run의 NodeRun.
        events: 그 Run의 이벤트(끊기기 직전 상태 계산).
        graph: 실행 당시 팀 구성(노드 label·순서). 없으면 label 없이 NodeRun 순서.
        node_types: 노드 타입 디스크립터(`rerunnable`). 모르는 타입은 다시 실행할 수 없다.
    """
    if run.status != INTERRUPTED_RUN_STATUS or run.root_run_id is not None:
        return ResumeOptions(run_id=run.id)
    rerunnable = {d.id: d.rerunnable for d in node_types}
    specs = {n.id: n for n in graph.nodes} if graph is not None else {}
    order = {node_id: i for i, node_id in enumerate(specs)}
    by_node: dict[str, list[RunEvent]] = {}
    for event in events:
        if len(event.node_path) == 1:
            by_node.setdefault(event.node_path[0], []).append(event)
    # 같은 노드의 반복 회차가 여럿이면 마지막 회차만 본다(design §5R.4). 위임자가 부른 호출
    # NodeRun(design §5R.6)은 스케줄되지 않아 다시 실행할 지점이 아니다(부른 위임자를 고른다).
    latest: dict[str, NodeRun] = {}
    for node_run in node_runs:
        if node_run.invoked_by is not None:
            continue
        seen = latest.get(node_run.node_id)
        if seen is None or (node_run.attempt, node_run.iteration) >= (seen.attempt, seen.iteration):
            latest[node_run.node_id] = node_run
    found: list[tuple[int, ResumeNodeOption]] = []
    for i, node_run in enumerate(latest.values()):
        status = interrupted_status(node_run, by_node.get(node_run.node_id, ()))
        if status is None:
            continue
        spec = specs.get(node_run.node_id)
        node_type = node_run.node_type or (spec.type if spec is not None else None)
        option = ResumeNodeOption(
            node_id=node_run.node_id,
            label=spec.label if spec is not None else None,
            rerunnable=bool(node_type is not None and rerunnable.get(node_type, False)),
            status=status,
        )
        found.append((order.get(node_run.node_id, len(order) + i), option))
    found.sort(key=lambda pair: pair[0])
    return ResumeOptions(run_id=run.id, nodes=[option for _, option in found])


def resume_issues(options: ResumeOptions, node_ids: Iterable[str]) -> list[Issue]:
    """고른 노드 중 다시 실행할 수 없는 것(노드별 error 이슈, 순수 함수)."""
    known = {n.node_id: n for n in options.nodes}
    issues: list[Issue] = []
    for node_id in dict.fromkeys(node_ids):
        option = known.get(node_id)
        if option is None:
            issues.append(
                Issue(
                    severity="error",
                    code=ResumeIssueCodes.UNKNOWN_NODE,
                    message="고른 노드는 이 실행에서 끊긴 노드가 아니라 다시 실행할 수 없습니다",
                    node_id=node_id,
                    details={"node_id": node_id},
                )
            )
        elif not option.rerunnable:
            name = f"'{option.label}'은(는) " if option.label else "이 종류의 노드는 "
            issues.append(
                Issue(
                    severity="error",
                    code=ResumeIssueCodes.NOT_RERUNNABLE,
                    message=f"{name}다시 실행할 수 없습니다",
                    node_id=node_id,
                )
            )
    return issues


def resume_seed(node_runs: Sequence[NodeRun], node_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """고른 노드의 저장된 입력(`NodeRun.inputs`, 같은 노드가 여러 번이면 마지막 시도·회차).

    위임자가 부른 호출 NodeRun(`invoked_by`가 있음)은 보지 않는다(스케줄 실행만 시작점이다).
    """
    wanted = set(node_ids)
    seed: dict[str, dict[str, Any]] = {}
    for node_run in sorted(node_runs, key=lambda r: (r.attempt, r.iteration, r.call)):
        if node_run.node_id in wanted and node_run.invoked_by is None:
            seed[node_run.node_id] = dict(node_run.inputs)
    return seed


class ResumeService:
    """끊긴 Run 이어 가기: 선택지 조회와 새 Run 시작(검사 → seed → `starter`).

    Args:
        runs: Run·NodeRun 조회(`list(resumed_from=)`로 이미 이어 갔는지 확인).
        events: Run 이벤트 조회.
        graph_of: Run 당시 팀 구성(버전 이력). 찾을 수 없으면 None.
        node_types: 현재 노드 타입 디스크립터 목록을 돌려주는 함수.
        starter: 새 Run 시작(대화 턴 여부·검증은 시작하는 쪽이 정한다).
    """

    def __init__(
        self,
        runs: ResumeRunSource,
        events: ResumeEventSource,
        *,
        graph_of: Callable[[Run], Graph | None],
        node_types: Callable[[], Iterable[NodeTypeDescriptor]],
        starter: ResumeStarter,
    ) -> None:
        self._runs = runs
        self._events = events
        self._graph_of = graph_of
        self._node_types = node_types
        self._starter = starter
        self._lock = asyncio.Lock()

    def options(self, run_id: str) -> ResumeOptions:
        """`GET /runs/{id}/resume-options`. 끊긴 Run이 아니거나 이미 이어 갔으면 빈 목록.

        Raises:
            ResumeRunNotFoundError: Run이 없을 때.
        """
        run = self._require(run_id)
        if self._resumed_by(run_id) is not None:
            return ResumeOptions(run_id=run_id)
        return self._options(run)

    async def resume(self, run_id: str, node_ids: Sequence[str]) -> Run:
        """고른 노드를 저장된 입력으로 다시 실행하는 새 Run을 시작한다.

        Raises:
            ResumeRunNotFoundError: Run이 없을 때.
            RunNotResumableError: 끊긴 Run이 아니거나, 자식 Run이거나(`root_run_id`), 이미 이어
                갔거나, 당시 팀 구성이 없을 때.
            GraphValidationError: 끊긴 노드가 아니거나 `rerunnable`이 아닌 노드(노드별 이슈).
            Exception: `starter`가 낸 오류(그래프 검증 실패·대화 실행 중 등)는 그대로.
        """
        async with self._lock:  # 같은 Run을 두 번 이어 가지 않게(검사와 시작 사이)
            run = self._require(run_id)
            # 자식 Run 검사를 상태 검사보다 먼저 한다: 자식 Run은 상태와 무관하게 따로 이어 갈 수
            # 없고, 거절 상세에 이어 갈 곳(`root_run_id`·`parent_run_id`)이 있어야 한다.
            if run.root_run_id is not None:
                raise RunNotResumableError(
                    "중첩 팀 안의 실행은 따로 이어 갈 수 없습니다. 맨 위 실행을 열어 이어 가세요.",
                    details={
                        "run_id": run_id,
                        "status": run.status,
                        "root_run_id": run.root_run_id,
                        "parent_run_id": run.parent_run_id,
                    },
                )
            if run.status != INTERRUPTED_RUN_STATUS:
                raise RunNotResumableError(
                    "끊긴 실행만 이어 갈 수 있습니다",
                    details={"run_id": run_id, "status": run.status},
                )
            resumed_by = self._resumed_by(run_id)
            if resumed_by is not None:
                raise RunNotResumableError(
                    "이미 이어 간 실행입니다",
                    details={"run_id": run_id, "resumed_by": resumed_by},
                )
            graph = self._graph_of(run)
            if graph is None:
                raise RunNotResumableError(
                    "실행 당시 팀 구성을 찾을 수 없습니다",
                    details={"run_id": run_id, "graph_id": run.graph_id},
                )
            node_runs = self._runs.list_node_runs(run_id)
            options = resume_options(
                run,
                node_runs,
                self._events.list(run_id),
                graph=graph,
                node_types=self._node_types(),
            )
            issues = resume_issues(options, node_ids)
            if issues:
                raise GraphValidationError(issues)
            seed = resume_seed(node_runs, node_ids)
            return await self._starter(ResumeStart(run=run, graph=graph, seed=seed))

    def _require(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise ResumeRunNotFoundError(f"Run {run_id!r}가 없습니다", details={"id": run_id})
        return run

    def _resumed_by(self, run_id: str) -> str | None:
        later = self._runs.list(resumed_from=run_id)
        return later[0].id if later else None

    def _options(self, run: Run) -> ResumeOptions:
        return resume_options(
            run,
            self._runs.list_node_runs(run.id),
            self._events.list(run.id),
            graph=self._graph_of(run),
            node_types=self._node_types(),
        )
