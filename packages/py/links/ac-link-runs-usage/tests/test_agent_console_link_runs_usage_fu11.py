"""FU.11: 프로젝트 토큰 집계의 앱 기록 옛 Run(R22)과 질의 수(R17).

- "이 프로젝트" 집계는 앱 기록에서 그 ``project_id``의 최근 ``limit``개를 저장소 조건으로 바로
  읽는다. 다른 실행이 많아도 옛 프로젝트 Run이 빠지지 않는다. 기록 공간이 있는 조립(``mod-runs``
  ``SpaceRecorder``)에서도 앱 기록을 읽고 프로젝트 기록 DB를 두 번 세지 않는다.
- 다시 읽을 Run은 출처마다 묶어 읽는다: 처음 집계 = Run 목록 + 이벤트 + NodeRun 질의(출처마다),
  두 번째 = Run 목록만. 묶어 읽기가 없는 출처는 Run마다 읽고 결과는 같다.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import NodeRun, Run, RunEvent, RunStatus, Usage
from agent_console_link_runs_usage import (
    AppScopedRuns,
    BatchEvents,
    BatchNodeRuns,
    IncrementalTokenRollups,
    project_rollup_sources,
)
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.storage import BRANCH
from agent_console_store import (
    InMemoryStorage,
    RecordsDb,
    SqliteDatabase,
    SqliteStorage,
    open_records_db,
)


def _save(
    storage: Any,
    run_id: str,
    *,
    at: float,
    tokens: int,
    graph: str = "g",
    status: RunStatus = "completed",
    project_id: str | None = None,
    subagent: bool = False,
) -> None:
    storage.runs.save(
        Run(
            id=run_id,
            graph_id=graph,
            graph_version="v",
            status=status,
            input={},
            origin="api",
            created_at=at,
            project_id=project_id,
        )
    )
    storage.runs.save_node_run(
        NodeRun(
            run_id=run_id,
            node_id="a",
            status="succeeded",
            started_at=at,
            usage=Usage(input_tokens=tokens, output_tokens=0),
        )
    )
    events = [
        RunEvent(
            event_id=f"{run_id}-1",
            run_id=run_id,
            seq=1,
            ts=at,
            node_path=["a"],
            attempt=1,
            actor="agent-x",
            type="agent.session_started",
            payload={"model": "m"},
        ),
        RunEvent(
            event_id=f"{run_id}-2",
            run_id=run_id,
            seq=2,
            ts=at,
            node_path=["a"],
            type="node.started",
            payload={},
        ),
    ]
    if subagent:
        events.append(
            RunEvent(
                event_id=f"{run_id}-3",
                run_id=run_id,
                seq=3,
                ts=at,
                node_path=["a"],
                actor="helper",
                type="agent.subagent_stopped",
                payload={"subagent_id": "s1", "usage": {"total_tokens": 7}},
            )
        )
    storage.events.append_many(events)


def _by_graph(rows: list[Any]) -> dict[str, int]:
    found: dict[str, int] = {}
    for row in rows:
        found[row.graph_id] = found.get(row.graph_id, 0) + int(row.usage.input_tokens or 0)
    return found


def _host(tmp_path: Path) -> tuple[SqliteDatabase, SqliteStorage]:
    """앱 기록 DB(계보 ``runs`` 포함 — ``project_id`` 열·색인 ``ix_runs_project_created``)."""
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    db.upgrade([BRANCH])
    return db, SqliteStorage(db.engine)


@contextmanager
def _selects(engine: sa.Engine) -> Iterator[list[str]]:
    found: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            found.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        yield found
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)


# --- R22: 앱 기록의 옛 프로젝트 Run ---


@pytest.mark.parametrize("which", ["memory", "sqlite"])
def test_project_scope_reads_old_app_runs_beyond_other_runs(tmp_path: Path, which: str) -> None:
    """다른 실행이 ``limit``보다 많아도 그 프로젝트의 옛 앱 Run이 집계에 들어간다."""
    db: SqliteDatabase | None = None
    host: Any
    if which == "memory":
        host = InMemoryStorage()
    else:
        db, host = _host(tmp_path)
    _save(host, "old-p1", at=1.0, tokens=5, graph="legacy-p1", project_id="p1")
    for i in range(10):
        _save(host, f"other-{i}", at=10.0 + i, tokens=1, graph="other", project_id="p2")
    _save(host, "shared", at=30.0, tokens=1, graph="shared")
    rollups = IncrementalTokenRollups(host.runs, host.events)
    assert _by_graph(rollups.rollups(limit=3, tz=UTC, project_id="p1")) == {"legacy-p1": 5}
    assert _by_graph(rollups.rollups(limit=3, tz=UTC, project_id="p2")) == {"other": 3}
    assert _by_graph(rollups.rollups(limit=3, tz=UTC)) == {"other": 2, "shared": 1}
    if db is not None:
        rollups.rollups(limit=3, tz=UTC, project_id="p1")
        with _selects(db.engine) as selects:
            rollups.rollups(limit=3, tz=UTC, project_id="p1")
        # 캐시된 끝난 Run은 다시 읽지 않는다: 그 프로젝트 조건이 든 Run 목록 질의 하나
        assert len(selects) == 1
        assert "project_id" in selects[0]
        db.close()


@dataclass
class _Project:
    id: str
    archived: bool = False


class _Lookup:
    def __init__(self, projects: list[_Project]) -> None:
        self.projects = projects

    def list_projects(self) -> list[_Project]:
        return list(self.projects)


class _Spaces:
    """``records.spaces`` 가짜: ``project:<id>`` → 폴더 기록 DB(계보 ``runs`` 포함)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dbs: dict[str, RecordsDb] = {}

    def open(self, space: str) -> RecordsDb:
        if space not in self.dbs:
            folder = self.root / space.split(":", 1)[1]
            self.dbs[space] = open_records_db(
                folder / "records.sqlite3", [BRANCH], backup_dir=folder / "bk"
            )
        return self.dbs[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def close_all(self) -> None:
        for db in self.dbs.values():
            db.close()


def test_spaced_runs_reader_reads_app_records_once(tmp_path: Path) -> None:
    """``mod-runs``의 ``runs.reader``(기록 공간 있음): 앱 기록은 ``for_project(None)``으로 읽는다.

    ``list(project_id=)``는 이 조립에서 프로젝트 기록 DB를 읽으므로, 그대로 쓰면 프로젝트 Run을
    두 번 세고 앱 기록의 옛 Run은 빠진다.
    """
    db, host = _host(tmp_path)
    spaces = _Spaces(tmp_path / "spaces")
    _save(host, "old-p1", at=1.0, tokens=5, graph="legacy-p1", project_id="p1")
    for i in range(5):
        _save(host, f"other-{i}", at=10.0 + i, tokens=1, graph="other")
    project = SqliteStorage(spaces.open("project:p1").writable_engine())
    _save(project, "p1-a", at=20.0, tokens=100, graph="p1", project_id="p1")
    _save(project, "p1-b", at=21.0, tokens=200, graph="p1", project_id="p1")

    stores = space_records(lambda: spaces, prefix="project:")
    recorder = SpaceRecorder(host, stores)
    assert recorder.spaced
    assert isinstance(recorder.runs, AppScopedRuns)
    assert isinstance(recorder.runs, BatchNodeRuns)
    assert isinstance(recorder.events, BatchEvents)
    lookup = _Lookup([_Project("p1")])
    rollups = IncrementalTokenRollups(
        recorder.runs, recorder.events, extra=project_rollup_sources(lambda: lookup, stores)
    )
    assert _by_graph(rollups.rollups(limit=3, tz=UTC, project_id="p1")) == {
        "p1": 300,
        "legacy-p1": 5,
    }
    assert _by_graph(rollups.rollups(limit=10, tz=UTC)) == {"other": 5, "legacy-p1": 5, "p1": 300}
    spaces.close_all()
    db.close()


# --- R17: 질의 수(N+1 묶기) ---


def test_first_rollup_reads_each_source_in_batches(tmp_path: Path) -> None:
    """처음 집계는 출처마다 Run 목록·이벤트·NodeRun 질의 하나씩, 두 번째는 Run 목록만이다."""
    db, host = _host(tmp_path)
    for i in range(30):
        _save(host, f"r{i:02d}", at=float(i + 1), tokens=1, subagent=i % 3 == 0)
    rollups = IncrementalTokenRollups(host.runs, host.events)
    with _selects(db.engine) as selects:
        first = rollups.rollups(limit=50, tz=UTC)
    assert len(selects) == 3  # 목록 + 이벤트 묶음 + NodeRun 묶음(Run 30개, N+1 아님)
    with _selects(db.engine) as selects:
        assert rollups.rollups(limit=50, tz=UTC) == first
    assert len(selects) == 1
    # 새 Run과 표시된 Run만 묶어 다시 읽는다
    _save(host, "new", at=99.0, tokens=1)
    rollups.mark(type("E", (), {"run_id": "r03"})())
    with _selects(db.engine) as selects:
        third = rollups.rollups(limit=50, tz=UTC)
    assert len(selects) == 3
    assert _by_graph(third) == {"g": 31}
    db.close()


class _PerRun:
    """묶어 읽기가 없는 출처(Run마다 읽기로 떨어진다)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def list(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.list(*args, **kwargs)

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        found: builtins.list[NodeRun] = self._inner.list_node_runs(run_id)
        return found


def test_batched_and_per_run_reads_agree_with_increments(tmp_path: Path) -> None:
    """묶어 읽기와 Run마다 읽기의 결과가 같다(끝나지 않은 Run의 형식별 워터마크 포함)."""
    storage = InMemoryStorage()
    for i in range(6):
        _save(storage, f"r{i}", at=float(i + 1), tokens=i + 1, subagent=i % 2 == 0)
    _save(storage, "live", at=50.0, tokens=3, status="running")
    batched = IncrementalTokenRollups(storage.runs, storage.events)
    per_run = IncrementalTokenRollups(_PerRun(storage.runs), _PerRun(storage.events))
    assert not isinstance(_PerRun(storage.events), BatchEvents)
    assert batched.rollups(limit=20, tz=UTC) == per_run.rollups(limit=20, tz=UTC)
    # 끝나지 않은 Run에 새 사용량 이벤트가 붙으면 둘 다 그 뒤만 더한다
    storage.events.append_many(
        [
            RunEvent(
                event_id="live-9",
                run_id="live",
                seq=9,
                ts=51.0,
                node_path=["a"],
                actor="helper",
                type="agent.subagent_stopped",
                payload={"subagent_id": "s9", "usage": {"total_tokens": 11}},
            )
        ]
    )
    first = batched.rollups(limit=20, tz=UTC)
    assert first == per_run.rollups(limit=20, tz=UTC)
    assert batched.rollups(limit=20, tz=UTC) == first  # 같은 이벤트를 두 번 더하지 않는다
    subagent_total = sum(
        int(row.usage.total_tokens or 0) for row in first if row.agent_id == "helper"
    )
    assert subagent_total == 7 * 3 + 11


def test_spaced_first_rollup_is_three_queries_per_source_without_duplicates(
    tmp_path: Path,
) -> None:
    """기록 공간 조립: 앱 기록·프로젝트 기록 DB 각각 처음 집계 질의 3회, 합친 결과에 중복이 없다."""
    db, host = _host(tmp_path)
    spaces = _Spaces(tmp_path / "spaces")
    for i in range(12):
        _save(host, f"app-{i:02d}", at=float(i + 1), tokens=1, graph="app", project_id="p1")
    project = SqliteStorage(spaces.open("project:p1").writable_engine())
    for i in range(12):
        _save(project, f"prj-{i:02d}", at=100.0 + i, tokens=10, graph="prj", project_id="p1")
    stores = space_records(lambda: spaces, prefix="project:")
    recorder = SpaceRecorder(host, stores)
    lookup = _Lookup([_Project("p1")])
    rollups = IncrementalTokenRollups(
        recorder.runs, recorder.events, extra=project_rollup_sources(lambda: lookup, stores)
    )
    project_engine = spaces.open("project:p1").writable_engine()
    with _selects(db.engine) as app_selects, _selects(project_engine) as prj_selects:
        rows = rollups.rollups(limit=50, tz=UTC, project_id="p1")
    # 표 존재 확인(sqlite_master)은 기록 열기 점검이라 빼고, 기록 표 질의만 센다
    app_reads = [s for s in app_selects if "sqlite_master" not in s]
    prj_reads = [s for s in prj_selects if "sqlite_master" not in s]
    assert len(app_reads) == 3
    assert len(prj_reads) == 3
    assert _by_graph(rows) == {"app": 12, "prj": 120}
    keys = [(r.graph_id, r.run_id) for r in rows if hasattr(r, "run_id")]
    assert len(keys) == len(set(keys))
    spaces.close_all()
    db.close()
