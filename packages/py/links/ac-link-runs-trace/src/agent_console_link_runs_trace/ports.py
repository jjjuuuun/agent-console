"""link-runs-trace의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L6).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``runs.reader``: Run 조회(``RunReader`` — ``get``·``list``(``parent_run_id`` 포함)·
  ``list_node_runs``). 직접 자식 Run(중첩 팀)과 호출 NodeRun 입력(위임 과제)을 읽는다.
- 필수 ``runs.events``: 실행 이벤트 조회(``EventReader`` — ``list``).
- 선택 ``definitions.lookup``: 실행 당시 팀 구성(버전 기록 ``get_version``, 없으면 현재 ``get``).
  연결 종류(``edge_kinds``)를 넘김 화살표에 붙이는 데 쓴다. 없으면 종류 없이 그린다.
- 선택 ``definitions.spaces``: 공간 이름 → 정의 저장소(``agent_console_store.DefinitionSpaces``).
  ``project_id``가 있는 Run의 당시 팀 구성은 그 공간 저장소에서만 읽는다(못 열면 종류 없이 그린다 —
  라이브러리로 넘어가지 않는다). 없으면(기능 단독) ``definitions.lookup``.

프로젝트 기준 읽기(``?project=``): ``runs.reader``·``runs.events``의 선택 메서드 ``for_project(id)``
(``ProjectRunReader``·``ProjectEventReader``)로 그 프로젝트에 묶인 읽기를 얻는다. 없으면 Run의
``project_id``로 거른다(실행 목록 ``GET /runs?project=``와 같은 정책).

제공: 없음(경로만 — ``/runs/{id}/trace``·``/runs/handoffs``).
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import NodeRun, Run, RunEvent, RunStatus
from agent_console_modkit import PortKey
from agent_console_store import DEFINITIONS_SPACES_PORT, DefinitionSpaces


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
        project_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]: ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...


@runtime_checkable
class ProjectRunReader(Protocol):
    """``runs.reader``의 선택 능력: 그 프로젝트(기록 공간)에 묶인 읽기.

    모르는 프로젝트면 제공자의 예외(``agent_console_store.UnknownSpace`` → 404
    ``project.not_found``)를 낸다.
    """

    def for_project(self, project_id: str | None) -> RunReader: ...


@runtime_checkable
class EventReader(Protocol):
    def list(self, run_id: str, *, since_seq: int = 0) -> builtins.list[RunEvent]: ...


@runtime_checkable
class ProjectEventReader(Protocol):
    """``runs.events``의 선택 능력: 그 프로젝트(기록 공간)에 묶인 이벤트 읽기."""

    def for_project(self, project_id: str | None) -> EventReader: ...


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
DEFINITIONS_SPACES: PortKey[DefinitionSpaces] = PortKey(
    DEFINITIONS_SPACES_PORT, "공간 이름 → 정의 저장소"
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SPACES",
    "RUNS_EVENTS",
    "RUNS_READER",
    "EventReader",
    "GraphHistory",
    "ProjectEventReader",
    "ProjectRunReader",
    "RunReader",
]
