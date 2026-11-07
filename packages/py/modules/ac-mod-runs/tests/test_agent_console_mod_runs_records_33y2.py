"""5.7R.33y2: ``project_id``가 있는 Run을 그 프로젝트 기록 DB에(선택 포트 ``records.spaces``).

실행 모듈은 프로젝트를 모른다 - 테스트 공급자가 공간 이름(``project:<id>``) → 기록 DB 핸들을 준다.

- 프로젝트 Run(+ 자식 Run)은 그 기록 DB에만, ``host_id``를 적는다. 프로젝트 없는 Run은 호스트.
- 쓸 수 없는 기록 DB → 409 ``project.records_unavailable``, 모르는 프로젝트 → 404.
- 재시작 복구는 자기 앱 Run만(``recover_space``), 쓰는 중에 잃으면 대기 줄 + 취소 알림.
- 1만 이벤트 쓰기 시간(호스트 DB 대비)을 기록한다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Graph, Run, RunEvent
from agent_console_mod_runs import (
    DEFINITIONS_LOOKUP,
    RECORDS_SPACES,
    SpaceRecorder,
    module,
    recover_space,
    space_records,
)
from agent_console_mod_runs.storage import BRANCH
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries
from agent_console_runtime.testing import BUILDERS as B
from agent_console_runtime.testing import (
    register_child_types,
    register_interaction_types,
    register_scheduling_types,
)
from agent_console_store import (
    DEFAULT_KINDS,
    InMemoryDefinitionStore,
    InMemoryStorage,
    RecordsDb,
    RecordsUnavailable,
    SqliteStorage,
    create_sqlite_engine,
    open_records_db,
    upgrade,
)

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


class Handle:
    """테스트용 ``RecordsHandle``: ``RecordsDb`` + ``host_id`` + 대기 줄(메모리).

    ``lost``·``readonly``면 쓰기를 거부한다."""

    def __init__(self, db: RecordsDb, host_id: str) -> None:
        self.db = db
        self.host_id = host_id
        self.spooled: list[tuple[str, str, Mapping[str, Any]]] = []
        self.lost = False
        self.readonly = False

    @property
    def state(self) -> Any:
        return self.db.state

    @property
    def engine(self) -> Any:
        return self.db.engine

    def read_engine(self) -> Any:
        return self.db.read_engine()

    def writable_engine(self) -> Any:
        if self.lost:
            raise RecordsUnavailable("folder_missing")
        if self.readonly:
            raise RecordsUnavailable("readonly")
        return self.db.writable_engine()

    def spool(self, run_id: str, kind: str, data: Mapping[str, Any]) -> None:
        self.spooled.append((run_id, kind, data))

    def close(self) -> None:
        self.db.close()


class Spaces:
    """``records.spaces`` 테스트 구현: ``project:<id>`` → 폴더 기록 DB(``runs`` 계보 포함)."""

    def __init__(self, root: Path, host_id: str = "host-mine") -> None:
        self.root = root
        self.host_id = host_id
        self.handles: dict[str, Handle] = {}

    def open(self, space: str) -> Handle:
        if not space.startswith("project:") or space.endswith(":nope"):
            raise LookupError(space)
        if space not in self.handles:
            folder = self.root / space.split(":", 1)[1]
            self.handles[space] = Handle(
                open_records_db(
                    folder / "records.sqlite3", [BRANCH], backup_dir=folder / "backups"
                ),
                self.host_id,
            )
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def close_all(self) -> None:
        for handle in self.handles.values():
            handle.close()


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    register_scheduling_types(registries)
    register_interaction_types(registries)
    register_child_types(registries)
    return registries


def _child() -> Graph:
    return B.graph([B.node("Q", type="t.asker", asks=[])], [B.reply("Q")], "child", entries=["Q"])


def _parent(graph_id: str) -> Graph:
    return B.graph(
        [B.node("N", type="t.nest", graph=_child().model_dump(mode="json"))],
        [B.reply("N")],
        graph_id,
        entries=["N"],
    )


def _module(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


@contextmanager
def _client(tmp_path: Path, spaces: Spaces | None) -> Iterator[TestClient]:
    library = InMemoryDefinitionStore(DEFAULT_KINDS)
    library.create("graph", _parent("g").model_dump(mode="json"))
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    modules = [module, _module("t-defs", DEFINITIONS_LOOKUP, library)]
    if spaces is not None:
        modules.append(_module("t-records", RECORDS_SPACES, spaces))
    assembly = assemble(modules, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _finish(client: TestClient, project: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {"graph_id": "g", "input": {}}
    if project is not None:
        body["project_id"] = project
    created = client.post(f"{API}/runs", json=body)
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    query = f"?project={project}" if project else ""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}{query}").json()
        if snap["run"]["status"] in TERMINAL and all(
            c["status"] in TERMINAL for c in snap["children"]
        ):
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders")
    yield found
    found.close_all()


def _space_runs(spaces: Spaces, project: str) -> list[Run]:
    engine = spaces.open(f"project:{project}").read_engine()
    return [] if engine is None else SqliteStorage(engine).runs.list()


def test_project_runs_and_children_go_to_that_records_db(tmp_path: Path, spaces: Spaces) -> None:
    with _client(tmp_path, spaces) as client:
        a = _finish(client, "pa")
        b = _finish(client, "pb")
        plain = _finish(client, None)
        assert a["run"]["status"] == "completed"
        assert a["run"]["host_id"] == "host-mine"
        assert len(a["children"]) == 1  # 자식 Run도 같은 공간에서 보인다
        listed = client.get(f"{API}/runs?project=pa").json()
        assert {r["id"] for r in listed} == {a["run"]["id"], a["children"][0]["id"]}
        assert all(r["project_id"] == "pa" for r in listed)
        assert client.get(f"{API}/runs?project=pa&source=app").json() == []
        host_roots = client.get(f"{API}/runs?root_only=true").json()
        assert [r["id"] for r in host_roots] == [plain["run"]["id"]]
        events = client.get(f"{API}/runs/{a['run']['id']}/events?project=pa").json()
        assert events[0]["type"] == "run.queued" or events
        assert plain["run"]["host_id"] is None
    assert len(_space_runs(spaces, "pa")) == 2
    assert len(_space_runs(spaces, "pb")) == 2
    assert b["run"]["project_id"] == "pb"


def test_unwritable_or_unknown_project_refuses_before_creating_run(
    tmp_path: Path, spaces: Spaces
) -> None:
    spaces.open("project:ro").readonly = True
    with _client(tmp_path, spaces) as client:
        body = {"graph_id": "g", "input": {}, "project_id": "ro"}
        refused = client.post(f"{API}/runs", json=body)
        assert refused.status_code == 409, refused.text
        error = refused.json()["error"]
        assert error["code"] == "project.records_unavailable"
        assert error["details"] == {"reason": "readonly", "project_id": "ro"}
        unknown = client.post(f"{API}/runs", json={**body, "project_id": "nope"})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
        assert client.get(f"{API}/runs").json() == []  # 호스트로 대신 쓰지 않았다


def test_without_port_project_runs_stay_in_host(tmp_path: Path) -> None:
    with _client(tmp_path, None) as client:
        snap = _finish(client, "pa")
        assert snap["run"]["project_id"] == "pa"
        listed = client.get(f"{API}/runs?project=pa").json()
        assert snap["run"]["id"] in {r["id"] for r in listed}


def _run(run_id: str, *, host: str | None, status: str = "running") -> Run:
    return Run.model_validate(
        {
            "id": run_id,
            "graph_id": "g",
            "graph_version": "v",
            "status": status,
            "input": {},
            "origin": "api",
            "project_id": "pa",
            "host_id": host,
            "created_at": 1.0,
        }
    )


def test_recover_space_only_interrupts_own_runs_not_running_here(spaces: Spaces) -> None:
    handle = spaces.open("project:pa")
    storage = SqliteStorage(handle.writable_engine())
    storage.runs.save(_run("own", host="host-mine"))
    storage.runs.save(_run("live", host="host-mine"))
    storage.runs.save(_run("other", host="host-other"))
    storage.runs.save(_run("unknown", host=None))
    records = space_records(lambda: spaces, prefix="project:")
    assert recover_space(records, "pa", active=lambda: ["live"]) is True
    got = {r.id: r.status for r in storage.runs.list()}
    assert got == {
        "own": "interrupted",
        "live": "running",
        "other": "running",
        "unknown": "running",
    }
    events = storage.events.list("own")
    assert [e.type for e in events][-1] == "run.interrupted"


def test_recover_space_without_file_does_not_create_it(spaces: Spaces, tmp_path: Path) -> None:
    records = space_records(lambda: spaces, prefix="project:")
    assert recover_space(records, "fresh", active=list) is True
    assert not (tmp_path / "folders" / "fresh" / "records.sqlite3").exists()


def _event(run_id: str, seq: int) -> RunEvent:
    return RunEvent.model_validate(
        {
            "event_id": f"{run_id}-{seq}",
            "run_id": run_id,
            "seq": seq,
            "ts": 1.0 + seq,
            "type": "log.info",
            "node_path": [],
            "payload": {"message": "x"},
        }
    )


def test_lost_records_spool_rest_and_notify_once(spaces: Spaces) -> None:
    lost: list[tuple[str, str]] = []
    records = space_records(lambda: spaces, prefix="project:")
    recorder = SpaceRecorder(
        InMemoryStorage(), records, on_lost=lambda r, why: lost.append((r, why))
    )
    run = _run("r1", host=None)
    recorder.runs.save(run)
    recorder.events.append_many([_event("r1", 1), _event("r1", 2)])
    handle = spaces.open("project:pa")
    handle.lost = True
    recorder.events.append_many([_event("r1", 3)])
    handle.lost = False  # 돌아와도 그 Run의 남은 쓰기는 계속 대기 줄로(순서 유지)
    recorder.events.append(_event("r1", 4))
    recorder.runs.save(run.model_copy(update={"status": "cancelled", "ended_at": 2.0}))
    assert lost == [("r1", "folder_missing")]
    kinds = [(k, d.get("seq")) for _, k, d in handle.spooled]
    assert kinds == [("event", 3), ("event", 4), ("run", None)]
    final = handle.spooled[-1][2]
    assert final["error"]["code"] == "project.records_unavailable"
    assert final["host_id"] == "host-mine"
    stored = SqliteStorage(handle.writable_engine())
    assert stored.events.last_seq("r1") == 2
    assert recorder.events.last_seq("r1") == 2


def test_ten_thousand_events_write_time_vs_host(spaces: Spaces, tmp_path: Path) -> None:
    """1만 이벤트(100개씩 묶음) 쓰기 시간: 프로젝트 기록 DB vs 호스트 DB 파일(기록, 넉넉한 상한)."""
    host_engine = create_sqlite_engine(tmp_path / "host.sqlite3")
    upgrade(host_engine)
    host = SqliteStorage(host_engine)
    records = space_records(lambda: spaces, prefix="project:")
    spaced = SpaceRecorder(InMemoryStorage(), records)
    plain = SpaceRecorder(host, None)

    def write(recorder: SpaceRecorder, project: str | None) -> float:
        run = _run("big", host=None).model_copy(update={"project_id": project})
        recorder.runs.save(run)
        started = time.perf_counter()
        for start in range(1, 10_001, 100):
            recorder.events.append_many([_event("big", s) for s in range(start, start + 100)])
        return time.perf_counter() - started

    host_s = write(plain, None)
    space_s = write(spaced, "pa")
    print(f"10k events: host {host_s:.2f}s, project records {space_s:.2f}s")
    assert spaced.events.last_seq("big") == 10_000
    assert host.events.last_seq("big") == 10_000
    assert space_s < host_s * 5 + 5  # 쓰기마다 리비전 재확인 비용이 크게 늘지 않는다
    host_engine.dispose()


# ---- WS ``run:<id>``와 프로젝트 기록 DB(요청 11/07 후속) -------------------------------------
def _ws_events(ws: Any, until_seq: int) -> list[int]:
    seqs: list[int] = []
    for _ in range(200):
        message = ws.receive_json()
        assert message["type"] == "run.event", message
        seqs.append(int(message["payload"]["seq"]))
        if seqs[-1] >= until_seq:
            return seqs
    raise AssertionError("이벤트가 끝나지 않았다")


def test_ws_run_topic_reads_project_records_after_scoped_read(
    tmp_path: Path, spaces: Spaces
) -> None:
    """이전 프로세스가 프로젝트 기록 DB에 남긴 Run: ``?project=`` 조회(웹이 먼저 하는 REST) 뒤
    ``run:<id>`` 구독이 그 기록 DB 이벤트를 재생한다. 조회 전에는 앱 기록만 보므로 ``not_found``
    (구독에는 프로젝트가 없다 - 웹은 REST 다음에 구독한다)."""
    stored = SqliteStorage(spaces.open("project:pa").writable_engine())
    stored.runs.save(_run("old", host="host-other", status="completed"))
    stored.events.append_many([_event("old", 1), _event("old", 2)])
    with _client(tmp_path, spaces) as client, client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "subscribe", "payload": {"topic": "run:old"}})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "not_found"
        assert client.get(f"{API}/runs/old?project=pa").status_code == 200
        ws.send_json({"type": "subscribe", "payload": {"topic": "run:old"}})
        assert _ws_events(ws, 2) == [1, 2]
        ws.send_json({"type": "subscribe", "payload": {"topic": "run:old", "since_seq": 1}})
        assert _ws_events(ws, 2) == [2]


def test_ws_run_topic_for_project_run_started_here(tmp_path: Path, spaces: Spaces) -> None:
    """이 프로세스에서 돈 프로젝트 Run은 조회 없이도 구독이 그 기록 DB 이벤트를 재생한다."""
    with _client(tmp_path, spaces) as client:
        snap = _finish(client, "pa")
        run_id = snap["run"]["id"]
        last = client.get(f"{API}/runs/{run_id}/events?project=pa").json()[-1]["seq"]
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": f"run:{run_id}"}})
            seqs = _ws_events(ws, last)
        assert seqs == list(range(1, last + 1))
    assert {r.id for r in _space_runs(spaces, "pa")} >= {run_id}
