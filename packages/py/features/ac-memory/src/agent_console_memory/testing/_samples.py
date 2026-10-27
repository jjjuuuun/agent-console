"""테스트 도구: 가짜 시계, 표본 쓴 주체·맥락·범위 종류.

이름은 테스트용이고 기본 데이터와 무관하다.
"""

from __future__ import annotations

import threading

from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAccessContext,
    MemoryAuthor,
    MemoryScopeKindSpec,
)
from agent_console_memory._scope_kinds import MemoryScopeKind


class FakeClock:
    """손으로 움직이는 시계(Unix epoch 초). 부를 때마다 `step`만큼 간다(기본 0).

    >>> clock = FakeClock(100.0)
    >>> clock(), clock.advance(5), clock()
    (100.0, None, 105.0)
    """

    def __init__(self, start: float = 1_700_000_000.0, *, step: float = 0.0) -> None:
        self.now = start
        self.step = step
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            value = self.now
            self.now += self.step
            return value

    def advance(self, seconds: float) -> None:
        """시각을 `seconds`만큼 옮긴다."""
        with self._lock:
            self.now += seconds


def user_author(label: str | None = None) -> MemoryAuthor:
    """사람 쓴 주체."""
    return MemoryAuthor(kind=KnownMemoryAuthorKinds.USER, label=label)


def agent_author_sample(agent_id: str = "agent-a", run_id: str = "run-1") -> MemoryAuthor:
    """에이전트 쓴 주체 표본."""
    return MemoryAuthor(kind=KnownMemoryAuthorKinds.AGENT, agent_id=agent_id, run_id=run_id)


def sample_context(**values: object) -> MemoryAccessContext:
    """접근 맥락 표본(필드 기본값 = 그래프 `g1`·프로젝트 `p1`·실행 `run-1`·에이전트 `agent-a`)."""
    base: dict[str, object] = {
        "run_id": "run-1",
        "root_run_id": "run-1",
        "graph_id": "g1",
        "root_graph_id": "g1",
        "project_id": "p1",
        "agent_id": "agent-a",
        "node_id": "n1",
        "node_path": ["n1"],
    }
    base.update(values)
    return MemoryAccessContext.model_validate(base)


def sample_scope_kinds(names: tuple[str, str, str]) -> dict[str, MemoryScopeKindSpec]:
    """이름을 고를 수 있는 범위 종류 셋(공용 모양·프로젝트 모양·팀 모양). R0 시험에 쓴다.

    >>> sorted(sample_scope_kinds(("x", "y", "z")))
    ['x', 'y', 'z']
    """
    everyone, per_project, per_graph = names
    return {
        everyone: MemoryScopeKindSpec(label=f"{everyone} label", id=""),
        per_project: MemoryScopeKindSpec(label=f"{per_project} label", id="{/project_id}"),
        per_graph: MemoryScopeKindSpec(label=f"{per_graph} label", id="{/graph_id}"),
    }


def sample_plugin_scope_kinds() -> list[MemoryScopeKind]:
    """X29 플러그인 모양 표본(entry point 대상): 계산 범위 종류 하나(루트 실행 id 앞 4글자).

    >>> sample_plugin_scope_kinds()[0].resolve(MemoryAccessContext(root_run_id="abcdef"))
    'abcd'
    """
    return [
        MemoryScopeKind(
            id="sample-computed",
            label="계산 표본",
            resolver=lambda ctx: ctx.root_run_id[:4] or None,
        )
    ]
