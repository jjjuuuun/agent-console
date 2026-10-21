"""2R.3 QA: 삭제 범위, 1R 작업 공간 해시 호환, 링크 보호."""

import os
from pathlib import Path

import pytest

from agent_console_store import FileDefinitionStore, default_hash


def _doc() -> dict[str, object]:
    return {
        "kind": "resource",
        "id": "sk",
        "type": "skill",
        "name": "s",
        "content": {"file": "SKILL.md"},
    }


def test_delete_only_touches_own_folder_and_keeps_links_and_neighbors(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("k")
    store = FileDefinitionStore(ws)
    created = store.create("resource", _doc())
    store.write_files(
        "resource", "sk", {"SKILL.md": b"m", "d/x.txt": b"1"}, expected_version=created.version_hash
    )
    other = store.create("resource", {**_doc(), "id": "other"})
    store.write_file("resource", "other", "SKILL.md", b"o", expected_version=other.version_hash)
    folder = ws / "resources" / "sk"
    (folder / "hand.txt").write_text("손")
    (ws / "resources" / "unrelated.txt").write_text("u")
    if os.name != "nt":
        try:
            (folder / "lnk").symlink_to(outside, target_is_directory=True)
            (folder / "flnk.txt").symlink_to(outside / "keep.txt")
        except OSError:
            pytest.skip("symlink")
    store.delete("resource", "sk")
    assert not (folder / "hand.txt").exists()
    assert (outside / "keep.txt").read_text() == "k"
    assert (ws / "resources" / "other" / "SKILL.md").exists()
    assert (ws / "resources" / "unrelated.txt").exists()


def test_1r_workspace_single_file_keeps_pre_v3_hash(tmp_path: Path) -> None:
    """1R 방식(정의 YAML + 본문 파일 하나)으로 손수 만든 작업 공간의 해시 = 옛 공식."""
    import hashlib

    ws = tmp_path / "ws"
    store = FileDefinitionStore(ws)
    created = store.create("resource", _doc())
    v = store.write_content("resource", "sk", b"hello", expected_version=created.version_hash)
    # 새 저장소 인스턴스(= 재시작)도 같은 해시
    again = FileDefinitionStore(ws).get("resource", "sk")
    old = default_hash({**again.document, "$content_sha256": hashlib.sha256(b"hello").hexdigest()})
    assert again.version_hash == v.version_hash == old


@pytest.mark.skipif(os.name == "nt", reason="symlink")
def test_prune_orphans_does_not_follow_links(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("k")
    store = FileDefinitionStore(ws)
    orphan = ws / "resources" / "ghost"
    orphan.mkdir(parents=True)
    (orphan / "a.txt").write_text("a")
    try:
        (orphan / "lnk").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink")
    store.prune_orphan_bodies("resource")
    assert (outside / "keep.txt").read_text() == "k"
