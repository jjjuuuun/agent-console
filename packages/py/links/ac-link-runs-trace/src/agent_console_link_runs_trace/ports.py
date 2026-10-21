"""link-runs-trace의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L6).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``runs.reader``: Run 조회(``RunReader`` — ``get``·``list``(``parent_run_id`` 포함)·
  ``list_node_runs``). 직접 자식 Run(중첩 팀)과 호출 NodeRun 입력(위임 과제)을 읽는다.
- 필수 ``runs.events``: 실행 이벤트 조회(``EventReader`` — ``list``).
- 선택 ``definitions.lookup``: 실행 당시 팀 구성(버전 기록 ``get_version``, 없으면 현재 ``get``).
  연결 종류(``edge_kinds``)를 넘김 화살표에 붙이는 데 쓴다. 없으면 종류 없이 그린다.

제공: 없음(경로만 — ``/runs/{id}/trace``·``/runs/handoffs``).
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import NodeRun, Run, RunEvent, RunStatus
from agent_console_modkit import PortKey


@runtime_checkable
class RunReader(Protocol):
    def get(self, run_id: str) -> Run | None: ...

    def list(
        self,
        *,
        graph_id: str | None = None,
        status: Iterable[RunStatus] | None = None,
        conversation_id: str | None = None,
        agent: str | None = None,
        parent_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]: ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...


@runtime_checkable
class EventReader(Protocol):
    def list(self, run_id: str, *, since_seq: int = 0) -> builtins.list[RunEvent]: ...


class _Doc(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


class _Version(Protocol):
    @property
    def content(self) -> Mapping[str, Any] | None: ...


@runtime_checkable
class GraphHistory(Protocol):
    """정의 읽기 중 쓰는 부분. 없으면 저장소 예외를 낸다."""

    def get(self, kind: str, id: str) -> _Doc: ...

    def get_version(self, kind: str, id: str, version_hash: str) -> _Version: ...


RUNS_READER: PortKey[RunReader] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[EventReader] = PortKey("runs.events", "실행 이벤트 조회")
DEFINITIONS_LOOKUP: PortKey[GraphHistory] = PortKey("definitions.lookup", "정의 읽기")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "RUNS_EVENTS",
    "RUNS_READER",
    "EventReader",
    "GraphHistory",
    "RunReader",
]
