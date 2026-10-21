"""저장소 v3(2R.3): 이어 가기 컬럼, 본문 스냅샷, 여러 파일 본문, 경로 검사 강화, 0003."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_contracts import Run
from agent_console_store import (
    ContentTooLarge,
    DefinitionCorrupt,
    DefinitionKind,
    DefinitionStore,
    FileDefinitionStore,
    InMemoryDefinitionStore,
    InMemoryStorage,
    InvalidContentPath,
    NotFound,
    VersionConflict,
    check_content_path,
    create_sqlite_engine,
    current_revision,
    default_hash,
    downgrade,
    open_sqlite,
    upgrade,
)
from agent_console_store.schema import include_object, metadata


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- runs.resumed_from -----------------------------------------------------
def test_runs_resumed_from_column_and_filter(storage: Any) -> None:
    base: dict[str, Any] = {
        "graph_id": "g",
        "graph_version": "h",
        "status": "completed",
        "input": {},
        "origin": "api",
    }
    storage.runs.save(Run(id="r1", created_at=1.0, **base))
    storage.runs.save(
        Run(id="r2", created_at=2.0, resumed_from="r1", **{**base, "origin": "resume"})
    )
    storage.runs.save(Run(id="r3", created_at=3.0, **base))
    assert [r.id for r in storage.runs.list(resumed_from="r1")] == ["r2"]
    assert storage.runs.get("r2").resumed_from == "r1"
    assert storage.runs.list(resumed_from="nobody") == []


# ---- 마이그레이션 0003 -----------------------------------------------------
def _cols(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _indexes(engine: sa.Engine, table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(engine).get_indexes(table) if i["name"]}


def test_0003_adds_tables_columns_and_indexes(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine, "0002")
    assert "chat_queue" not in sa.inspect(engine).get_table_names()
    upgrade(engine)
    assert current_revision(engine) == "0003"
    assert {"id", "conversation_id", "position", "text", "held", "created_at"} <= _cols(
        engine, "chat_queue"
    )
    assert "ix_chat_queue_conversation_position" in _indexes(engine, "chat_queue")
    assert {"sha256", "size", "data"} == _cols(engine, "content_blobs")
    assert "content_files" in _cols(engine, "definition_versions")
    assert "resumed_from" in _cols(engine, "runs")
    assert "ix_runs_resumed_from" in _indexes(engine, "runs")
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"include_object": include_object})
        assert compare_metadata(context, metadata) == []
    engine.dispose()


def test_0003_downgrade_and_reapply(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine, "0002")
    run_doc = json.dumps({"id": "r1", "resumed_from": "r0"})
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO runs (id, graph_id, graph_version, status, origin, created_at, doc) "
            "VALUES ('r1', 'g', 'h', 'completed', 'resume', 1.0, ?)",
            (run_doc,),
        )
        conn.exec_driver_sql(
            "INSERT INTO definition_versions (kind, def_id, version_hash, saved_at, content) "
            "VALUES ('graph', 'g', 'h', 1.0, '{}')"
        )
    upgrade(engine)
    with engine.connect() as conn:  # 적용할 때 doc에서 채운다
        assert conn.exec_driver_sql("SELECT resumed_from FROM runs").scalar() == "r0"
        assert (
            conn.exec_driver_sql("SELECT content_files FROM definition_versions").scalar() is None
        )
    downgrade(engine, "0002")
    assert current_revision(engine) == "0002"
    tables = set(sa.inspect(engine).get_table_names())
    assert not ({"chat_queue", "content_blobs"} & tables)
    assert "resumed_from" not in _cols(engine, "runs")
    assert "content_files" not in _cols(engine, "definition_versions")
    assert "ix_runs_status" in _indexes(engine, "runs")  # 이전 인덱스는 그대로
    with engine.connect() as conn:  # 0002의 데이터는 그대로
        assert conn.exec_driver_sql("SELECT count(*) FROM runs").scalar() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM definition_versions").scalar() == 1
    upgrade(engine)  # 다시 적용하면 같은 값이 복구된다
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT resumed_from FROM runs").scalar() == "r0"
        context = MigrationContext.configure(conn, opts={"include_object": include_object})
        assert compare_metadata(context, metadata) == []
    downgrade(engine)  # 끝까지 내려가도 된다
    assert current_revision(engine) is None
    engine.dispose()


# ---- 경로 검사 강화 --------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        "a:b.md",
        "C:x",
        "a/b:stream",
        "con",
        "CON.txt",
        "dir/Nul.md",
        "aux",
        "com1.txt",
        "LPT9",
        "lpt¹.txt",
        "name.",
        "name ",
        "dir./x.md",
        "dir /x.md",
        "a<b",
        "a?b",
        "a*b",
        'a"b',
        "a|b",
    ],
)
def test_windows_unsafe_paths_are_rejected(bad: str) -> None:
    with pytest.raises(InvalidContentPath):
        check_content_path(bad)


@pytest.mark.parametrize(
    "good",
    [
        "a.md",
        "skills/x/SKILL.md",
        "console.md",
        "컨벤션.md",
        "a b/c.md",
        ".hidden",
        "com10.txt",
        "conx",
    ],
)
def test_ordinary_paths_pass(good: str) -> None:
    assert check_content_path(good) == good


# ---- 여러 파일 본문 --------------------------------------------------------
def skill(id: str = "sk", **extra: Any) -> dict[str, Any]:
    return {
        "kind": "resource",
        "id": id,
        "type": "skill",
        "name": "스킬",
        "config": {},
        "content": {"file": "SKILL.md", "media_type": "text/markdown"},
        **extra,
    }


def test_files_roundtrip_listing_and_events(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", skill())
    assert definitions.list_files("resource", "sk") == []
    v1 = definitions.write_file(
        "resource", "sk", "SKILL.md", b"# main", expected_version=created.version_hash
    )
    v2 = definitions.write_file(
        "resource", "sk", "scripts/run.py", b"print(1)", expected_version=v1.version_hash
    )
    listing = definitions.list_files("resource", "sk")
    assert [f.path for f in listing] == ["SKILL.md", "scripts/run.py"]
    assert listing[0].sha256 == sha(b"# main")
    assert listing[0].size == 6
    assert listing[0].media_type == "text/markdown"
    assert definitions.read_file("resource", "sk", "scripts/run.py") == b"print(1)"
    assert definitions.read_content("resource", "sk") == b"# main"
    v3 = definitions.delete_file(
        "resource", "sk", "scripts/run.py", expected_version=v2.version_hash
    )
    assert [f.path for f in definitions.list_files("resource", "sk")] == ["SKILL.md"]
    assert v3.version_hash == v1.version_hash  # 같은 파일 집합이면 같은 해시
    assert len({created.version_hash, v1.version_hash, v2.version_hash}) == 3
    with pytest.raises(NotFound):
        definitions.read_file("resource", "sk", "scripts/run.py")
    with pytest.raises(NotFound):
        definitions.delete_file(
            "resource", "sk", "scripts/run.py", expected_version=v3.version_hash
        )
    with pytest.raises(NotFound):
        definitions.list_files("resource", "ghost")


def test_single_file_hash_is_unchanged_from_before_v3(definitions: DefinitionStore) -> None:
    """파일이 content.file 하나뿐이면 0003 이전과 같은 해시(`$content_sha256`)다."""
    created = definitions.create("resource", skill())
    v1 = definitions.write_content("resource", "sk", b"x", expected_version=created.version_hash)
    assert v1.version_hash == default_hash({**v1.document, "$content_sha256": sha(b"x")})


def test_hash_covers_every_file_and_is_order_independent(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", skill())
    a = definitions.write_files(
        "resource",
        "sk",
        {"SKILL.md": b"m", "a.txt": b"1", "b.txt": b"2"},
        expected_version=created.version_hash,
    )
    b = definitions.write_file(
        "resource", "sk", "b.txt", b"changed", expected_version=a.version_hash
    )
    assert b.version_hash != a.version_hash
    back = definitions.write_file("resource", "sk", "b.txt", b"2", expected_version=b.version_hash)
    assert back.version_hash == a.version_hash  # 같은 파일 집합이면 같은 해시


def test_write_files_is_one_version_and_if_match_guards_every_write(
    definitions: DefinitionStore,
) -> None:
    created = definitions.create("resource", skill())
    stored = definitions.write_files(
        "resource",
        "sk",
        {"SKILL.md": b"m", "a.txt": b"1"},
        expected_version=created.version_hash,
        message="두 파일",
    )
    versions = definitions.list_versions("resource", "sk")
    assert versions[0].message == "두 파일"
    assert len(versions) == 2  # 생성 + 한 번의 쓰기
    with pytest.raises(VersionConflict):
        definitions.write_file("resource", "sk", "c.txt", b"3", expected_version="stale")
    with pytest.raises(VersionConflict):
        definitions.delete_file("resource", "sk", "a.txt", expected_version=created.version_hash)
    # 삭제와 쓰기를 한 번에
    after = definitions.write_files(
        "resource", "sk", {"a.txt": None, "b.txt": b"2"}, expected_version=stored.version_hash
    )
    assert [f.path for f in definitions.list_files("resource", "sk")] == ["SKILL.md", "b.txt"]
    assert after.version_hash != stored.version_hash


def test_failed_write_changes_nothing(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", skill())
    ok = definitions.write_file(
        "resource", "sk", "a.txt", b"1", expected_version=created.version_hash
    )
    with pytest.raises(InvalidContentPath):
        definitions.write_files(
            "resource", "sk", {"b.txt": b"2", "../x": b"3"}, expected_version=ok.version_hash
        )
    assert [f.path for f in definitions.list_files("resource", "sk")] == ["a.txt"]
    assert definitions.get("resource", "sk").version_hash == ok.version_hash


def test_file_folder_and_case_collisions_are_rejected(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", skill())
    v = definitions.write_file(
        "resource", "sk", "docs/a.md", b"1", expected_version=created.version_hash
    )
    for bad in ("docs", "docs/a.md/b", "DOCS/A.MD", "docs/A.md"):
        with pytest.raises(InvalidContentPath):
            definitions.write_file("resource", "sk", bad, b"x", expected_version=v.version_hash)
    with pytest.raises(InvalidContentPath):  # 한 번에 보낸 두 경로끼리도
        definitions.write_files(
            "resource", "sk", {"x": b"1", "X": b"2"}, expected_version=v.version_hash
        )
    # 같은 경로를 덮어쓰는 것은 된다
    definitions.write_file("resource", "sk", "docs/a.md", b"2", expected_version=v.version_hash)


def test_content_limit_counts_the_whole_resource(tmp_path: Path) -> None:
    for store in (
        InMemoryDefinitionStore(max_content_bytes=10),
        FileDefinitionStore(tmp_path, max_content_bytes=10),
    ):
        created = store.create("resource", skill())
        v = store.write_file(
            "resource", "sk", "a", b"123456", expected_version=created.version_hash
        )
        with pytest.raises(ContentTooLarge) as caught:
            store.write_file("resource", "sk", "b", b"12345", expected_version=v.version_hash)
        assert caught.value.code == "payload_too_large"
        assert [f.path for f in store.list_files("resource", "sk")] == ["a"]
        # 덮어쓰기는 옛 크기를 빼고 센다, 지우면 한도가 비는 것도
        v = store.write_file("resource", "sk", "a", b"1234567890", expected_version=v.version_hash)
        v = store.write_files(
            "resource", "sk", {"a": None, "b": b"12345"}, expected_version=v.version_hash
        )
        with pytest.raises(ContentTooLarge):  # write_content도 같은 한도
            store.write_content("resource", "sk", b"x" * 6, expected_version=v.version_hash)


def test_limit_none_means_unlimited() -> None:
    store = InMemoryDefinitionStore(max_content_bytes=None)
    created = store.create("resource", skill())
    store.write_file("resource", "sk", "big", b"x" * 100_000, expected_version=created.version_hash)


def test_default_limit_is_ten_mib() -> None:
    store = InMemoryDefinitionStore()
    created = store.create("resource", skill())
    with pytest.raises(ContentTooLarge):
        store.write_file(
            "resource",
            "sk",
            "big",
            b"x" * (10 * 1024 * 1024 + 1),
            expected_version=created.version_hash,
        )


def test_kinds_without_multi_file_refuse_file_api(definitions: DefinitionStore) -> None:
    definitions.create("agent", {"id": "a1", "name": "a"})
    with pytest.raises(ValueError, match="multiple content files"):
        definitions.list_files("agent", "a1")
    with pytest.raises(ValueError, match="multiple"):
        definitions.write_file("agent", "a1", "x", b"1")


def test_multi_file_needs_content_field() -> None:
    with pytest.raises(ValueError, match="content_field"):
        DefinitionKind("bad", directory="bad", multi_file=True)


def test_delete_removes_every_file(definitions: DefinitionStore) -> None:
    created = definitions.create("resource", skill())
    definitions.write_files(
        "resource",
        "sk",
        {"SKILL.md": b"m", "a/b/c.txt": b"1"},
        expected_version=created.version_hash,
    )
    definitions.delete("resource", "sk")
    with pytest.raises(NotFound):
        definitions.list_files("resource", "sk")
    again = definitions.create("resource", skill())
    assert definitions.list_files("resource", "sk") == []
    assert again.version_hash == created.version_hash


def test_file_store_layout_and_hand_added_files(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", skill())
    v1 = store.write_files(
        "resource",
        "sk",
        {"SKILL.md": b"m", "scripts/run.py": b"1"},
        expected_version=created.version_hash,
    )
    folder = tmp_path / "resources" / "sk"
    assert (folder / "scripts" / "run.py").read_bytes() == b"1"
    (folder / "notes.txt").write_bytes("손으로 추가".encode())
    now = store.get("resource", "sk")
    assert now.version_hash != v1.version_hash
    assert store.get_version("resource", "sk", now.version_hash).message == "외부 변경 감지"
    assert [f.path for f in store.list_files("resource", "sk")] == [
        "SKILL.md",
        "notes.txt",
        "scripts/run.py",
    ]
    # 외부 변경으로 만든 버전도 본문 스냅샷을 가진다
    assert {f.path for f in store.list_version_files("resource", "sk", now.version_hash)} == {
        "SKILL.md",
        "notes.txt",
        "scripts/run.py",
    }


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_links_are_not_listed_and_linked_folder_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("비밀", encoding="utf-8")
    store = FileDefinitionStore(tmp_path / "ws")
    created = store.create("resource", skill())
    v = store.write_file("resource", "sk", "ok.txt", b"1", expected_version=created.version_hash)
    folder = tmp_path / "ws" / "resources" / "sk"
    try:
        (folder / "link.txt").symlink_to(outside / "secret.txt")
        (folder / "dirlink").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not permitted")
    assert [f.path for f in store.list_files("resource", "sk")] == ["ok.txt"]
    with pytest.raises(InvalidContentPath):
        store.read_file("resource", "sk", "dirlink/secret.txt")
    with pytest.raises(InvalidContentPath):
        store.read_file("resource", "sk", "link.txt")
    with pytest.raises(InvalidContentPath):
        store.write_file("resource", "sk", "dirlink/x", b"x", expected_version=v.version_hash)
    store.delete("resource", "sk")
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "비밀"


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한")
def test_body_folder_that_is_a_link_is_checked_from_the_workspace_root(tmp_path: Path) -> None:
    """`resources/<id>` 자체가 밖을 가리키는 링크여도(폴더 기준 검사는 통과하던 경우) 거부한다."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("비밀", encoding="utf-8")
    store = FileDefinitionStore(tmp_path / "ws")
    created = store.create("resource", skill())
    folder = tmp_path / "ws" / "resources" / "sk"
    try:
        folder.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not permitted")
    with pytest.raises(InvalidContentPath):
        store.read_file("resource", "sk", "secret.txt")
    with pytest.raises(DefinitionCorrupt):  # 정의 전체가 읽을 수 없는 것으로 다뤄진다
        store.write_file("resource", "sk", "x.txt", b"x", expected_version=created.version_hash)
    with pytest.raises(DefinitionCorrupt):
        store.get("resource", "sk")
    with pytest.raises(DefinitionCorrupt):
        store.list_files("resource", "sk")
    store.delete("resource", "sk")  # 삭제는 되지만 밖의 파일은 건드리지 않는다
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "비밀"
    assert list(outside.iterdir()) == [outside / "secret.txt"]


