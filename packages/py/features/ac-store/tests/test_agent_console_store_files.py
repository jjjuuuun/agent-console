"""FileDefinitionStore 전용: 파일이 진실의 원천(R0.4) — 주석 보존, 외부 편집, 원자적 쓰기."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_console_store import (
    DefinitionCorrupt,
    FileDefinitionStore,
    NotFound,
    VersionConflict,
    open_sqlite,
)


def test_file_layout_and_utf8_without_bom(
    tmp_path: Path, make_graph: Callable[..., dict[str, Any]]
) -> None:
    store = FileDefinitionStore(tmp_path)
    store.create("graph", make_graph(description="한글 설명"))
    store.save("settings", {"default_entry": "g1"})
    raw = (tmp_path / "graphs" / "g1.yaml").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "한글 설명" in raw.decode("utf-8")
    assert (tmp_path / "settings.yaml").is_file()
    assert not list((tmp_path / "graphs").glob(".*tmp"))  # 임시 파일이 남지 않는다


def test_comments_and_key_order_survive_save(tmp_path: Path, clock: Callable[[], float]) -> None:
    store = FileDefinitionStore(tmp_path, clock=clock)
    path = tmp_path / "graphs" / "g1.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# 내가 쓴 메모\n"
        "kind: graph\n"
        "id: g1\n"
        "name: 손으로 만든 그래프  # 이름 주석\n"
        "my_extra: {k: v}\n"
        "nodes:\n"
        "  - id: n0\n"
        "    type: x   # 노드 주석\n",
        encoding="utf-8",
    )
    current = store.get("graph", "g1")
    doc = dict(current.document)
    doc["name"] = "바뀐 이름"
    store.save("graph", doc, expected_version=current.version_hash)
    text = path.read_text(encoding="utf-8")
    assert "# 내가 쓴 메모" in text
    assert "# 노드 주석" in text
    assert "바뀐 이름" in text
    assert text.index("my_extra") < text.index("nodes")  # 파일의 키 순서 유지
    assert store.get("graph", "g1").document["my_extra"] == {"k": "v"}


def test_multiline_and_roundtrip_hash_is_stable(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    created = store.create(
        "agent",
        {"id": "a1", "name": "A", "system_prompt": "첫 줄\n둘째 줄\n", "temperature_x": 1.0},
    )
    again = FileDefinitionStore(tmp_path).get("agent", "a1")  # 새 인스턴스로 다시 읽어도 같은 해시
    assert again.version_hash == created.version_hash
    assert again.document["system_prompt"] == "첫 줄\n둘째 줄\n"
    assert "|" in (tmp_path / "agents" / "a1.yaml").read_text(encoding="utf-8")


def test_external_edit_changes_hash_and_is_snapshotted(
    tmp_path: Path, clock: Callable[[], float], make_graph: Callable[..., dict[str, Any]]
) -> None:
    db = open_sqlite(tmp_path / "db.sqlite3")
    store = FileDefinitionStore(tmp_path / "ws", versions=db.versions, clock=clock)
    first = store.create("graph", make_graph())
    path = tmp_path / "ws" / "graphs" / "g1.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("그래프 g1", "밖에서 고침"), encoding="utf-8"
    )
    now = store.get("graph", "g1")
    assert now.version_hash != first.version_hash
    # 외부 변경도 이력에 남아 Run의 graph_version으로 조회 가능
    assert store.get_version("graph", "g1", now.version_hash).content is not None
    # 이전 해시로 저장하면 충돌
    with pytest.raises(VersionConflict):
        store.save("graph", make_graph(), expected_version=first.version_hash)
    db.close()


def test_history_persists_across_store_instances(
    tmp_path: Path, make_graph: Callable[..., dict[str, Any]]
) -> None:
    db = open_sqlite(tmp_path / "db.sqlite3")
    s1 = FileDefinitionStore(tmp_path / "ws", versions=db.versions)
    v1 = s1.create("graph", make_graph())
    db.close()
    db2 = open_sqlite(tmp_path / "db.sqlite3")
    s2 = FileDefinitionStore(tmp_path / "ws", versions=db2.versions)
    assert [v.version_hash for v in s2.list_versions("graph", "g1")] == [v1.version_hash]
    db2.close()


def test_corrupt_file_is_reported_and_skipped_in_listing(
    tmp_path: Path, make_graph: Callable[..., dict[str, Any]]
) -> None:
    store = FileDefinitionStore(tmp_path)
    store.create("graph", make_graph("ok"))
    (tmp_path / "graphs" / "broken.yaml").write_text("a: [unclosed\n", encoding="utf-8")
    (tmp_path / "graphs" / "list.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(DefinitionCorrupt):
        store.get("graph", "broken")
    with pytest.raises(DefinitionCorrupt):
        store.get("graph", "list")
    assert [s.id for s in store.summaries("graph")] == ["ok"]


def test_delete_with_expected_version(
    tmp_path: Path, make_graph: Callable[..., dict[str, Any]]
) -> None:
    """삭제도 기대 버전을 받는다(If-Match, 3R.12): 다르면 412 오류, 같으면 지운다."""
    store = FileDefinitionStore(tmp_path)
    saved = store.create("graph", make_graph())
    with pytest.raises(VersionConflict) as info:
        store.delete("graph", "g1", expected_version="other")
    assert info.value.details.current_version_hash == saved.version_hash
    assert (tmp_path / "graphs" / "g1.yaml").exists()
    with pytest.raises(NotFound):
        store.delete("graph", "nope", expected_version="x")
    store.delete("graph", "g1", expected_version=saved.version_hash)
    assert not (tmp_path / "graphs" / "g1.yaml").exists()


def test_delete_removes_file(tmp_path: Path, make_graph: Callable[..., dict[str, Any]]) -> None:
    store = FileDefinitionStore(tmp_path)
    store.create("graph", make_graph())
    store.delete("graph", "g1")
    assert not (tmp_path / "graphs" / "g1.yaml").exists()
    with pytest.raises(NotFound):
        store.get("graph", "g1")
