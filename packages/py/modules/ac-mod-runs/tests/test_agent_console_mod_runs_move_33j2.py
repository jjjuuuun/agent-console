"""5.7R.33j2: 앱 DB 옛 Run 기록 -> 프로젝트 기록 DB 옮기기(`RunMover`, REST)."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Interaction,
    NodeRun,
    RecordsMoveRequest,
    Run,
    RunEvent,
)
from agent_console_mod_runs import (
    RECORDS_SPACES,
    RunMover,
    module,
    space_records,
)
from agent_console_mod_runs.storage import BRANCH
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries
from agent_console_store import (
    RecordsDb,
    RecordsMove,
    RecordsUnavailable,
    SqliteDatabase,
    SqliteStorage,
    create_sqlite_engine,
    open_records_db,
    upgrade,
)

API = "/api/v1"
TOKEN = "t" * 32
RUN_TABLES = ("runs", "node_runs", "run_events", "interactions")


class Handle:
    """테스트용 ``RecordsHandle``: ``RecordsDb`` + ``host_id``."""

    def __init__(self, db: RecordsDb, host_id: str) -> None:
        self.db = db
        self.host_id = host_id
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
        if self.readonly:
            raise RecordsUnavailable("readonly")
        return self.db.writable_engine()

    def spool(self, run_id: str, kind: str, data: Mapping[str, Any]) -> None:
        pass

    def close(self) -> None:
        self.db.close()


class Spaces:
    def __init__(self, root: Path) -> None:
        self.root = root
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
                "host-mine",
            )
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def close_all(self) -> None:
        for handle in self.handles.values():
            handle.close()


def run(id: str, created_at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id,
        "graph_id": "g",
        "graph_version": "h",
        "status": "completed",
        "input": {"text": "안녕"},
        "origin": "api",
        "created_at": created_at,
    }
    fields.update(kw)
    return Run(**fields)


def event(run_id: str, seq: int) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-e{seq}",
        run_id=run_id,
        seq=seq,
        ts=100.0 + seq,
        type="log.info",
        node_path=["n1"],
        actor="pl",
    )


def seed(storage: SqliteStorage, project: str | None, *, events: int = 2) -> None:
    """루트 a(자식 c), 루트 b, 루트 d(실행 중): 노드·이벤트·상호작용 포함."""
    for r in (
        run("a", 1.0, project_id=project),
        run("c", 2.0, project_id=project, parent_run_id="a", root_run_id="a"),
        run("b", 3.0, project_id=project, conversation_id="conv1"),
        run("d", 4.0, project_id=project, status="running"),
    ):
        storage.runs.save(r)
        storage.runs.save_node_run(NodeRun(run_id=r.id, node_id="n1", status="succeeded"))
        for seq in range(1, events + 1):
            storage.events.append(event(r.id, seq))
    storage.interactions.save(
        Interaction(
            id="i1",
            run_id="a",
            node_id="n1",
            kind="question",
            status="pending",
            created_at=5.0,
            payload={"question": "?"},
            response_schema={"type": "object"},
            root_run_id="a",
        )
    )


def table_digest(engine: sa.Engine, ids: tuple[str, ...]) -> dict[str, str]:
    """표별 내용 해시(`project_id`가 달라지므로 `runs`는 그 열과 doc의 그 값을 뺀다)."""
    out: dict[str, str] = {}
    marks = ",".join("?" for _ in ids)
    with engine.connect() as c:
        for table, column in (
            ("runs", "id"),
            ("node_runs", "run_id"),
            ("run_events", "run_id"),
            ("interactions", "run_id"),
        ):
            h = hashlib.sha256()
            cols = [x["name"] for x in sa.inspect(c).get_columns(table)]
            order = ", ".join(cols)
            rows = c.exec_driver_sql(
                f"select {order} from {table} where {column} in ({marks}) order by {order}", ids
            )
            for row in rows:
                values = dict(zip(cols, row, strict=True))
                if table == "runs":
                    values.pop("project_id", None)
                    values["doc"] = _strip_project(values["doc"])
                h.update(repr(sorted(values.items(), key=lambda kv: kv[0])).encode())
            out[table] = h.hexdigest()
    return out


def _strip_project(doc: str) -> str:
    import json

    found = json.loads(doc)
    found.pop("project_id", None)
    return json.dumps(found, sort_keys=True)


def count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as c:
        return int(c.exec_driver_sql(f"select count(*) from {table}").scalar() or 0)


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders")
    yield found
    found.close_all()


@pytest.fixture
def app_db(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    db.upgrade([BRANCH])
    yield db
    db.close()


def mover_of(db: SqliteDatabase, spaces: Spaces) -> RunMover:
    return RunMover(lambda: db.engine, space_records(lambda: spaces, prefix="project:"))


def target_engine(spaces: Spaces, project: str) -> sa.Engine:
    return spaces.open(f"project:{project}").writable_engine()  # type: ignore[no-any-return]


def test_move_ids_tree_with_children_events_and_interactions(
    app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(SqliteStorage(app_db.engine), "p1")
    before = table_digest(app_db.engine, ("a", "c"))
    result = mover_of(app_db, spaces).move(
        RecordsMoveRequest(project_id="p1", select="ids", ids=["a"])
    )
    assert (result.moved, result.skipped, result.failed) == (2, 0, [])  # a + 자식 c
    target = target_engine(spaces, "p1")
    assert table_digest(target, ("a", "c")) == before  # 행 수·내용 같음
    assert (count(target, "runs"), count(target, "node_runs")) == (2, 2)
    assert (count(target, "run_events"), count(target, "interactions")) == (4, 1)
    for table in RUN_TABLES:  # 원본에서는 a·c가 사라졌다
        column = "id" if table == "runs" else "run_id"
        with app_db.engine.connect() as c:
            left = c.exec_driver_sql(f"select count(*) from {table} where {column} in ('a','c')")
            assert left.scalar() == 0
    moved = SqliteStorage(target).runs.get("c")
    assert moved is not None
    assert moved.project_id == "p1"
    assert moved.root_run_id == "a"


def test_move_carries_run_labels_6r6(app_db: SqliteDatabase, spaces: Spaces) -> None:
    """6R.6: 표 `run_labels`(`runs_0004`)가 코드 수정 없이 따라온다 - 전후 행 수·내용 같음."""
    storage = SqliteStorage(app_db.engine)
    storage.runs.save(run("a", 1.0, project_id="p1", labels={"sdd.spec": "s1", "sdd.task": "t1"}))
    storage.runs.save(run("c", 2.0, project_id="p1", parent_run_id="a", root_run_id="a"))
    storage.runs.save(run("b", 3.0, project_id="p1", labels={"sdd.spec": "s2"}))
    storage.runs.save(run("keep", 4.0, project_id="other", labels={"sdd.spec": "s1"}))
    result = mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert (result.moved, result.failed) == (3, [])
    target = target_engine(spaces, "p1")
    assert count(target, "run_labels") == 3
    with target.connect() as c:
        rows = set(c.exec_driver_sql("select run_id, key, value from run_labels").all())
    assert rows == {("a", "sdd.spec", "s1"), ("a", "sdd.task", "t1"), ("b", "sdd.spec", "s2")}
    with app_db.engine.connect() as c:  # 원본에는 안 옮긴 Run의 라벨만 남는다
        left = set(c.exec_driver_sql("select run_id, key, value from run_labels").all())
    assert left == {("keep", "sdd.spec", "s1")}
    items, _ = SqliteStorage(target).runs.page(labels={"sdd.spec": "s1"})
    assert [r.id for r in items] == ["a"]


def test_select_project_and_null_move_roots_and_skip_running(
    app_db: SqliteDatabase, spaces: Spaces
) -> None:
    storage = SqliteStorage(app_db.engine)
    seed(storage, "p1")
    storage.runs.save(run("x", 9.0, project_id="other"))
    storage.runs.save(run("n", 10.0))  # 프로젝트 없음
    mover = mover_of(app_db, spaces)
    first = mover.move(RecordsMoveRequest(project_id="p1", select="project"))
    # 루트 a(+c), b는 옮기고, 실행 중인 d는 failed
    assert (first.moved, first.skipped) == (3, 0)
    assert [(i.code, i.details["id"]) for i in first.failed] == [("run.move_busy", "d")]
    assert count(app_db.engine, "runs") == 3  # d, x, n
    second = mover.move(RecordsMoveRequest(project_id="p1", select="null"))
    assert (second.moved, second.failed) == (1, [])
    moved = SqliteStorage(target_engine(spaces, "p1")).runs.get("n")
    assert moved is not None
    assert moved.project_id == "p1"  # 프로젝트 없던 Run은 대상 프로젝트로 표시된다


def test_twice_does_not_duplicate_and_keep_source(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(SqliteStorage(app_db.engine), None)
    mover = mover_of(app_db, spaces)
    request = RecordsMoveRequest(project_id="p1", select="ids", ids=["a", "b"], remove_source=False)
    first = mover.move(request)
    again = mover.move(request)
    assert (first.moved, first.skipped) == (3, 0)
    assert (again.moved, again.skipped) == (0, 2)
    target = target_engine(spaces, "p1")
    assert (count(target, "runs"), count(target, "run_events")) == (3, 6)
    assert count(app_db.engine, "runs") == 4  # remove_source=false -> 원본 남음
    # 지우는 요청으로 다시 하면 이미 있어 건너뛰고 원본은 그대로다(옮긴 것이 아니다)
    last = mover.move(request.model_copy(update={"remove_source": True}))
    assert (last.moved, last.skipped) == (0, 2)
    assert count(target, "runs") == 3


def test_failure_in_the_middle_leaves_source_and_rolls_back_target(
    app_db: SqliteDatabase, spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(SqliteStorage(app_db.engine), "p1")
    source_before = {t: count(app_db.engine, t) for t in RUN_TABLES}

    def boom(self: RecordsMove) -> int:
        raise RuntimeError("disk full")

    monkeypatch.setattr(RecordsMove, "delete_source", boom)
    result = mover_of(app_db, spaces).move(
        RecordsMoveRequest(project_id="p1", select="ids", ids=["a", "b"])
    )
    assert result.moved == 0
    assert {i.code for i in result.failed} == {"run.move_failed"}
    target = target_engine(spaces, "p1")
    assert {t: count(target, t) for t in RUN_TABLES} == dict.fromkeys(RUN_TABLES, 0)
    assert {t: count(app_db.engine, t) for t in RUN_TABLES} == source_before


def test_verify_failure_keeps_source(
    app_db: SqliteDatabase, spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_console_store import MoveVerifyError

    seed(SqliteStorage(app_db.engine), "p1")

    def bad(self: RecordsMove) -> None:
        raise MoveVerifyError("runs", 2, 1)

    monkeypatch.setattr(RecordsMove, "verify", bad)
    result = mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert result.moved == 0
    assert count(app_db.engine, "runs") == 4
    assert count(target_engine(spaces, "p1"), "runs") == 0


def test_not_found_ids_and_unavailable_records(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(SqliteStorage(app_db.engine), "p1")
    mover = mover_of(app_db, spaces)
    result = mover.move(RecordsMoveRequest(project_id="p1", select="ids", ids=["a", "zzz"]))
    assert (result.moved, [i.details["id"] for i in result.failed]) == (2, ["zzz"])
    spaces.open("project:p1").readonly = True
    with pytest.raises(RecordsUnavailable) as caught:
        mover.move(RecordsMoveRequest(project_id="p1", select="ids", ids=["b"]))
    assert caught.value.project_id == "p1"
    assert count(app_db.engine, "runs") == 2  # b, d 그대로


def test_old_app_db_without_lineage_columns_moves_to_lineage_target(
    tmp_path: Path, spaces: Spaces
) -> None:
    """계보를 올리지 않은 옛 DB(`root_run_id` 열 없음)도 옮기고, 대상에서는 새 열이 채워진다."""
    engine = create_sqlite_engine(tmp_path / "old.sqlite3")
    upgrade(engine)  # legacy 0003까지만
    storage = SqliteStorage(engine)
    storage.runs.save(run("a", 1.0, project_id="p1"))
    storage.runs.save(run("c", 2.0, project_id="p1", parent_run_id="a", root_run_id="a"))
    storage.events.append(event("c", 1))
    mover = RunMover(lambda: engine, space_records(lambda: spaces, prefix="project:"))
    result = mover.move(RecordsMoveRequest(project_id="p1", select="project"))
    assert (result.moved, result.failed) == (2, [])
    target = target_engine(spaces, "p1")
    with target.connect() as c:
        row = c.exec_driver_sql("select root_run_id from runs where id='c'").scalar()
    assert row == "a"
    assert count(target, "run_events") == 1
    assert count(engine, "runs") == 0
    engine.dispose()


def test_ten_thousand_events_time(app_db: SqliteDatabase, spaces: Spaces) -> None:
    storage = SqliteStorage(app_db.engine)
    storage.runs.save(run("big", 1.0, project_id="p1"))
    for start in range(0, 10_000, 500):
        storage.events.append_many([event("big", s) for s in range(start + 1, start + 501)])
    before = table_digest(app_db.engine, ("big",))
    started = time.perf_counter()
    result = mover_of(app_db, spaces).move(
        RecordsMoveRequest(project_id="p1", select="ids", ids=["big"])
    )
    elapsed = time.perf_counter() - started
    print(f"runs move 1 run + 10000 events: {elapsed:.2f}s")
    assert result.moved == 1
    target = target_engine(spaces, "p1")
    assert count(target, "run_events") == 10_000
    assert table_digest(target, ("big",)) == before
    assert count(app_db.engine, "run_events") == 0


# ---- REST ------------------------------------------------------------------------


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    return registries


def _provider(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


@contextmanager
def _client(tmp_path: Path, db: SqliteDatabase, spaces: Spaces | None) -> Iterator[TestClient]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=db,
        registries=_registries(),
    )
    modules = [module, local_definitions_module()]
    if spaces is not None:
        modules.append(_provider("t-records", RECORDS_SPACES, spaces))
    assembly = assemble(modules, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def test_rest_move_to_project_then_list_from_project_db(
    tmp_path: Path, app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(SqliteStorage(app_db.engine), "p1")
    with _client(tmp_path, app_db, spaces) as client:
        body = {"project_id": "p1", "select": "project"}
        assert [r["id"] for r in client.get(f"{API}/runs?project=p1&source=app").json()] == [
            "d",
            "b",
            "c",
            "a",
        ]
        moved = client.post(f"{API}/runs/move-to-project", json=body)
        assert moved.status_code == 200, moved.text
        # 서버 시작 때 끝나지 않은 d는 끊김(interrupted)으로 정리되므로 함께 옮겨진다
        assert moved.json()["moved"] == 4
        assert moved.json()["failed"] == []
        assert client.get(f"{API}/runs?project=p1&source=app").json() == []
        in_project = client.get(f"{API}/runs?project=p1").json()
        assert sorted(r["id"] for r in in_project) == ["a", "b", "c", "d"]
        again = client.post(f"{API}/runs/move-to-project", json=body)
        assert again.json()["moved"] == 0
        # 잘못된 요청: ids 없는 select=ids
        bad = client.post(f"{API}/runs/move-to-project", json={"project_id": "p1", "select": "ids"})
        assert bad.status_code == 422
        unknown = client.post(
            f"{API}/runs/move-to-project", json={"project_id": "nope", "select": "project"}
        )
        assert unknown.status_code == 404
        spaces.open("project:p1").readonly = True
        locked = client.post(f"{API}/runs/move-to-project", json=body)
        assert locked.status_code == 409
        assert locked.json()["error"]["code"] == "project.records_unavailable"


def test_rest_route_absent_without_database(tmp_path: Path, spaces: Spaces) -> None:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    assembly = assemble([module, local_definitions_module()], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        body = {"project_id": "p1", "select": "project"}
        assert client.post(f"{API}/runs/move-to-project", json=body).status_code in (404, 405)
