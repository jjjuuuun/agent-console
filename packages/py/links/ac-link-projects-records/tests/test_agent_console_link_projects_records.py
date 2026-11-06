"""link-projects-records: 기록 공간 열기·계보 선언만으로 올라감·폴더 없음·상한·대기 파일 다시 쓰기·
host_id·단독 기동(5.7R.33w2, design §PI.4.6)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import RunEvent
from agent_console_link_projects_records import (
    MODULE_ID,
    PROJECTS_SPACES,
    RECORDS_SPACES,
    PoolOptions,
    RecordsSpacePool,
    RecordsSpool,
    UnknownSpace,
    load_host_id,
    module,
)
from agent_console_link_projects_records.testing import FolderSpaces, folder_spaces_module
from agent_console_mod_chat.storage import BRANCH as CHAT_BRANCH
from agent_console_mod_runs.storage import BRANCH as RUNS_BRANCH
from agent_console_modkit import (
    BaseServices,
    MigrationBranch,
    ModulesConfig,
    ModuleState,
    Paths,
    assemble,
)
from agent_console_modkit.testing import fake_module
from agent_console_store import RecordsUnavailable, SqliteDatabase

STEPS = '''"""p"""
from alembic import op

revision = "probe_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE {table} (id TEXT PRIMARY KEY)")


def downgrade() -> None:
    op.execute("DROP TABLE {table}")
'''


def _probe_branch(root: Path, *scopes: str, name: str = "probe") -> MigrationBranch:
    folder = root / f"versions_{name}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "probe_0001.py").write_text(
        STEPS.replace("{table}", f"{name}_items"), encoding="utf-8"
    )
    return MigrationBranch(name, folder, scopes=scopes)


def _paths(tmp_path: Path) -> Paths:
    return Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "ws" / ".state")


def _folder(tmp_path: Path, name: str = "proj") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    return folder


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


@dataclass
class StubSpace:
    """읽기 전용 구성 폴더를 흉내 내는 공간."""

    folder: Path
    config_writable: bool = False

    @property
    def records_db_path(self) -> Path:
        return self.folder / ".agent-console" / "records.sqlite3"

    @property
    def state_dir(self) -> Path:
        return self.folder / ".agent-console" / ".state"


class StubSpaces:
    def __init__(self, space: StubSpace) -> None:
        self.space = space

    def open(self, project_id: str) -> StubSpace:
        return self.space


def _pool(
    tmp_path: Path,
    spaces: Any,
    branches: list[MigrationBranch] | None = None,
    *,
    options: PoolOptions | None = None,
    clock: Any = None,
) -> RecordsSpacePool:
    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    return RecordsSpacePool(
        lambda: spaces,
        lambda: branches or [],
        host_id="host-aaaa1111",
        spool=RecordsSpool(tmp_path / "ws" / ".state" / "records-spool"),
        options=options or PoolOptions(),
        network_fs=lambda _p: False,
        **kwargs,
    )


# ---- 조립: 계보는 선언만으로 -------------------------------------------------


@contextmanager
def _assembled(tmp_path: Path, folders: dict[str, Path], *modules: Any) -> Iterator[Any]:
    base = BaseServices(paths=_paths(tmp_path))
    assembly = assemble([folder_spaces_module(folders), module, *modules], None, base=base)
    try:
        yield assembly
    finally:
        pool = assembly.port(RECORDS_SPACES)
        if isinstance(pool, RecordsSpacePool):
            pool.close_all()


def test_project_scope_branch_is_applied_from_declaration_only(tmp_path: Path) -> None:
    """테스트 전용 모듈의 `project` 계보가 코드 수정 없이 기록 DB에 올라간다(R0)."""
    proj = _probe_branch(tmp_path, "project")
    app_only = _probe_branch(tmp_path, "app", name="appside")
    both = _probe_branch(tmp_path, "app", "project", name="both")
    mods = [
        fake_module("mod-proj", migrations=[proj]),
        fake_module("mod-app", migrations=[app_only]),
        fake_module("mod-both", migrations=[both]),
    ]
    folder = _folder(tmp_path)
    with _assembled(tmp_path, {"a": folder}, *mods) as assembly:
        status = assembly.status(MODULE_ID)
        assert status is not None
        assert status.state is ModuleState.ACTIVE
        pool = assembly.port(RECORDS_SPACES)
        handle = pool.open("project:a")
        engine = handle.writable_engine()
        names = _tables(engine)
        assert "probe_items" in names
        assert "appside_items" not in names  # app 범위만 선언한 계보는 기록 DB에 없다
        assert "both_items" in names
        versions = {t for t in names if t.startswith("alembic_version")}
        assert versions == {"alembic_version", "alembic_version_probe", "alembic_version_both"}
        assert (folder / ".agent-console" / "records.sqlite3").exists()
        assert handle.host_id == (tmp_path / "ws" / ".state" / "host_id").read_text().strip()


def test_link_is_off_without_projects_spaces(tmp_path: Path) -> None:
    base = BaseServices(paths=_paths(tmp_path))
    assembly = assemble([module], None, base=base)
    status = assembly.status(MODULE_ID)
    assert status is not None
    assert status.state is ModuleState.UNSATISFIED
    assert assembly.port(RECORDS_SPACES) is None


def test_link_can_be_disabled_and_nothing_provides_records(tmp_path: Path) -> None:
    base = BaseServices(paths=_paths(tmp_path))
    assembly = assemble(
        [folder_spaces_module({}), module], ModulesConfig(disabled=[MODULE_ID]), base=base
    )
    assert assembly.port(RECORDS_SPACES) is None


def test_runs_and_chat_tables_match_app_database(tmp_path: Path) -> None:
    """빈 기록 DB(legacy + project 계보)의 표·열·색인이 앱 DB의 같은 표와 같다."""
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH, CHAT_BRANCH])
    records = pool.open("project:a").writable_engine()
    app = SqliteDatabase.open(tmp_path / "app.sqlite3")
    app.upgrade([RUNS_BRANCH, CHAT_BRANCH])

    def shape(engine: sa.Engine) -> dict[str, Any]:
        insp = sa.inspect(engine)
        out: dict[str, Any] = {}
        for name in sorted(insp.get_table_names()):
            cols = [(c["name"], str(c["type"]), c["nullable"]) for c in insp.get_columns(name)]
            idx = sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                for i in insp.get_indexes(name)
            )
            out[name] = (cols, idx, insp.get_pk_constraint(name)["constrained_columns"])
        return out

    assert shape(records) == shape(app.engine)
    cols = {c["name"] for c in sa.inspect(records).get_columns("chat_queue")}
    assert "host_id" in cols
    pool.close_all()
    app.close()


# ---- 상태·폴더 ---------------------------------------------------------------


def test_view_does_not_create_files_and_state_is_absent(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    assert pool.state("project:a").state == "absent"
    handle = pool.open("project:a")
    assert handle.state.state == "absent"
    assert handle.read_engine() is None
    assert list(folder.iterdir()) == []  # 구성 폴더도 만들지 않았다
    handle.writable_engine()
    assert handle.state.state == "ready"
    assert pool.state("project:a").state == "ready"
    pool.close_all()


def test_state_peek_does_not_open_or_migrate(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    pool.open("project:a").writable_engine()
    pool.close_all()
    again = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    assert again.state("project:a").state == "ready"
    assert again.open_spaces() == []  # 상태만 봤다


def test_missing_folder_is_unavailable_and_never_recreated(tmp_path: Path) -> None:
    pool = _pool(tmp_path, FolderSpaces({"gone": tmp_path / "nope"}), [RUNS_BRANCH])
    st = pool.state("project:gone")
    assert (st.state, st.reason, st.writable) == ("unavailable", "folder_missing", False)
    handle = pool.open("project:gone")
    assert handle.state.reason == "folder_missing"
    with pytest.raises(RecordsUnavailable) as err:
        handle.writable_engine()
    assert err.value.reason == "folder_missing"
    assert not (tmp_path / "nope").exists()


def test_folder_vanishing_while_open_is_folder_missing_not_recreated(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    handle = pool.open("project:a")
    handle.writable_engine()
    shutil.rmtree(folder)
    assert handle.state.reason == "folder_missing"
    with pytest.raises(RecordsUnavailable) as err:
        handle.writable_engine()
    assert err.value.reason == "folder_missing"
    with pytest.raises(RecordsUnavailable):
        handle.read_engine()
    assert not folder.exists()
    pool.close_all()


def test_read_only_config_blocks_writes_without_touching_app_state(tmp_path: Path) -> None:
    space = StubSpace(_folder(tmp_path), config_writable=False)
    pool = _pool(tmp_path, StubSpaces(space), [RUNS_BRANCH])
    handle = pool.open("project:a")
    assert (handle.state.state, handle.state.reason, handle.state.writable) == (
        "absent",
        "readonly",
        False,
    )
    with pytest.raises(RecordsUnavailable) as err:
        handle.writable_engine()
    assert err.value.reason == "readonly"
    assert not space.records_db_path.exists()


def test_newer_database_is_readable_but_write_is_refused(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    engine = pool.open("project:a").writable_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE alembic_version_runs SET version_num = 'runs_9999'")
    pool.close_all()
    again = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    handle = again.open("project:a")
    assert handle.state.state == "newer"
    reader = handle.read_engine()
    assert reader is not None
    with reader.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM runs").scalar() == 0
    with pytest.raises(RecordsUnavailable) as err:
        handle.writable_engine()
    assert err.value.reason == "newer"
    again.close_all()


def test_unknown_space_and_project(tmp_path: Path) -> None:
    pool = _pool(tmp_path, FolderSpaces({}))
    with pytest.raises(UnknownSpace):
        pool.open("other:a")
    with pytest.raises(UnknownSpace):
        pool.open("project:")
    with pytest.raises(UnknownSpace):
        pool.open("project:nobody")
    with pytest.raises(UnknownSpace):
        pool.state("project:nobody")


def test_no_projects_spaces_port_means_link_disabled_state(tmp_path: Path) -> None:
    pool = RecordsSpacePool(
        lambda: None,
        lambda: [],
        host_id="host-aaaa1111",
        spool=RecordsSpool(tmp_path / "spool"),
    )
    assert pool.state("project:a").reason == "link_disabled"
    with pytest.raises(RecordsUnavailable) as err:
        pool.open("project:a").writable_engine()
    assert err.value.reason == "link_disabled"


# ---- 캐시 --------------------------------------------------------------------


def test_cache_cap_evicts_least_recent_and_evicted_handle_still_works(tmp_path: Path) -> None:
    folders = {n: _folder(tmp_path, n) for n in "abc"}
    pool = _pool(tmp_path, FolderSpaces(folders), [RUNS_BRANCH], options=PoolOptions(max_open=2))
    first = pool.open("project:a")
    first.writable_engine()
    pool.open("project:b")
    pool.open("project:c")
    assert pool.open_spaces() == ["project:b", "project:c"]
    engine = first.writable_engine()  # 밀려난 핸들은 다시 쓰면 살아난다
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM runs").scalar() == 0
    pool.close_all()


def test_idle_spaces_are_suspended_and_revive_on_use(tmp_path: Path) -> None:
    now = [0.0]
    folder = _folder(tmp_path)
    pool = _pool(
        tmp_path,
        FolderSpaces({"a": folder, "b": _folder(tmp_path, "b")}),
        [RUNS_BRANCH],
        options=PoolOptions(idle_close_seconds=10),
        clock=lambda: now[0],
    )
    handle = pool.open("project:a")
    engine = handle.writable_engine()
    now[0] = 50.0
    pool.open("project:b")  # 이때 유휴를 정리한다
    again = handle.writable_engine()
    assert again is not engine
    with again.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM runs").scalar() == 0
    pool.close_all()


def test_repointed_folder_replaces_cached_handle(tmp_path: Path) -> None:
    old, new = _folder(tmp_path, "old"), _folder(tmp_path, "new")
    spaces = FolderSpaces({"a": old})
    pool = _pool(tmp_path, spaces, [RUNS_BRANCH])
    pool.open("project:a").writable_engine()
    spaces.folders["a"] = new
    handle = pool.open("project:a")
    assert handle.state.state == "absent"  # 새 경로에는 아직 기록이 없다
    pool.close_all()


def test_two_spaces_use_different_files(tmp_path: Path) -> None:
    a, b = _folder(tmp_path, "a"), _folder(tmp_path, "b")
    pool = _pool(tmp_path, FolderSpaces({"a": a, "b": b}), [RUNS_BRANCH])
    ea = pool.open("project:a").writable_engine()
    eb = pool.open("project:b").writable_engine()
    with ea.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO run_events (run_id, seq, event_id, ts, type, body) "
            "VALUES ('r', 1, 'e', 0, 't', '{}')"
        )
    with eb.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM run_events").scalar() == 0
    pool.close_all()


# ---- host_id -----------------------------------------------------------------


def test_host_id_is_created_once_and_reused(tmp_path: Path) -> None:
    path = tmp_path / ".state" / "host_id"
    first = load_host_id(path)
    assert load_host_id(path) == first
    assert len(first) >= 8


def test_host_id_concurrent_creation_agrees(tmp_path: Path) -> None:
    path = tmp_path / "s" / "host_id"
    out: list[str] = []
    barrier = threading.Barrier(6)

    def run() -> None:
        barrier.wait()
        out.append(load_host_id(path))

    threads = [threading.Thread(target=run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert len(out) == 6
    assert len(set(out)) == 1


def test_host_id_garbage_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "host_id"
    path.write_text("not valid!!\n", encoding="utf-8")
    fresh = load_host_id(path)
    assert fresh != "not valid!!"
    assert load_host_id(path) == fresh


# ---- 대기 파일 ---------------------------------------------------------------


def _event(run_id: str, seq: int) -> dict[str, Any]:
    return RunEvent.model_validate(
        {
            "event_id": f"{run_id}-e{seq}",
            "run_id": run_id,
            "seq": seq,
            "ts": 1.0,
            "node_path": [],
            "type": "agent.text_delta",
            "payload": {"text": "x"},
        }
    ).model_dump(mode="json")


def test_spool_replays_into_records_db_without_duplicates(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    spool = pool.spool
    for seq in (1, 2, 2, 3):  # 같은 seq(같은 event_id)를 두 번 적었다
        spool.append("a", "r1", "event", _event("r1", seq))
    spool.append("a", "r2", "event", _event("r2", 1))
    assert spool.pending("a") == ["r1", "r2"]

    handle = pool.open("project:a")  # 열 때 다시 쓴다
    assert spool.pending("a") == []
    engine = handle.writable_engine()
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT run_id, seq FROM run_events ORDER BY run_id, seq")
        assert rows.fetchall() == [("r1", 1), ("r1", 2), ("r1", 3), ("r2", 1)]
    pool.close_all()
    # 다시 열어도 변화 없음(대기 파일이 없다)
    again = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    with again.open("project:a").writable_engine().connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM run_events").scalar() == 4
    again.close_all()


def test_spool_is_replayed_only_when_the_space_becomes_writable(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    ro = StubSpace(folder, config_writable=False)
    pool = _pool(tmp_path, StubSpaces(ro), [RUNS_BRANCH])
    pool.spool.append("a", "r1", "event", _event("r1", 1))
    pool.open("project:a")
    assert pool.spool.pending("a") == ["r1"]  # 못 썼으니 그대로
    assert not ro.records_db_path.exists()


def test_handle_spool_writes_into_app_spool_not_the_folder(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pool = _pool(tmp_path, FolderSpaces({"a": folder}), [RUNS_BRANCH])
    handle = pool.open("project:a")
    handle.spool("r9", "event", _event("r9", 1))
    assert pool.spool.pending("a") == ["r9"]
    assert list(folder.iterdir()) == []
    pool.close_all()


def test_spool_partial_failure_keeps_the_rest_in_order(tmp_path: Path) -> None:
    spool = RecordsSpool(tmp_path / "s")
    for n in range(4):
        spool.append("p", "r", "k", {"n": n})
    seen: list[int] = []

    def apply(kind: str, data: Any) -> bool:
        if data["n"] == 2:
            raise OSError("disk")
        seen.append(data["n"])
        return True

    result = spool.drain("p", apply)
    assert (result.written, result.remaining) == (2, 2)
    assert isinstance(result.errors[0], OSError)
    assert spool.pending("p") == ["r"]
    seen.clear()

    def collect(kind: str, data: Any) -> bool:
        seen.append(data["n"])
        return True

    done = spool.drain("p", collect)
    assert seen == [2, 3]
    assert done.remaining == 0
    assert spool.pending("p") == []


def test_spool_drops_unreadable_lines_and_quotes_ids(tmp_path: Path) -> None:
    spool = RecordsSpool(tmp_path / "s")
    path = spool.append("a/b", "../evil", "k", {"n": 1})
    assert path.resolve().is_relative_to((tmp_path / "s").resolve())
    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write('{"kind": 1}\n')
    result = spool.drain("a/b", lambda kind, data: True)
    assert (result.written, result.invalid, result.remaining) == (1, 2, 0)
    assert spool.pending("a/b") == []


# ---- 단독 기동 ---------------------------------------------------------------


def test_module_check_runs_without_with() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_projects_records", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert MODULE_ID in done.stdout


def test_ports_are_declared_on_the_descriptor() -> None:
    d = module.descriptor
    assert [p.name for p in d.provides] == ["records.spaces"]
    assert [p.name for p in d.requires] == [PROJECTS_SPACES.name]
