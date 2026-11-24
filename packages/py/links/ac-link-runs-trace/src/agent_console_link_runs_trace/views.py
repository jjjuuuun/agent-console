"""위임 흐름·넘김 집계 계산(``ac-trace``)에 실행 기록·당시 팀 구성을 넘긴다. FastAPI를 모른다.

프로젝트 기준 읽기는 ``TraceViews.in_project``다(``?project=``, 실행 목록과 같은 정책).
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from typing import Any

from agent_console_contracts import Graph, HandoffMatrix, NodeRun, Run, RunStatus, Trace
from agent_console_trace import build_trace, handoff_matrix

from .ports import (
    EventReader,
    GraphHistory,
    ProjectEventReader,
    ProjectRunReader,
    RunReader,
)

GRAPH_KIND = "graph"
"""정의 저장소에서 팀 구성 종류 이름."""


def call_edges(graph: Graph) -> dict[tuple[str, str], str]:
    """(출발 노드, 도착 노드) → 연결 id. 그 쌍의 연결이 하나뿐일 때만 싣는다(모호하면 뺀다).

    호출 span(위임자 → 대상)에 쓴 연결을 붙이는 데 쓴다. 연결 종류 이름은 보지 않는다.
    """
    found: dict[tuple[str, str], list[str]] = {}
    for edge in graph.edges:
        found.setdefault((edge.source.node, edge.target.node), []).append(edge.id)
    return {pair: ids[0] for pair, ids in found.items() if len(ids) == 1}


class RunNotFoundError(LookupError):
    """Run이 없다(404)."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id}이(가) 없습니다")
        self.run_id = run_id


class ProjectRuns:
    """``for_project``가 없는 Run 조회를 한 프로젝트로 좁힌다(Run의 ``project_id``로 거른다).

    >>> from agent_console_store import InMemoryStorage
    >>> ProjectRuns(InMemoryStorage().runs, "p1").get("nope") is None
    True
    """

    def __init__(self, runs: RunReader, project_id: str) -> None:
        self._runs = runs
        self.project_id = project_id

    def get(self, run_id: str) -> Run | None:
        run = self._runs.get(run_id)
        return run if run is not None and run.project_id == self.project_id else None

    def list(self, **filters: Any) -> builtins.list[Run]:
        return self._runs.list(**{**filters, "project_id": self.project_id})

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        return self._runs.list_node_runs(run_id)


class TraceViews:
    """실행 흐름 계산.

    Args:
        runs: Run 조회.
        events: 이벤트 조회.
        history: 정의 읽기(없으면 None을 돌려주는 함수 — 연결 종류 없이 그린다).
        space_history: 공간 이름 → 그 공간의 정의 읽기. ``project_id``가 있는 Run의 당시 팀 구성은
            여기서만 읽는다(None을 돌려주거나 예외면 연결 종류 없이 그린다 — ``history``로 넘어가지
            않는다). 이 인자가 None(기본, 공간 제공자 없음)이면 모든 Run이 ``history``.
    """

    def __init__(
        self,
        runs: RunReader,
        events: EventReader,
        *,
        history: Callable[[], GraphHistory | None] = lambda: None,
        space_history: Callable[[str], GraphHistory | None] | None = None,
    ) -> None:
        self._runs = runs
        self._events = events
        self._history = history
        self._space_history = space_history

    def in_project(self, project_id: str) -> TraceViews:
        """그 프로젝트에 묶인 계산(``runs``·``events``의 선택 메서드 ``for_project``, 없으면 Run의
        ``project_id``로 거른다). 정의 읽기는 같다.

        Raises:
            Exception: ``for_project``가 낸 예외(모르는 프로젝트 ``UnknownSpace`` 등). 제공자에
                따라 읽을 때 낸다.
        """
        runs: RunReader = (
            self._runs.for_project(project_id)
            if isinstance(self._runs, ProjectRunReader)
            else ProjectRuns(self._runs, project_id)
        )
        events: EventReader = (
            self._events.for_project(project_id)
            if isinstance(self._events, ProjectEventReader)
            else self._events
        )
        return TraceViews(runs, events, history=self._history, space_history=self._space_history)

    def require_run(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        return run

    def graph_at(self, run: Run) -> Graph | None:
        """실행 당시 팀 구성(버전 기록), 없으면 현재 팀 구성. 정의 읽기가 없거나 못 읽으면 None.

        ``project_id``가 있는 Run은 공간 정의 읽기(``space_history``)가 있으면 그것만 본다.
        """
        history = self._history_of(run)
        if history is None:
            return None
        try:
            version = history.get_version(GRAPH_KIND, run.graph_id, run.graph_version)
            if version.content is not None:
                return Graph.model_validate(version.content)
        except Exception:
            pass
        try:
            return Graph.model_validate(history.get(GRAPH_KIND, run.graph_id).document)
        except Exception:
            return None

    def _history_of(self, run: Run) -> GraphHistory | None:
        if run.project_id is None or self._space_history is None:
            return self._history()
        try:
            return self._space_history(run.project_id)
        except Exception:  # 보관·모르는 공간 등 — 라이브러리로 넘어가지 않는다
            return None

    def trace(self, run: Run, *, children: bool = True) -> Trace:
        """위임 흐름. `children`이면 자식 Run(중첩 팀)의 흐름을 부른 노드 span 아래에 붙인다.

        자식 Run은 직접 자식(`parent_run_id`)부터 재귀로 읽는다. 깊이는 실제 중첩 깊이(엔진의
        `max_nesting`이 막는다)이고, 같은 Run을 두 번 붙이지 않는다.
        """
        return self._trace(run, children=children, seen={run.id})

    def _trace(self, run: Run, *, children: bool, seen: set[str]) -> Trace:
        graph = self.graph_at(run)
        edge_kinds = {e.id: e.kind for e in graph.edges} if graph is not None else None
        child_traces: dict[str, Trace] = {}
        if children:
            for child in reversed(self._runs.list(parent_run_id=run.id)):  # 만든 순
                if child.id in seen:
                    continue
                seen.add(child.id)
                child_traces[child.id] = self._trace(child, children=True, seen=seen)
        return build_trace(
            self._events.list(run.id),
            run_id=run.id,
            edge_kinds=edge_kinds,
            call_edges=call_edges(graph) if graph is not None else None,
            node_runs=self._runs.list_node_runs(run.id),
            children=child_traces,
        )

    def handoffs(
        self,
        *,
        graph_id: str | None,
        conversation_id: str | None,
        agent_id: str | None,
        status: RunStatus | None,
        limit: int,
    ) -> HandoffMatrix:
        runs: Sequence[Run] = self._runs.list(
            graph_id=graph_id,
            conversation_id=conversation_id,
            agent=agent_id,
            status=[status] if status is not None else None,
            limit=limit,
        )
        # Run마다 자기 흐름만 센다(자식 Run은 목록에 따로 있어 붙이면 두 번 센다).
        matrix = handoff_matrix(self.trace(run, children=False) for run in runs)
        return matrix.model_copy(update={"runs": len(runs)})


__all__ = ["GRAPH_KIND", "ProjectRuns", "RunNotFoundError", "TraceViews", "call_edges"]
