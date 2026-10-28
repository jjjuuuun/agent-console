"""공간 열기와 정의 저장: workspace 정의 YAML과 같은 형식, 공간별 버전, 종류 이름은 데이터."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_console_project_space import (
    FolderMissing,
    SpaceLayout,
    UnsafeConfigDir,
    open_space,
    portable_kinds,
)
from agent_console_project_space.testing import sample_agent, snapshot_tree
from agent_console_store import (
    DEFAULT_KINDS,
    DefinitionCorrupt,
    DefinitionKind,
    FileDefinitionStore,
    InMemoryVersionRepository,
    InvalidContentPath,
    NotFound,
)


def test_open_writes_nothing_and_lists_empty(folder: Path) -> None:
    space = open_space(folder)
    assert space.definitions.list_ids("agent") == []
    assert space.root == folder / ".agent-console"
    assert snapshot_tree(folder) == {}
    assert space.config_writable is True


def test_save_uses_same_format_as_workspace_store(folder: Path, tmp_path: Path) -> None:
    space = open_space(folder)
    space.definitions.create("agent", sample_agent("a1", attributes={"x": 1}))
    workspace = FileDefinitionStore(tmp_path / "ws")
    workspace.create("agent", sample_agent("a1", attributes={"x": 1}))
    mine = (folder / ".agent-console" / "agents" / "a1.yaml").read_bytes()
    assert mine == (tmp_path / "ws" / "agents" / "a1.yaml").read_bytes()


def test_paths_come_from_layout_and_config_dir(folder: Path) -> None:
    layout = SpaceLayout(memory_file="mem.db", records_file="rec.db", sessions_dir="keep")
    space = open_space(folder, config_dir="cfg/ac", layout=layout)
    assert space.root == folder / "cfg" / "ac"
    assert space.memory_db_path == folder / "cfg/ac/mem.db"
    assert space.records_db_path == folder / "cfg/ac/rec.db"
    assert space.sessions_dir == folder / "cfg/ac/keep"
    assert space.state_dir == folder / "cfg/ac/.state"
    space.definitions.create("agent", sample_agent())
    assert (folder / "cfg/ac/agents/a1.yaml").is_file()


@pytest.mark.parametrize("bad", ["", "/abs", "../up", "a/../b", "a\\b", "C:/x"])
def test_config_dir_must_stay_inside(folder: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="config_dir"):
        open_space(folder, config_dir=bad)


def test_layout_rejects_escaping_names() -> None:
    with pytest.raises(ValueError, match="records_file"):
        SpaceLayout(records_file="../records.sqlite3")


def test_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(FolderMissing):
        open_space(tmp_path / "nope")


def test_versions_differ_per_space(tmp_path: Path) -> None:
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a = open_space(a_dir, versions=InMemoryVersionRepository())
    b = open_space(b_dir, versions=InMemoryVersionRepository())
    a.definitions.create("agent", sample_agent(attributes={"v": 1}))
    a.definitions.save("agent", sample_agent(attributes={"v": 2}))
    b.definitions.create("agent", sample_agent(attributes={"v": 9}))
    assert len(a.definitions.list_versions("agent", "a1")) == 2
    assert len(b.definitions.list_versions("agent", "a1")) == 1
    assert a.definitions.get("agent", "a1").document["attributes"] == {"v": 2}


def test_singleton_and_non_portable_kinds_stay_out(folder: Path) -> None:
    mine = DefinitionKind(name="note", directory="notes")
    hidden = DefinitionKind(name="registry", directory="registry", portable=False)
    single = DefinitionKind(name="prefs", singleton_file="prefs.yaml", portable=True)
    kinds = (*DEFAULT_KINDS, mine, hidden, single)
    assert [k.name for k in portable_kinds(kinds)] == ["graph", "agent", "resource", "note"]
    space = open_space(folder, kinds=kinds)
    assert space.portable_kinds == ("graph", "agent", "resource", "note")
    assert sorted(space.definitions.kinds()) == sorted(space.portable_kinds)
    for name in ("settings", "registry", "prefs"):
        with pytest.raises(NotFound):
            space.definitions.get(name, name)
        with pytest.raises(NotFound):
            space.definitions.create(name, {"id": name})
    assert snapshot_tree(folder) == {}


def test_renamed_fake_kind_behaves_the_same(folder: Path) -> None:
    kind = DefinitionKind(name="zork", directory="zorks", require_version=True)
    space = open_space(folder, kinds=[kind])
    created = space.definitions.create("zork", {"id": "z1", "color": "red"})
    assert (folder / ".agent-console/zorks/z1.yaml").is_file()
    assert space.definitions.summaries("zork")[0].id == "z1"
    space.definitions.save(
        "zork", {"id": "z1", "color": "blue"}, expected_version=created.version_hash
    )
    assert len(space.definitions.list_versions("zork", "z1")) == 2


def test_link_and_dotdot_are_rejected_as_before(folder: Path, tmp_path: Path) -> None:
    space = open_space(folder)
    store = space.definitions
    doc = {"id": "r1", "type": "instruction", "name": "n", "content": {"file": "a.md"}}
    store.create("resource", doc)
    version = store.get("resource", "r1").version_hash
    for bad in ("../escape.md", "/abs.md"):
        with pytest.raises(InvalidContentPath):
            store.write_file("resource", "r1", bad, b"x", expected_version=version)
    outside = tmp_path / "outside"
    outside.mkdir()
    body = folder / ".agent-console" / "resources" / "r1"
    shutil.rmtree(body, ignore_errors=True)
    body.symlink_to(outside, target_is_directory=True)
    with pytest.raises((InvalidContentPath, DefinitionCorrupt)):
        store.write_file("resource", "r1", "b.md", b"x", expected_version=version)
    assert list(outside.iterdir()) == []


def test_config_dir_that_is_a_link_is_refused(folder: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (folder / ".agent-console").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeConfigDir):
        open_space(folder)
    assert list(outside.iterdir()) == []