def test_orphan_body_folders_are_listed_and_pruned(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create("resource", skill())
    store.write_file("resource", "sk", "a.txt", b"1", expected_version=created.version_hash)
    orphan = tmp_path / "resources" / "ghost"
    (orphan / "deep").mkdir(parents=True)
    (orphan / "deep" / "f.txt").write_bytes(b"x")
    (tmp_path / "resources" / "bad name").mkdir()
    assert store.orphan_bodies("resource") == ["ghost"]
    assert store.orphan_bodies("agent") == []
    assert store.prune_orphan_bodies("resource") == ["ghost"]
    assert not orphan.exists()
    assert (tmp_path / "resources" / "sk" / "a.txt").exists()  # 정의가 있는 폴더는 그대로
    assert store.orphan_bodies("resource") == []


def test_memory_store_orphans() -> None:
    store = InMemoryDefinitionStore()
    store._bodies[("resource", "ghost", "f")] = b"x"  # 저장 도중 종료로 남은 상태를 흉내
    assert store.orphan_bodies("resource") == ["ghost"]
    assert store.prune_orphan_bodies("resource") == ["ghost"]
    assert store.orphan_bodies("resource") == []


# ---- 본문 스냅샷 · 복원 · 보존 ------------------------------------------------
@pytest.fixture(params=["sqlite", "memory"])
def snap_store(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    def make(**kw: Any) -> Any:
        if request.param == "sqlite":
            db = open_sqlite(tmp_path / "s.sqlite3")
            request.addfinalizer(db.close)
            return db, FileDefinitionStore(tmp_path / "ws", versions=db.versions, **kw)
        return None, InMemoryDefinitionStore(**kw)

    return make


def test_every_save_snapshots_the_body_and_old_versions_stay_readable(snap_store: Any) -> None:
    _, store = snap_store()
    created = store.create("resource", skill())
    v1 = store.write_files(
        "resource", "sk", {"SKILL.md": b"v1", "a.txt": b"A"}, expected_version=created.version_hash
    )
    v2 = store.write_files(
        "resource", "sk", {"SKILL.md": b"v2", "a.txt": None}, expected_version=v1.version_hash
    )
    assert [f.path for f in store.list_version_files("resource", "sk", v1.version_hash)] == [
        "SKILL.md",
        "a.txt",
    ]
    assert store.read_version_file("resource", "sk", v1.version_hash, "SKILL.md") == b"v1"
    assert store.read_version_file("resource", "sk", v1.version_hash, "a.txt") == b"A"
    assert store.read_version_file("resource", "sk", v2.version_hash, "SKILL.md") == b"v2"
    assert store.list_version_files("resource", "sk", created.version_hash) == []  # 본문 없음
    with pytest.raises(NotFound):
        store.read_version_file("resource", "sk", v2.version_hash, "a.txt")
    with pytest.raises(NotFound):
        store.list_version_files("resource", "sk", "nope")


def test_blobs_are_shared_between_versions_with_same_content(snap_store: Any) -> None:
    db, store = snap_store()
    created = store.create("resource", skill())
    v1 = store.write_file(
        "resource", "sk", "big", b"same" * 100, expected_version=created.version_hash
    )
    store.write_file("resource", "sk", "other", b"o", expected_version=v1.version_hash)
    if db is not None:
        with db.engine.connect() as conn:
            rows = conn.exec_driver_sql("SELECT sha256, size FROM content_blobs").all()
        assert len(rows) == 2  # 'same'*100 한 번, 'o' 한 번 (v2가 big을 다시 넣어도 그대로)
        assert dict(rows)[sha(b"same" * 100)] == 400
    else:
        assert len(store.versions._blobs) == 2


def test_restore_brings_back_document_and_files(snap_store: Any) -> None:
    _, store = snap_store()
    created = store.create("resource", skill(description="처음"))
    v1 = store.write_files(
        "resource", "sk", {"SKILL.md": b"v1", "a.txt": b"A"}, expected_version=created.version_hash
    )
    changed = {**skill(description="나중")}
    v2 = store.save("resource", changed, expected_version=v1.version_hash)
    v3 = store.write_files(
        "resource",
        "sk",
        {"SKILL.md": b"v2", "b.txt": b"B", "a.txt": None},
        expected_version=v2.version_hash,
    )
    with pytest.raises(VersionConflict):
        store.restore_version("resource", "sk", v1.version_hash, expected_version="stale")
    restored = store.restore_version(
        "resource", "sk", v1.version_hash, expected_version=v3.version_hash
    )
    assert restored.version_hash == v1.version_hash  # 같은 내용이니 같은 해시
    assert restored.document["description"] == "처음"
    assert [f.path for f in store.list_files("resource", "sk")] == ["SKILL.md", "a.txt"]
    assert store.read_file("resource", "sk", "SKILL.md") == b"v1"
    assert store.read_file("resource", "sk", "a.txt") == b"A"
    assert store.get("resource", "sk").version_hash == v1.version_hash
    with pytest.raises(NotFound):
        store.restore_version("resource", "sk", "nope", expected_version=v1.version_hash)


def test_restore_of_document_without_body_snapshot_keeps_current_files(snap_store: Any) -> None:
    _, store = snap_store()
    plain = store.create("agent", {"id": "a1", "name": "처음"})
    store.save("agent", {"id": "a1", "name": "나중"})
    back = store.restore_version("agent", "a1", plain.version_hash)
    assert back.document["name"] == "처음"
    assert store.get("agent", "a1").version_hash == plain.version_hash


def test_restore_recreates_a_deleted_definition(snap_store: Any) -> None:
    _, store = snap_store()
    created = store.create("resource", skill())
    v1 = store.write_file("resource", "sk", "a.txt", b"A", expected_version=created.version_hash)
    store.delete("resource", "sk")
    back = store.restore_version("resource", "sk", v1.version_hash)
    assert store.read_file("resource", "sk", "a.txt") == b"A"
    assert back.version_hash == v1.version_hash


def test_max_versions_trims_oldest_and_prunes_orphan_blobs(snap_store: Any) -> None:
    db, store = snap_store(max_versions=3)
    created = store.create("resource", skill())
    version = created.version_hash
    hashes = [version]
    for n in range(6):
        version = store.write_file(
            "resource", "sk", "a.txt", f"v{n}".encode(), expected_version=version
        ).version_hash
        hashes.append(version)
    listed = [v.version_hash for v in store.list_versions("resource", "sk")]
    assert listed == hashes[-1:-4:-1]  # 최신 3개
    assert store.get("resource", "sk").version_hash == hashes[-1]  # 현재는 항상 남는다
    with pytest.raises(NotFound):
        store.get_version("resource", "sk", hashes[0])
    if db is not None:
        with db.engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT count(*) FROM content_blobs").scalar() == 3
    else:
        assert len(store.versions._blobs) == 3
    assert store.prune_blobs() == 0


def test_max_versions_none_keeps_everything(snap_store: Any) -> None:
    _, store = snap_store()
    version = store.create("resource", skill()).version_hash
    for n in range(5):
        version = store.write_file(
            "resource", "sk", "a", str(n).encode(), expected_version=version
        ).version_hash
    assert len(store.list_versions("resource", "sk")) == 6


def test_trim_keeps_graph_versions_that_runs_point_at(snap_store: Any) -> None:
    db, store = snap_store(max_versions=2)
    storage = db if db is not None else InMemoryStorage()
    if db is None:
        store = InMemoryDefinitionStore(versions=storage.versions, max_versions=2)
    graph = {"id": "g", "name": "g", "nodes": [], "edges": []}
    first = store.create("graph", graph)
    storage.runs.save(
        Run(
            id="r1",
            graph_id="g",
            graph_version=first.version_hash,
            status="completed",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    version = first.version_hash
    for n in range(4):
        version = store.save(
            "graph", {**graph, "name": f"g{n}"}, expected_version=version
        ).version_hash
    kept = {v.version_hash for v in store.list_versions("graph", "g")}
    assert first.version_hash in kept  # Run이 가리키므로 남는다
    assert version in kept
    assert len(kept) == 2  # 보호 대상 + 현재(= keep 안에 포함)


def test_trim_on_repository_never_deletes_protected(snap_store: Any) -> None:
    db, _ = snap_store()
    repo = db.versions if db is not None else InMemoryStorage().versions
    for n in range(5):
        repo.record("agent", "a", f"h{n}", {"n": n}, saved_at=float(n))
    assert (
        repo.trim("agent", "a", keep=1, protect=("h0",)) == 4
    )  # 보호가 keep을 채우면 나머지는 모두 지운다
    assert [v.version_hash for v in repo.list("agent", "a")] == ["h0"]
