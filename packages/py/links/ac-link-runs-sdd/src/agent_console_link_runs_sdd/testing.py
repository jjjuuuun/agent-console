"""테스트·예제용 가짜 실행 모듈 몫(공개). 실제 실행 엔진이 아니다.

- ``FakeRuns``: ``runs.starter``·``runs.reader`` 한 객체. ``start_graph``는 Run을 메모리에 만들고
  ``run.started`` 이벤트를 낸다(구독자 함수 ``emit``). ``finish``로 상태를 바꾸고 이벤트를 낸다.
  ``graphs``(공간 이름 → 팀 구성 id)·``library``로 ``definitions_for``·``find_graph``를 흉내 낸다
  (공간에 없고 공용에만 있으면 ``project.not_imported`` ``in_library``).
- ``fake_runs_module``: ``FakeRuns``를 ``runs.starter``·``runs.reader``로 주고 ``runs.event``로
  이벤트를 발행하는 모듈(``mod-runs`` 대신).
- ``LocalSddService``·``local_sdd_module``: 메모리 스펙 저장소 하나(공간 이름 없음)를
  ``sdd.service`` 모양으로 주는 작은 서비스·모듈(``mod-sdd`` 대신 — 비밀 검사 없음, 알림은 기록만).
- ``standalone_modules``: ``--with`` 없는 단독 실행에 붙일 모듈(가짜 실행 + 메모리 스펙).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import ErrorInfo, Issue, Run, RunEvent
from agent_console_contracts.constants import ErrorCodes
from agent_console_contracts.sdd import SddSettings
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_sdd import LoadedSpec, SpecContext, SpecFiles, SpecRepository
from agent_console_sdd.testing import memory_repository

from .ports import RUNS_EVENT, RUNS_READER, RUNS_STARTER, SDD_SERVICE

DEFAULT_LABEL_PREFIX = "sdd."
"""``LocalSddService`` 라벨 접두(``mod-sdd`` 설치자 기본값과 같은 값 — 가짜 전용)."""


class FakePreflightError(Exception):
    """사전 점검 거부(``error`` = ``ErrorInfo`` — ``RunPreflightError``와 같은 모양)."""

    def __init__(self, error: ErrorInfo) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class FakeHandle:
    run_id: str


@dataclass
class FakeRuns:
    """메모리 실행 시작·읽기.

    Attributes:
        graphs: 공간 이름(None = 공간 없음) → 있는 팀 구성 id.
        library: 공용 구성에 있는 팀 구성 id.
        emit: 이벤트를 받을 함수(모듈은 ``runs.event`` 발행을 넣는다).
        started: ``start_graph`` 인자 기록.
    """

    graphs: dict[str | None, set[str]] = field(default_factory=dict)
    library: set[str] = field(default_factory=set)
    emit: Callable[[RunEvent], None] = lambda _event: None
    started: list[dict[str, Any]] = field(default_factory=list)
    runs: dict[str, Run] = field(default_factory=dict)
    clock: Callable[[], float] = time.time
    _seq: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------ runs.starter
    def definitions_for(self, project_id: str | None, graph_id: str) -> object | None:
        if project_id is None:
            return None
        if graph_id in self.graphs.get(project_id, set()):
            return object()
        raise FakePreflightError(
            ErrorInfo(
                code=ErrorCodes.PROJECT_NOT_IMPORTED,
                message="공간에 없는 팀 구성입니다.",
                details={
                    "project_id": project_id,
                    "kind": "graph",
                    "id": graph_id,
                    "in_library": graph_id in self.library,
                },
            )
        )

    def find_graph(self, graph_id: str, *, project_id: str | None = None) -> object | None:
        if project_id is None:
            known = self.graphs.get(None, set()) | self.library
        else:
            known = self.graphs.get(project_id, set())
        return object() if graph_id in known else None

    async def start_graph(
        self,
        graph_id: str,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = "api",
        project_id: str | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> FakeHandle:
        self.definitions_for(project_id, graph_id)
        if self.find_graph(graph_id, project_id=project_id) is None:
            raise FakePreflightError(
                ErrorInfo(code=ErrorCodes.NOT_FOUND, message="팀 구성이 없습니다.")
            )
        run_id = f"run-{len(self.runs) + 1}"
        now = self.clock()
        run = Run(
            id=run_id,
            graph_id=graph_id,
            graph_version="v",
            status="running",
            input=dict(input or {}),
            origin=origin,
            project_id=project_id,
            created_at=now + len(self.runs) * 1e-3,
            started_at=now,
            labels=dict(labels or {}),
        )
        self.runs[run_id] = run
        self.started.append(
            {
                "graph_id": graph_id,
                "input": dict(input or {}),
                "origin": origin,
                "project_id": project_id,
                "labels": dict(labels or {}),
            }
        )
        self._event(run_id, "run.started", "running")
        return FakeHandle(run_id)

    def finish(self, run_id: str, status: str = "completed") -> Run:
        """Run 상태를 바꾸고 ``run.<상태>`` 이벤트를 낸다."""
        run = self.runs[run_id].model_copy(update={"status": status, "ended_at": self.clock()})
        self.runs[run_id] = run
        self._event(run_id, f"run.{status}", status)
        return run

    def _event(self, run_id: str, type: str, status: str) -> None:
        seq = self._seq.get(run_id, 0) + 1
        self._seq[run_id] = seq
        self.emit(
            RunEvent(
                event_id=f"{run_id}-{seq}",
                run_id=run_id,
                seq=seq,
                ts=self.clock(),
                node_path=[],
                type=type,
                payload={"status": status},
            )
        )

    # ------------------------------------------------------------ runs.reader
    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def page(self, **filters: Any) -> tuple[list[Run], str | None]:
        labels: Mapping[str, str] = filters.get("labels") or {}
        project_id = filters.get("project_id")
        limit = int(filters.get("limit") or 50)
        offset = int(filters.get("cursor") or 0)
        items = [
            r
            for r in sorted(self.runs.values(), key=lambda r: (r.created_at, r.id), reverse=True)
            if (project_id is None or r.project_id == project_id)
            and all(r.labels.get(k) == v for k, v in labels.items())
        ]
        chunk = items[offset : offset + limit]
        more = offset + limit < len(items)
        return chunk, (str(offset + limit) if more else None)


def fake_runs_module(runs: FakeRuns, module_id: str = "fake-runs") -> Module:
    """``FakeRuns``를 ``runs.starter``·``runs.reader``로 주고 이벤트를 ``runs.event``로 낸다."""

    def build(ctx: ModuleContext) -> ModuleParts:
        runs.emit = lambda event: ctx.publish(RUNS_EVENT, event)
        ctx.provide(RUNS_STARTER, runs)
        ctx.provide(RUNS_READER, runs)
        return ModuleParts()

    return fake_module(
        module_id, kind="testing", provides=[RUNS_STARTER, RUNS_READER], on_build=build
    )


@dataclass
class LocalScope:
    """``SddScopeLike`` 예제 구현(공간 이름 없음)."""

    repository: SpecRepository
    name: str | None = None
    files: SpecFiles | None = None
    spec_root: str = ""


@dataclass
class LocalSddService:
    """``sdd.service`` 모양의 작은 서비스(메모리 저장소 하나, 비밀 검사 꺼짐).

    Attributes:
        repository: 스펙 저장소(기본 ``agent_console_sdd.testing.memory_repository()``).
        label_prefix: 라벨 접두. notified: ``notify`` 기록(공간, 스펙 id).
    """

    repository: SpecRepository = field(default_factory=memory_repository)
    label_prefix: str = DEFAULT_LABEL_PREFIX
    notified: list[tuple[str | None, str]] = field(default_factory=list)

    def scope(self, space: str | None) -> LocalScope:
        if space is not None:
            raise LookupError(space)
        return LocalScope(repository=self.repository)

    def context(self, scope: Any, loaded: LoadedSpec) -> SpecContext:
        return SpecContext(
            space=None,
            spec=loaded.spec,
            index=loaded.index,
            syntax=loaded.syntax,
            version_hash=loaded.stored.version_hash,
            directory=self.repository.spec_directory(loaded.spec.id),
        )

    def settings(self) -> SddSettings:
        return SddSettings()

    def label_key(self, name: str) -> str:
        return self.label_prefix + name

    def secret_findings(self, text: str) -> list[Issue]:
        return []

    def secret_mode(self) -> str:
        return "off"

    def notify(
        self,
        space: str | None,
        spec_id: str,
        *,
        version_hash: str | None = None,
        automation: bool = False,
        deleted: bool = False,
    ) -> None:
        self.notified.append((space, spec_id))


def local_sdd_module(
    service: LocalSddService | None = None, module_id: str = "local-sdd"
) -> Module:
    """``LocalSddService``를 ``sdd.service``로 주는 모듈."""
    svc = service or LocalSddService()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(SDD_SERVICE, svc)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[SDD_SERVICE], on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(가짜 실행 + 메모리 스펙)."""
    return [fake_runs_module(FakeRuns()), local_sdd_module()]


__all__ = [
    "DEFAULT_LABEL_PREFIX",
    "FakeHandle",
    "FakePreflightError",
    "FakeRuns",
    "LocalScope",
    "LocalSddService",
    "fake_runs_module",
    "local_sdd_module",
    "standalone_modules",
]
