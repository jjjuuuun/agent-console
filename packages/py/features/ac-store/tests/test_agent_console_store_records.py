"""프로젝트 기록 DB 열기(5.7R.33w2, design §PI.4.6.2): 없음·같음·뒤처짐·앞섬·깨짐·읽기 전용·잠금."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa

from agent_console_store import (
    RecordsAbsent,
    RecordsUnavailable,
    branch_version_table,
    inspect_records,
    is_network_fs,
    open_records_db,
    upgrade,
)

_TEMPLATE = '''"""test"""
from alembic import op

revision = "{rev}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""{up}""")


def downgrade() -> None:
    op.execute("""{down_sql}""")
'''


@dataclass(frozen=True)
class Branch:
    name: str
    versions: Path


def make_branch(root: Path, name: str, steps: list[tuple[str, str, str]]) -> Branch:
    """`steps` = (리비전, 올리기 SQL, 내리기 SQL). 앞 리비전 뒤에 이어 붙는다."""
    folder = root / f"versions_{name}"
    folder.mkdir(parents=True, exist_ok=True)
    prev = "None"
    for rev, up, down in steps:
        (folder / f"{rev}.py").write_text(
            _TEMPLATE.format(rev=rev, down=prev, up=up, down_sql=down), encoding="utf-8"
        )
        prev = f'"{rev}"'
    return Branch(name, folder)


STEPS = [
    ("probe_0001", "CREATE TABLE probe_items (id TEXT PRIMARY KEY)", "DROP TABLE probe_items"),
    (
        "probe_0002",
        "ALTER TABLE probe_items ADD COLUMN note TEXT",
        "ALTER TABLE probe_items DROP COLUMN note",
    ),
]


@pytest.fixture
def branch(tmp_path: Path) -> Branch:
    return make_branch(tmp_path, "probe", STEPS)


def _db(tmp_path: Path, *branches: Branch, **kw: object):  # type: ignore[no-untyped-def]
    return open_records_db(
        tmp_path / "proj" / "records.sqlite3",
        branches,
        backup_dir=tmp_path / "proj" / "backups",
        **kw,  # type: ignore[arg-type]
    )


def _rev(path: Path, table: str) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(f"SELECT version_num FROM {table}").fetchone()
        return None if row is None else str(row[0])
    finally:
        conn.close()


def _make_old(tmp_path: Path, branch: Branch, *, rows: int = 2) -> Path:
    """legacy는 head, probe는 probe_0001인 옛 기록 DB(행 포함)."""
    path = tmp_path / "proj" / "records.sqlite3"
    path.parent.mkdir(parents=True)
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    upgrade(engine)
    upgrade(engine, "probe_0001", versions=branch.versions, version_table="alembic_version_probe")
    with engine.begin() as conn:
        for i in range(rows):
            conn.exec_driver_sql("INSERT INTO probe_items (id) VALUES (?)", (f"x{i}",))
    engine.dispose()
    return path


def test_absent_does_not_create_file_until_first_write(tmp_path: Path, branch: Branch) -> None:
    db = _db(tmp_path, branch)
    assert db.state.state == "absent"
    assert db.state.writable
    assert not db.path.exists()
    assert not db.path.parent.exists()
    assert db.read_engine() is None
    with pytest.raises(RecordsAbsent):
        _ = db.engine

    engine = db.writable_engine()
    assert db.path.exists()
    assert db.state.state == "ready"
    assert db.revision() == "0003"
    assert db.revision("probe") == "probe_0002"
    with engine.connect() as conn:
        cols = [c["name"] for c in sa.inspect(conn).get_columns("probe_items")]
    assert cols == ["id", "note"]
    assert db.read_engine() is engine
    db.close()


def test_same_revision_opens_ready_without_backup(tmp_path: Path, branch: Branch) -> None:
    first = _db(tmp_path, branch)
    first.writable_engine()
    first.close()
    again = _db(tmp_path, branch)
    assert again.state.state == "ready"
    assert again.state.reason is None
    assert again.state.backup_path is None
    assert not (tmp_path / "proj" / "backups").exists()
    again.close()


def test_behind_is_backed_up_then_upgraded(tmp_path: Path, branch: Branch) -> None:
    path = _make_old(tmp_path, branch)
    db = _db(tmp_path, branch)
    assert db.state.state == "ready"
    backup = db.state.backup_path
    assert backup is not None
    assert backup.parent == tmp_path / "proj" / "backups"
    assert backup.name.startswith("records-")
    assert "probe@probe_0001" in backup.name
    # 백업은 올리기 전 모양 그대로(행 유지, 리비전 옛 것)
    assert _rev(backup, "alembic_version_probe") == "probe_0001"
    old = sqlite3.connect(backup)
    assert old.execute("SELECT count(*) FROM probe_items").fetchone()[0] == 2
    old.close()
    assert _rev(path, "alembic_version_probe") == "probe_0002"
    assert db.revision("probe") == "probe_0002"
    db.close()


def test_backups_are_pruned_to_keep_count(tmp_path: Path) -> None:
    ticks = iter(range(1_700_000_000, 1_700_000_100, 7))
    steps = [("p_0001", "CREATE TABLE p1 (id TEXT)", "DROP TABLE p1")]
    folder = make_branch(tmp_path, "p", steps)
    # 계보를 한 칸씩 늘려 가며 열 때마다 뒤처진 상태를 만든다
    path = tmp_path / "proj" / "records.sqlite3"
    backups = tmp_path / "proj" / "backups"
    first = open_records_db(path, [folder], backup_dir=backups, clock=lambda: next(ticks))
    first.writable_engine()
    first.close()
    for n in range(2, 6):
        steps.append((f"p_000{n}", f"CREATE TABLE p{n} (id TEXT)", f"DROP TABLE p{n}"))
        folder = make_branch(tmp_path, "p", steps)
        db = open_records_db(
            path, [folder], backup_dir=backups, keep_backups=2, clock=lambda: next(ticks)
        )
        assert db.state.state == "ready"
        db.close()
    assert len(list(backups.glob("records-*.sqlite3"))) == 2


def test_newer_is_read_only_and_never_touched(tmp_path: Path, branch: Branch) -> None:
    seed = _db(tmp_path, branch)
    seed.writable_engine()
    seed.close()
    path = tmp_path / "proj" / "records.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("INSERT INTO probe_items (id) VALUES ('keep')")
    raw.execute("UPDATE alembic_version_probe SET version_num = 'probe_9999'")
    raw.commit()
    raw.close()
    before = path.read_bytes()

    db = _db(tmp_path, branch)
    assert db.state.state == "newer"
    assert db.state.reason == "newer"
    assert not db.state.writable
    assert db.state.backup_path is None
    engine = db.read_engine()
    assert engine is not None
    with engine.connect() as conn:  # 읽기는 된다
        assert conn.exec_driver_sql("SELECT id FROM probe_items").fetchall() == [("keep",)]
    with pytest.raises(sa.exc.OperationalError), engine.begin() as conn:  # mode=ro라 쓰기 불가
        conn.exec_driver_sql("INSERT INTO probe_items (id) VALUES ('no')")
    with pytest.raises(RecordsUnavailable) as err:
        db.writable_engine()
    assert err.value.reason == "newer"
    assert err.value.code == "project.records_unavailable"
    db.close()
    assert _rev(path, "alembic_version_probe") == "probe_9999"
    assert path.read_bytes() == before
    assert not (tmp_path / "proj" / "backups").exists()


def test_corrupt_file_is_unavailable_and_left_alone(tmp_path: Path, branch: Branch) -> None:
    path = tmp_path / "proj" / "records.sqlite3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"this is not a sqlite database" * 20)
    db = _db(tmp_path, branch)
    assert db.state.state == "unavailable"
    assert db.state.reason == "corrupt"
    assert not db.state.writable
    with pytest.raises(RecordsUnavailable) as err:
        db.read_engine()
    assert err.value.reason == "corrupt"
    with pytest.raises(RecordsUnavailable):
        db.writable_engine()
    assert path.read_bytes().startswith(b"this is not")
    db.close()


def test_read_only_folder_absent_and_existing(tmp_path: Path, branch: Branch) -> None:
    absent = _db(tmp_path, branch, can_write=lambda _p: False)
    assert absent.state.state == "absent"
    assert not absent.state.writable
    assert absent.state.reason == "readonly"
    with pytest.raises(RecordsUnavailable) as err:
        absent.writable_engine()
    assert err.value.reason == "readonly"
    assert not absent.path.exists()

    seed = _db(tmp_path, branch)
    seed.writable_engine()
    seed.close()
    ro = _db(tmp_path, branch, can_write=lambda _p: False)
    assert ro.state.state == "ready"
    assert not ro.state.writable
    assert ro.state.reason == "readonly"
    engine = ro.read_engine()
    assert engine is not None
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM probe_items").scalar() == 0
    with pytest.raises(RecordsUnavailable):
        ro.writable_engine()
    ro.close()


def test_read_only_folder_with_behind_db_is_not_upgraded(tmp_path: Path, branch: Branch) -> None:
    path = _make_old(tmp_path, branch)
    before = path.read_bytes()
    db = _db(tmp_path, branch, can_write=lambda _p: False)
    assert db.state.state == "unavailable"
    assert db.state.reason == "readonly"
    db.close()
    assert path.read_bytes() == before
    assert not (tmp_path / "proj" / "backups").exists()


def test_network_fs_uses_delete_journal(tmp_path: Path, branch: Branch) -> None:
    db = _db(tmp_path, branch, network_fs=lambda _p: True)
    assert db.state.network_fs
    assert db.state.journal_mode == "DELETE"
    engine = db.writable_engine()
    with engine.connect() as conn:
        assert str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "delete"
    db.close()
    local = tmp_path / "local"
    other = open_records_db(
        local / "r.sqlite3", [branch], backup_dir=local / "b", network_fs=lambda _p: False
    )
    assert other.state.journal_mode == "WAL"
    with other.writable_engine().connect() as conn:
        assert str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
    other.close()


def test_is_network_fs_reads_mountinfo_and_unc() -> None:
    info = (
        "20 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
        "30 20 0:40 / /mnt/share rw - nfs4 server:/x rw\n"
        "31 20 0:41 / /mnt/with\\040space rw - cifs //s/y rw\n"
    )
    assert is_network_fs("/mnt/share/proj/records.sqlite3", mountinfo=info)
    assert is_network_fs("/mnt/with space/p", mountinfo=info)
    assert not is_network_fs("/home/u/proj", mountinfo=info)
    assert not is_network_fs("/mnt/sharex/p", mountinfo=info)
    assert is_network_fs("\\\\server\\share\\proj")


def test_invalid_journal_and_branch_name(tmp_path: Path, branch: Branch) -> None:
    with pytest.raises(ValueError, match="journal"):
        _db(tmp_path, branch, journal="MEMORY")
    with pytest.raises(ValueError, match="브랜치"):
        _db(tmp_path, Branch("legacy", branch.versions))
    with pytest.raises(ValueError, match="브랜치"):
        _db(tmp_path, Branch("a-b", branch.versions))


def test_two_connections_upgrade_the_same_file_once(tmp_path: Path, branch: Branch) -> None:
    path = _make_old(tmp_path, branch)
    # probe_0002에 한 번만 들어가야 하는 행을 넣는 계보로 바꾼다
    folder = make_branch(
        tmp_path,
        "probe",
        [
            *STEPS,
            (
                "probe_0003",
                "CREATE TABLE probe_log (n INTEGER); INSERT INTO probe_log VALUES (1)".replace(
                    "; ", '""")\n    op.execute("""'
                ),
                "DROP TABLE probe_log",
            ),
        ],
    )
    barrier = threading.Barrier(2)
    results: list[object] = []

    def run() -> None:
        barrier.wait()
        db = open_records_db(path, [folder], backup_dir=tmp_path / "proj" / "backups")
        results.append(db.state)
        db.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(results) == 2
    assert all(getattr(s, "state", None) == "ready" for s in results)
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT count(*) FROM probe_log").fetchone()[0] == 1
    conn.close()
    assert _rev(path, "alembic_version_probe") == "probe_0003"
    assert len(list((tmp_path / "proj" / "backups").glob("records-*.sqlite3"))) == 1


def test_write_rechecks_revision_and_turns_newer(tmp_path: Path, branch: Branch) -> None:
    db = _db(tmp_path, branch)
    db.writable_engine()
    assert db.state.state == "ready"
    other = sqlite3.connect(db.path)  # 더 새 앱이 올렸다
    other.execute("UPDATE alembic_version_probe SET version_num = 'probe_0099'")
    other.commit()
    other.close()
    with pytest.raises(RecordsUnavailable) as err:
        db.writable_engine()
    assert err.value.reason == "newer"
    assert db.state.state == "newer"
    assert db.read_engine() is not None  # 읽기는 계속
    db.close()


def test_deleted_file_is_recreated_on_next_write(tmp_path: Path, branch: Branch) -> None:
    db = _db(tmp_path, branch)
    db.writable_engine()
    for suffix in ("", "-wal", "-shm"):
        Path(str(db.path) + suffix).unlink(missing_ok=True)
    db.writable_engine()
    assert db.path.exists()
    assert db.revision("probe") == "probe_0002"
    db.close()


def test_failed_migration_rolls_back_and_reports_backup(tmp_path: Path) -> None:
    good = make_branch(tmp_path, "bad", [STEPS[0]])
    seed = _db(tmp_path, good)
    seed.writable_engine()
    seed.close()
    broken = make_branch(
        tmp_path,
        "bad",
        [
            STEPS[0],
            ("probe_0002", "CREATE TABLE half (id TEXT)", ""),
            ("probe_0003", "THIS IS NOT SQL", ""),
        ],
    )
    db = _db(tmp_path, broken)
    assert db.state.state == "unavailable"
    assert db.state.reason == "migration_failed"
    assert db.state.backup_path is not None
    assert db.state.backup_path.exists()
    with pytest.raises(RecordsUnavailable) as err:
        db.writable_engine()
    assert err.value.backup_path == db.state.backup_path
    db.close()
    conn = sqlite3.connect(db.path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "half" not in tables  # 같은 트랜잭션이라 함께 되돌아갔다
    assert _rev(db.path, "alembic_version_bad") == "probe_0001"


def test_tables_of_unknown_branches_are_ignored(tmp_path: Path, branch: Branch) -> None:
    seed = _db(tmp_path, branch)
    seed.writable_engine()
    seed.close()
    raw = sqlite3.connect(seed.path)
    raw.execute(f"CREATE TABLE {branch_version_table('stranger')} (version_num TEXT)")
    raw.execute(f"INSERT INTO {branch_version_table('stranger')} VALUES ('x_9')")
    raw.commit()
    raw.close()
    db = _db(tmp_path, branch)
    assert db.state.state == "ready"
    db.close()


def test_inspect_records_has_no_side_effects(tmp_path: Path, branch: Branch) -> None:
    path = tmp_path / "proj" / "records.sqlite3"
    assert inspect_records(path, [branch]).state == "absent"
    assert not path.parent.exists()
    old = _make_old(tmp_path, branch)
    before = old.read_bytes()
    st = inspect_records(old, [branch])  # 뒤처짐은 ready(처음 쓸 때 올린다)
    assert st.state == "ready"
    assert old.read_bytes() == before
    assert not (tmp_path / "proj" / "backups").exists()
    raw = sqlite3.connect(old)
    raw.execute("UPDATE alembic_version_probe SET version_num = 'probe_9999'")
    raw.commit()
    raw.close()
    assert inspect_records(old, [branch]).state == "newer"
    old.write_bytes(b"garbage" * 100)
    assert inspect_records(old, [branch]).reason == "corrupt"
    ro = inspect_records(tmp_path / "none" / "r.sqlite3", [branch], can_write=lambda _p: False)
    assert (ro.state, ro.reason, ro.writable) == ("absent", "readonly", False)


def test_suspend_releases_connections_and_revives_on_next_use(
    tmp_path: Path, branch: Branch
) -> None:
    db = _db(tmp_path, branch)
    first = db.writable_engine()
    db.suspend()
    second = db.writable_engine()
    assert second is not first
    with second.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM probe_items").scalar() == 0
    db.close()
    with pytest.raises(RecordsUnavailable):
        db.writable_engine()
