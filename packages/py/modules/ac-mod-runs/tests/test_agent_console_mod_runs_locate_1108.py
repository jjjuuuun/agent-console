"""요청 11/08 후속: 실행 위치 찾기(``GET /runs/{id}/locate``)와 WS ``run:<id>``.

- 주소로 바로 연 실행(아직 이 프로세스가 모르는 프로젝트 기록 DB)의 등록 id를 알려 준다. 앱
  기록(호스트 DB)이면 null, 없으면 404, 여러 공간이면 409 ``run.ambiguous``.
- 등록 프로젝트 수 상한(``locate_max_projects``)을 넘는 공간은 읽지 않고, 기록 DB 파일을 만들지
  않는다. 찾은 자리는 기억해 다음에는 그 자리만 다시 본다.
- WS 구독은 모르는 프로젝트 기록 DB의 Run도 찾아 이벤트를 재생한다(``projects.lookup``이 있을 때).
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Graph, Run, RunEvent
from agent_console_mod_runs import (
    DEFINITIONS_LOOKUP,
    PROJECTS_LOOKUP,
    RECORDS_SPACES,
    RunAmbiguousError,
    RunNotFoundError,
    RunService,
    SpaceRecorder,
    module,
    space_records,
)
from agent_console_mod_runs.storage import BRANCH
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries
from agent_console_runtime.testing import BUILDERS as B
from agent_console_runtime.testing import make_registries
from agent_console_store import (
    DEFAULT_KINDS,
    InMemoryDefinitionStore,
    InMemoryStorage,
    RecordsDb,
    SqliteStorage,
    open_records_db,
)

API = "/api/v1"
TOKEN = "t" * 32
IDS = ("pa", "pb", "pc")
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


class Handle:
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
    """``project:<id>`` → 폴더 기록 DB. 등록되지 않은 id는 ``LookupError``(실제 풀과 같다)."""

    def __init__(self, root: Path, registered: Sequence[str]) -> None:
        self.root = root
        self.registered = set(registered)
        self.handles: dict[str, Handle] = {}
        self.opened: list[str] = []

    def open(self, space: str) -> Handle:
        project_id = space.split(":", 1)[1]
        if project_id not in self.registered:
            raise LookupError(space)
        self.opened.append(project_id)
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


def _run(run_id: str, project_id: str | None, status: str = "completed") -> Run:
    return Run.model_validate(
        {
            "id": run_id,
            "graph_id": "g",
            "graph_version": "v",
            "status": status,
            "input": {},
            "origin": "api",
            "project_id": project_id,
            "host_id": "host-other",
            "created_at": 1.0,
        }
    )


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


def _seed(spaces: Spaces, project_id: str, run_id: str, *, events: int = 0) -> None:
    """이전 프로세스가 그 프로젝트 기록 DB에 남긴 Run(이 프로세스는 아직 그 자리를 모름)."""
    stored = SqliteStorage(spaces.open(f"project:{project_id}").writable_engine())
    stored.runs.save(_run(run_id, project_id))
    if events:
        stored.events.append_many([_event(run_id, seq) for seq in range(1, events + 1)])
    spaces.opened.clear()


def _recorder(
    spaces: Spaces, ids: Sequence[str] | None = IDS, limit: int = 200
) -> tuple[SpaceRecorder, InMemoryStorage]:
    host = InMemoryStorage()
    recorder = SpaceRecorder(
        host,
        space_records(lambda: spaces, prefix="project:"),
        project_ids=(lambda: list(ids)) if ids is not None else None,
        locate_limit=limit,
    )
    return recorder, host


# ---- 기록 자리 ------------------------------------------------------------------


def test_locate_finds_unknown_project_and_host(spaces: Spaces) -> None:
    _seed(spaces, "pb", "r1", events=2)
    recorder, host = _recorder(spaces)
    host.runs.save(_run("r-app", None))
    assert recorder.locate("r1") == ["pb"]
    # 찾은 자리를 기억해 ?project= 없는 run_id 조회(WS 재생)가 그 공간을 본다
    assert recorder.project_of_run("r1") == "pb"
    found = recorder.runs.get("r1")
    assert found is not None
    assert found.project_id == "pb"
    assert [e.seq for e in recorder.events.list("r1")] == [1, 2]
    assert recorder.locate("r-app") == [None]
    assert recorder.locate("nope") == []
    # 기록 DB가 없는 프로젝트는 읽기만 하고 파일을 만들지 않는다
    assert not spaces.file("pa").exists()
    assert not spaces.file("pc").exists()


def test_locate_remembers_place_and_rechecks_it(spaces: Spaces) -> None:
    _seed(spaces, "pc", "r1")
    recorder, _ = _recorder(spaces)
    assert recorder.locate("r1") == ["pc"]
    spaces.opened.clear()
    assert recorder.locate("r1") == ["pc"]
    assert spaces.opened == ["pc"]  # 기억한 자리만 다시 본다


def test_locate_ambiguous_and_limits(spaces: Spaces) -> None:
    _seed(spaces, "pa", "dup")
    _seed(spaces, "pc", "dup")
    _seed(spaces, "pc", "r3")
    recorder, host = _recorder(spaces)
    host.runs.save(_run("dup", None))
    assert recorder.locate("dup") == ["pa", "pc", None]
    limited, _ = _recorder(spaces, limit=2)
    assert limited.locate("r3") == []  # 앞의 2개(pa, pb)만 읽는다
    none, _ = _recorder(spaces, limit=0)
    assert none.locate("r3") == []
    unlisted, _ = _recorder(spaces, ids=None)
    assert unlisted.locate("r3") == []  # 목록이 없으면 아는 공간과 호스트만
    unlisted.for_project("pc").get("r3")  # ?project= 조회로 본 공간은 목록 없이도 본다
    assert unlisted.locate("r3") == ["pc"]


def test_locate_skips_unregistered_ids(spaces: Spaces) -> None:
    _seed(spaces, "pb", "r1")
    recorder, _ = _recorder(spaces, ids=["gone", "pb"])
    assert recorder.locate("r1") == ["pb"]


def test_without_records_port_host_only() -> None:
    host = InMemoryStorage()
    host.runs.save(_run("r-app", "p1"))
    recorder = SpaceRecorder(host, None, project_ids=lambda: ["p1"])
    assert recorder.locate("r-app") == [None]
    assert recorder.locate("nope") == []


# ---- REST·WS(모듈 조립) ----------------------------------------------------------


def _registries() -> Registries:
    registries = make_registries()
    load_registries(registries)
    return registries


def _graph() -> Graph:
    return B.graph([B.node("A")], [B.reply("A")], "g", entries=["A"])


def _provider(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


@contextmanager
def _client(tmp_path: Path, spaces: Spaces | None, listing: Listing | None) -> Iterator[TestClient]:
    library = InMemoryDefinitionStore(DEFAULT_KINDS)
    library.create("graph", _graph().model_dump(mode="json"))
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    modules = [module, _provider("t-defs", DEFINITIONS_LOOKUP, library)]
    if spaces is not None:
        modules.append(_provider("t-records", RECORDS_SPACES, spaces))
    if listing is not None:
        modules.append(_provider("t-projects", PROJECTS_LOOKUP, listing))
    assembly = assemble(modules, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def test_rest_locate(tmp_path: Path, spaces: Spaces) -> None:
    _seed(spaces, "pb", "r1")
    _seed(spaces, "pa", "dup")
    _seed(spaces, "pc", "dup")
    with _client(tmp_path, spaces, Listing(IDS)) as client:
        found = client.get(f"{API}/runs/r1/locate")
        assert found.status_code == 200, found.text
        assert found.json() == {"project_id": "pb"}
        detail = client.get(f"{API}/runs/r1", params={"project": "pb"})
        assert detail.status_code == 200
        assert detail.json()["run"]["project_id"] == "pb"
        missing = client.get(f"{API}/runs/nope/locate")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
        ambiguous = client.get(f"{API}/runs/dup/locate")
        assert ambiguous.status_code == 409
        body = ambiguous.json()["error"]
        assert body["code"] == "run.ambiguous"
        assert body["details"]["project_ids"] == ["pa", "pc"]
        # 앱 기록(프로젝트 없음)에서 돈 Run은 null
        created = client.post(f"{API}/runs", json={"graph_id": "g", "input": {}})
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        _wait(client, run_id)
        assert client.get(f"{API}/runs/{run_id}/locate").json() == {"project_id": None}


def _wait(client: TestClient, run_id: str, project: str | None = None) -> None:
    params = {"project": project} if project else {}
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap = client.get(f"{API}/runs/{run_id}", params=params).json()
        if snap["run"]["status"] in TERMINAL:
            return
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_rest_locate_project_run_started_here(tmp_path: Path, spaces: Spaces) -> None:
    with _client(tmp_path, spaces, None) as client:
        body = {"graph_id": "g", "input": {}, "project_id": "pa"}
        created = client.post(f"{API}/runs", json=body)
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        assert client.get(f"{API}/runs/{run_id}/locate").json() == {"project_id": "pa"}
        _wait(client, run_id, "pa")
        assert client.get(f"{API}/runs/{run_id}/locate").json() == {"project_id": "pa"}


def test_rest_locate_without_records_port_is_host_only(tmp_path: Path) -> None:
    with _client(tmp_path, None, Listing(["p1"])) as client:
        body = {"graph_id": "g", "input": {}, "project_id": "p1"}
        created = client.post(f"{API}/runs", json=body)
        run_id = created.json()["id"]
        _wait(client, run_id)
        assert client.get(f"{API}/runs/{run_id}/locate").json() == {"project_id": None}
        assert client.get(f"{API}/runs/nope/locate").status_code == 404


def _ws_events(ws: Any, until_seq: int) -> list[int]:
    seqs: list[int] = []
    for _ in range(200):
        message = ws.receive_json()
        assert message["type"] == "run.event", message
        seqs.append(int(message["payload"]["seq"]))
        if seqs[-1] >= until_seq:
            return seqs
    raise AssertionError("이벤트가 끝나지 않았다")


def test_ws_subscribe_finds_unknown_project_run(tmp_path: Path, spaces: Spaces) -> None:
    """재시작 직후(그 공간을 아직 모름) ``run:<id>`` 구독이 등록 프로젝트 기록 DB의 Run을 찾아
    이벤트를 재생한다. 없는 Run은 ``not_found``."""
    _seed(spaces, "pb", "old", events=2)
    with (
        _client(tmp_path, spaces, Listing(IDS)) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_json({"type": "subscribe", "payload": {"topic": "run:old"}})
        assert _ws_events(ws, 2) == [1, 2]
        ws.send_json({"type": "subscribe", "payload": {"topic": "run:nope"}})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "not_found"


def test_service_locate_errors(spaces: Spaces) -> None:
    """``RunService.locate``: 없음 = ``RunNotFoundError``, 여러 곳 = ``RunAmbiguousError``."""
    _seed(spaces, "pa", "dup")
    _seed(spaces, "pb", "dup")
    recorder, _ = _recorder(spaces)
    service = SimpleNamespace(
        runtime=SimpleNamespace(get=lambda _id: None), records=recorder, _runs=recorder.runs
    )
    with pytest.raises(RunNotFoundError):
        RunService.locate(service, "nope")  # type: ignore[arg-type]
    with pytest.raises(RunAmbiguousError) as caught:
        RunService.locate(service, "dup")  # type: ignore[arg-type]
    assert caught.value.project_ids == ["pa", "pb"]
