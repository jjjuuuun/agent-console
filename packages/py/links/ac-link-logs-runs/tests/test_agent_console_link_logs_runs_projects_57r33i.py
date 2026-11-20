"""5.7R.33i·33u2·R15.3: 프로젝트 공간(폴더 기록 DB)의 실행도 로그로 색인한다.

- 등록 프로젝트(``projects.lookup``)마다 그 공간의 Run을 ``runs.reader.list(project_id=)``로 읽는다
  (실제 ``mod-runs`` ``SpaceRecorder`` + ``records.spaces`` 위 폴더 기록 DB). 이 프로세스가 아직
  모르는 공간(이전 프로세스가 쓴 기록)도 읽는다.
- 세션 ``project_id``는 작업 폴더(``run.started`` ``cwd``)로 붙어 ``project=`` 필터로 걸러진다.
- 프로젝트 모듈이 꺼지면(``projects.lookup`` 없음) 공용(앱 기록) 실행만 읽는다(R0).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import NodeRun, Run, RunEvent
from agent_console_contracts.logs import LogSessionSummary
from agent_console_link_logs_runs import (
    PROJECTS_LOOKUP,
    RUNS_EVENTS,
    RUNS_READER,
    module,
    platform_runs,
)
from agent_console_link_logs_runs.testing import LocalLogs, local_logs_module, run_event
from agent_console_logs import LogFilter, LogIngestor, LogRegistries, QueryContext, query_context
from agent_console_logs.testing import MemoryLogIndex
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.storage import BRANCH
from agent_console_modkit import BaseServices, EventBus, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import InMemoryStorage, RecordsDb, SqliteStorage, open_records_db

TOKEN = "t" * 32
IDS = ("pa", "pb")
FOLDERS = {"pa": "/w/pa", "pb": "/w/pb"}
SHARED_CWD = "/w/shared"


class Handle:
    """``records.spaces`` 핸들 가짜(폴더 기록 DB 하나, 대기 파일 없음)."""

    def __init__(self, db: RecordsDb) -> None:
        self.db = db
        self.host_id = "host-mine"

    @property
    def state(self) -> Any:
        return self.db.state

    @property
    def engine(self) -> Any:
        return self.db.engine

    def read_engine(self) -> Any:
        return self.db.read_engine()

    def writable_engine(self) -> Any:
        return self.db.writable_engine()

    def spool(self, run_id: str, kind: str, data: Any) -> None:
        pass

    def close(self) -> None:
        self.db.close()


class Spaces:
    """``project:<id>`` → 폴더 기록 DB(``records.spaces`` 모양). 모르는 id는 ``LookupError``."""

    def __init__(self, root: Path, registered: Sequence[str]) -> None:
        self.root = root
        self.registered = set(registered)
        self.handles: dict[str, Handle] = {}

    def open(self, space: str) -> Handle:
        project_id = space.split(":", 1)[1]
        if project_id not in self.registered:
            raise LookupError(space)
        if space not in self.handles:
            folder = self.root / project_id
            db = open_records_db(folder / "records.sqlite3", [BRANCH], backup_dir=folder / "b")
            self.handles[space] = Handle(db)
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def file(self, project_id: str) -> Path:
        return self.root / project_id / "records.sqlite3"


class Listing:
    """``projects.lookup`` 가짜(``list_projects`` 항목의 ``id``만)."""

    def __init__(self, ids: Sequence[str]) -> None:
        self.ids = list(ids)

    def list_projects(self) -> list[Any]:
        return [SimpleNamespace(id=i) for i in self.ids]


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders", IDS)
    yield found
    for handle in found.handles.values():
        handle.close()


def _run(run_id: str, project_id: str | None, created_at: float) -> Run:
    return Run.model_validate(
        {
            "id": run_id,
            "graph_id": "g",
            "graph_version": "v",
            "status": "completed",
            "input": {},
            "origin": "api",
            "project_id": project_id,
            "created_at": created_at,
        }
    )


def _run_events(run_id: str, cwd: str, session: str) -> list[RunEvent]:
    return [
        run_event(1, "run.started", {"status": "running", "cwd": cwd}, path=(), run_id=run_id),
        run_event(2, "agent.session_started", {"session_id": session}, run_id=run_id),
        run_event(3, "agent.message", {"role": "assistant", "text": "안녕"}, run_id=run_id),
    ]


def _seed_space(spaces: Spaces, project_id: str, run_id: str, session: str) -> SqliteStorage:
    """이전 프로세스가 그 프로젝트 기록 DB에 남긴 실행(이 프로세스는 아직 그 자리를 모른다)."""
    stored = SqliteStorage(spaces.open(f"project:{project_id}").writable_engine())
    stored.runs.save(_run(run_id, project_id, created_at=2.0))
    stored.runs.save_node_run(
        NodeRun(run_id=run_id, node_id="a", status="succeeded", backend_session_id=session)
    )
    stored.events.append_many(_run_events(run_id, FOLDERS[project_id], session))
    return stored


def _recorder(
    spaces: Spaces, project_ids: Sequence[str] | None = None
) -> tuple[SpaceRecorder, InMemoryStorage]:
    host = InMemoryStorage()
    host.runs.save(_run("r-shared", None, created_at=1.0))
    host.events.append_many(_run_events("r-shared", SHARED_CWD, "s-shared"))
    recorder = SpaceRecorder(
        host,
        space_records(lambda: spaces, prefix="project:"),
        project_ids=None if project_ids is None else (lambda: list(project_ids)),
    )
    return recorder, host


def _project_for(cwd: str) -> str | None:
    for project_id, folder in FOLDERS.items():
        if cwd == folder or cwd.startswith(folder + "/"):
            return project_id
    return None


def _ctx() -> QueryContext:
    return query_context(None, project_for=_project_for)


def _sessions(index: Any, **flt: object) -> list[LogSessionSummary]:
    found: list[LogSessionSummary] = index.list_sessions(LogFilter(limit=200).with_(**flt), _ctx())
    return found


def _run_ids(index: Any) -> set[str]:
    page = index.query_events(LogFilter(limit=500), _ctx())
    return {e.run_id for e in page.items}


def _ingestor(recorder: SpaceRecorder, project_ids: Any) -> tuple[LogIngestor, MemoryLogIndex]:
    item = platform_runs(recorder.runs, recorder.events, project_ids=project_ids)
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, LogRegistries())
    ingestor.add_runtime_source(item.source, classifier=item.classifier)
    return ingestor, index


def test_project_space_runs_are_indexed_with_project_id(spaces: Spaces) -> None:
    _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces)
    ingestor, index = _ingestor(recorder, lambda: list(IDS))
    ingestor.scan()

    assert _run_ids(index) == {"r-shared", "r-pa"}
    by_session = {s.session: s for s in _sessions(index)}
    assert by_session["s-pa"].project_id == "pa"
    assert by_session["s-pa"].cwd == FOLDERS["pa"]
    assert by_session["s-shared"].project_id is None
    # ?project= 거르기: 그 프로젝트 세션만
    assert [s.session for s in _sessions(index, project=["pa"])] == ["s-pa"]
    assert _sessions(index, project=["pb"]) == []
    # 기록 DB가 아직 없는 등록 프로젝트는 파일을 만들지 않는다
    assert not spaces.file("pb").exists()


def test_later_events_of_project_run_read_after_watermark(spaces: Spaces) -> None:
    stored = _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces)
    item = platform_runs(recorder.runs, recorder.events, project_ids=lambda: list(IDS))
    index = MemoryLogIndex()
    ingestor = LogIngestor(index, LogRegistries())
    ingestor.add_runtime_source(item.source, classifier=item.classifier)
    ingestor.scan()
    flt = LogFilter(limit=500).with_(run_id=["r-pa"])
    before = index.query_events(flt, _ctx()).items
    stored.events.append(run_event(4, "node.completed", {"status": "succeeded"}, run_id="r-pa"))
    item.source.invalidate("r-pa")  # runs.event 구독이 하는 일(끝난 Run의 마지막 seq 캐시 지움)
    ingestor.scan()
    after = index.query_events(flt, _ctx()).items
    assert len(after) == len(before) + 1  # 워터마크 뒤만(중복 없음)
    assert {e.cwd for e in after} == {FOLDERS["pa"]}  # 커서 state의 cwd를 이어 받는다
    assert [s.session for s in _sessions(index, project=["pa"])] == ["s-pa"]


def test_without_projects_lookup_only_shared_runs(spaces: Spaces) -> None:
    _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces)
    ingestor, index = _ingestor(recorder, None)
    ingestor.scan()
    assert _run_ids(index) == {"r-shared"}
    assert _sessions(index, project=["pa"]) == []


def test_unreadable_space_is_skipped(spaces: Spaces) -> None:
    _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces)
    # 등록부에는 있으나 공간을 열 수 없는 프로젝트(LookupError) — 그 공간만 건너뛴다
    ingestor, index = _ingestor(recorder, lambda: ["gone", "pa"])
    ingestor.scan()
    assert _run_ids(index) == {"r-shared", "r-pa"}


# ---- 모듈 조립(projects.lookup 있음/없음) -------------------------------------------


def _assembled(
    tmp_path: Path, recorder: SpaceRecorder, *, with_projects: bool
) -> tuple[Any, LocalLogs]:
    logs = LocalLogs()

    def build_runs(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUNS_READER, recorder.runs)
        ctx.provide(RUNS_EVENTS, recorder.events)
        return ModuleParts()

    def build_projects(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECTS_LOOKUP, Listing(IDS))
        return ModuleParts()

    modules = [
        local_logs_module(logs=logs),
        fake_module(
            "space-runs", kind="testing", provides=[RUNS_READER, RUNS_EVENTS], on_build=build_runs
        ),
        module,
    ]
    if with_projects:
        modules.append(
            fake_module(
                "projects", kind="testing", provides=[PROJECTS_LOOKUP], on_build=build_projects
            )
        )
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st"),
        events=EventBus(),
    )
    return assemble(modules, base=base), logs


@pytest.mark.parametrize(
    ("with_projects", "expected"), [(True, {"r-shared", "r-pa"}), (False, {"r-shared"})]
)
def test_module_reads_project_spaces_only_with_projects_lookup(
    tmp_path: Path, spaces: Spaces, with_projects: bool, expected: set[str]
) -> None:
    _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces)
    assembly, logs = _assembled(tmp_path, recorder, with_projects=with_projects)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        logs.request_scan()
        assert _run_ids(logs.index) == expected
        if with_projects:
            # 실행 세션 로그 경로도 프로젝트 Run을 찾는다(목록으로 본 자리를 기억)
            body = client.get("/api/v1/runs/r-pa/logs", params={"source": "platform-runs"})
            assert body.status_code == 200, body.text
            assert {i["session"] for i in body.json()["items"]} == {"s-pa"}


@pytest.mark.parametrize(("with_projects", "status"), [(True, 200), (False, 404)])
def test_run_logs_find_project_run_before_first_scan(
    tmp_path: Path, spaces: Spaces, with_projects: bool, status: int
) -> None:
    """재시작 직후(첫 수집 전, 그 공간을 아직 모름) ``/runs/{id}/logs``와 범위 ``run:<id>``가
    등록 프로젝트 기록 DB의 Run을 위치 찾기로 찾는다. 프로젝트 모듈이 꺼지면 공용만(404)."""
    _seed_space(spaces, "pa", "r-pa", "s-pa")
    recorder, _ = _recorder(spaces, IDS if with_projects else None)
    assembly, logs = _assembled(tmp_path, recorder, with_projects=with_projects)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        body = client.get("/api/v1/runs/r-pa/logs", params={"source": "platform-runs"})
        assert body.status_code == status, body.text
        if with_projects:
            assert body.json()["total"] == 0  # 아직 수집 전 — 찾기만 된다
            assert recorder.project_of_run("r-pa") == "pa"
            logs.request_scan()
            again = client.get("/api/v1/runs/r-pa/logs", params={"source": "platform-runs"})
            assert {i["session"] for i in again.json()["items"]} == {"s-pa"}
