"""로그 범위 종류 ``run``·``run-tree``(X27, design §5.5R.3·§5.5R.5).

``scope=run:<Run id>``는 그 Run의 플랫폼 실행 이벤트(``run_id``)와 그 Run의 세션 id들(NodeRun
``backend_session_id`` + 색인된 플랫폼 실행 이벤트의 ``session``)의 합집합이다.
``scope=run-tree:<Run id>``는 같은 계산을 그 Run과 아래 모든 자식 Run(중첩 팀, ``parent_run_id``)에
한다. 세션 id 계산은 ``/runs/{id}/logs``(``RunLogs``)와 같은 함수(``run_sessions``)를 쓴다.

FastAPI·``mod-logs``를 모른다. 등록은 모듈이 포트 ``logs.scope_kinds``로 한다.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from agent_console_contracts.logs import LogAggregateRequest
from agent_console_logs import LogScope

from .ports import LogQueryLike, RunReader
from .source import SOURCE_ID

__all__ = [
    "RUN_SCOPE_KIND",
    "RUN_TREE_SCOPE_KIND",
    "RunScopeKind",
    "run_scope_kinds",
    "run_sessions",
    "run_tree_ids",
]

RUN_SCOPE_KIND = "run"
"""범위 종류 id: Run 하나(``scope=run:<id>``)."""

RUN_TREE_SCOPE_KIND = "run-tree"
"""범위 종류 id: Run과 자식 Run 전부(``scope=run-tree:<id>``)."""

SESSION_DIMENSION = "session"
COUNT_METRIC = "events"
"""``ac-logs`` 질의 엔진의 차원·지표 이름(``agent_console_logs.DIMENSIONS``·``METRICS``)."""


def run_sessions(
    runs: RunReader,
    logs: LogQueryLike,
    run_ids: Collection[str],
    *,
    source_id: str = SOURCE_ID,
) -> set[str]:
    """Run들의 세션 id: NodeRun ``backend_session_id`` + 색인된 플랫폼 실행 이벤트의 ``session``.

    Args:
        runs: Run·NodeRun 조회.
        logs: 색인 읽기(집계 한 번).
        run_ids: 대상 Run id들(있는지는 보지 않는다).
        source_id: 플랫폼 실행 출처 id.
    """
    found: set[str] = set()
    for run_id in run_ids:
        found.update(
            n.backend_session_id for n in runs.list_node_runs(run_id) if n.backend_session_id
        )
    if not run_ids:
        return found
    rows = logs.aggregate(
        LogAggregateRequest(
            group_by=[SESSION_DIMENSION],
            metric=COUNT_METRIC,
            filter={"run_id": sorted(run_ids), "source": [source_id]},
        )
    )
    for row in rows:
        value = row.keys.get(SESSION_DIMENSION)
        if value:
            found.add(value)
    return found


def run_tree_ids(runs: RunReader, root: str) -> list[str]:
    """``root``와 아래 모든 자식 Run id(넓이 우선, ``root`` 먼저). 순환이 있어도 한 번씩만."""
    seen = [root]
    known = {root}
    queue = [root]
    while queue:
        parent = queue.pop(0)
        for child in runs.list(parent_run_id=parent):
            if child.id not in known:
                known.add(child.id)
                seen.append(child.id)
                queue.append(child.id)
    return seen


class RunScopeKind:
    """범위 종류(``LogScopeKind``) — 값 = Run id.

    Args:
        runs: Run·NodeRun 조회.
        logs: 색인 읽기(세션 id 계산용 집계).
        kind_id: 종류 id(``scope=<kind_id>:<Run id>``).
        tree: 참이면 자식 Run 전부를 포함한다(``run-tree``).
        source_id: 플랫폼 실행 출처 id.

    Raises (``resolve``):
        ValueError: 값이 비었거나 Run이 없다(``mod-logs``가 422로 바꾼다).
    """

    def __init__(
        self,
        runs: RunReader,
        logs: LogQueryLike,
        *,
        kind_id: str = RUN_SCOPE_KIND,
        tree: bool = False,
        source_id: str = SOURCE_ID,
    ) -> None:
        self._runs = runs
        self._logs = logs
        self._id = kind_id
        self._tree = tree
        self._source = source_id

    @property
    def id(self) -> str:
        return self._id

    def run_ids(self, value: str) -> list[str]:
        """값 → 범위의 Run id들(``ValueError``는 ``resolve``와 같다)."""
        run_id = value.strip()
        if not run_id:
            raise ValueError("Run id가 비었습니다")
        if self._runs.get(run_id) is None:
            raise ValueError(f"Run {run_id}이(가) 없습니다")
        return run_tree_ids(self._runs, run_id) if self._tree else [run_id]

    def resolve(self, value: str) -> LogScope:
        ids = self.run_ids(value)
        return LogScope.of(run_sessions(self._runs, self._logs, ids, source_id=self._source), ids)


def run_scope_kinds(
    runs: RunReader,
    logs: LogQueryLike,
    *,
    source_id: str = SOURCE_ID,
    kinds: Iterable[tuple[str, bool]] = ((RUN_SCOPE_KIND, False), (RUN_TREE_SCOPE_KIND, True)),
) -> list[RunScopeKind]:
    """기본 범위 종류 묶음(``run``·``run-tree``). ``kinds`` = (종류 id, 자식 포함) 목록."""
    return [
        RunScopeKind(runs, logs, kind_id=kid, tree=tree, source_id=source_id) for kid, tree in kinds
    ]
