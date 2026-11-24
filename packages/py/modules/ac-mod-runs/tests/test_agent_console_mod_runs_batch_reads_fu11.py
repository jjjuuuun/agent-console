"""FU.11: ``runs.reader.list_node_runs_many``·``runs.events.list_many``가 Run의 자리를 따라간다.

호스트 DB의 Run과 이 프로세스가 아는 공간(프로젝트 기록 DB)의 Run을 한 번에 물으면 자리마다 묶어
읽는다(Run마다 묻지 않는다). 읽을 수 없는 자리의 Run은 빠진다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import KnownRecordsUnavailableReasons, NodeRun, Run, RunEvent
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.storage import BRANCH
from agent_console_store import (
    RecordsDb,
    RecordsUnavailable,
    SqliteDatabase,
    SqliteStorage,
    open_records_db,
)


class _Spaces:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.dbs: dict[str, RecordsDb] = {}

    def open(self, space: str) -> RecordsDb:
        if space.endswith(":gone"):
            raise RecordsUnavailable(KnownRecordsUnavailableReasons.FOLDER_MISSING)
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


def _put(storage: Any, run_id: str, project_id: str | None = None) -> Run:
    run = Run(
        id=run_id,
        graph_id="g",
        graph_version="v",
        status="completed",
        input={},
        origin="api",
        created_at=1.0,
        project_id=project_id,
    )
    storage.runs.save(run)
    storage.runs.save_node_run(NodeRun(run_id=run_id, node_id="a", status="succeeded"))
    storage.events.append_many(
        [
            RunEvent(
                event_id=f"{run_id}-{seq}",
                run_id=run_id,
                seq=seq,
                ts=1.0,
                node_path=["a"],
                type=kind,
                payload={},
            )
            for seq, kind in ((1, "agent.session_started"), (2, "node.started"))
        ]
    )
    return run


def test_batch_reads_follow_run_places(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    db.upgrade([BRANCH])
    host = SqliteStorage(db.engine)
    spaces = _Spaces(tmp_path / "spaces")
    project = SqliteStorage(spaces.open("project:p1").writable_engine())
    recorder = SpaceRecorder(host, space_records(lambda: spaces, prefix="project:"))
    _put(host, "h1")
    recorder.remember([_put(project, "p1-run", "p1")], "p1")
    recorder.remember([_put(host, "lost")], "gone")  # 읽을 수 없는 자리(폴더 없음)

    node_runs = recorder.runs.list_node_runs_many(["h1", "p1-run", "lost", "none"])
    assert {k: [n.node_id for n in v] for k, v in node_runs.items()} == {
        "h1": ["a"],
        "p1-run": ["a"],
    }
    events = recorder.events.list_many(
        {"h1": 0, "p1-run": 0, "lost": 0}, type_prefixes=["agent.session_started"]
    )
    assert {k: [e.seq for e in v] for k, v in events.items()} == {"h1": [1], "p1-run": [1]}
    rest = project.events.list("p1-run", since_seq=1)
    assert recorder.events.list_many({"p1-run": 1}) == {"p1-run": rest}
    for handle in spaces.dbs.values():
        handle.close()
    db.close()
