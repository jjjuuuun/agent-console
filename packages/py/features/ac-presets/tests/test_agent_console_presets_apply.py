"""ac-presets 단위: 매니페스트 읽기, 탐색, 적용(충돌 정책·기본 진입점·참조 고치기), 오류.

테스트 프리셋은 tmp 폴더에 즉석으로 만든다(번들 프리셋 내용과 무관).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_presets import (
    ITEM_INVALID,
    MANIFEST_FILE,
    Preset,
    PresetError,
    RenameMap,
    apply_preset,
    discover_presets,
    load_items,
    load_preset,
    order_items,
)
from agent_console_store import FileDefinitionStore, InMemoryDefinitionStore


def write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON은 YAML의 부분집합이다.
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_preset(root: Path, pid: str = "p1", **manifest: Any) -> Path:
    folder = root / pid
    write(folder / "agents" / "a1.yaml", {"kind": "agent", "id": "a1", "name": "에이전트"})
    write(
        folder / "graphs" / "g1.yaml",
        {
            "kind": "graph",
            "id": "g1",
            "name": "그래프",
            "nodes": [{"id": "n1", "type": "t", "config": {"ref": "a1"}}],
        },
    )
    doc: dict[str, Any] = {
        "kind": "preset",
        "id": pid,
        "name": "프리셋",
        "items": ["agents/a1.yaml", {"file": "graphs/g1.yaml", "kind": "graph"}],
        "default_entry": "g1",
    }
    doc.update(manifest)
    write(folder / MANIFEST_FILE, doc)
    return folder


@pytest.fixture
def preset(tmp_path: Path) -> Preset:
    return load_preset(make_preset(tmp_path / "presets"))


def test_load_preset_reads_manifest(preset: Preset) -> None:
    assert preset.id == "p1"
    assert [r.file for r in preset.manifest.item_refs()] == ["agents/a1.yaml", "graphs/g1.yaml"]
    items = load_items(preset)
    assert [(i.kind, i.id) for i in items] == [("agent", "a1"), ("graph", "g1")]


def test_apply_creates_files_in_workspace(preset: Preset, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    store = FileDefinitionStore(ws)
    report = apply_preset(preset, store)
    assert report.ok
    assert [(i.kind, i.target_id, i.action) for i in report.items] == [
        ("agent", "a1", "created"),
        ("graph", "g1", "created"),
    ]
    assert (ws / "agents" / "a1.yaml").is_file()
    assert (ws / "graphs" / "g1.yaml").is_file()
    assert not (ws / "settings.yaml").exists()  # 프리셋 적용은 설정을 건드리지 않는다


def test_conflict_skip_keeps_user_definition(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    report = apply_preset(preset, store)
    assert [i.action for i in report.items] == ["skipped", "created"]
    assert store.get("agent", "a1").document["name"] == "사용자 것"


def test_conflict_overwrite_uses_if_match(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    store.create("graph", {"id": "g1", "name": "사용자 그래프"})  # graph는 If-Match 필수 종류
    report = apply_preset(preset, store, on_conflict="overwrite")
    assert [i.action for i in report.items] == ["overwritten", "overwritten"]
    assert store.get("agent", "a1").document["name"] == "에이전트"
    assert store.get("graph", "g1").document["name"] == "그래프"


def test_conflict_rename_with_reference_rewriter(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    store.create("agent", {"id": "a1-2", "name": "사용자 것 2"})

    def rewrite(kind: str, doc: dict[str, Any], renames: RenameMap) -> dict[str, Any]:
        if kind == "graph":
            for node in doc["nodes"]:
                ref = node["config"].get("ref")
                node["config"]["ref"] = renames.get(("agent", ref), ref)
        return doc

    report = apply_preset(preset, store, on_conflict="rename", rewrite_references=rewrite)
    assert [(i.target_id, i.action) for i in report.items] == [
        ("a1-3", "renamed"),
        ("g1", "created"),
    ]
    assert report.renames() == {("agent", "a1"): "a1-3"}
    assert report.warnings == []
    assert store.get("agent", "a1-3").document["name"] == "에이전트"
    assert store.get("graph", "g1").document["nodes"][0]["config"]["ref"] == "a1-3"


def test_rename_without_rewriter_warns(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("graph", {"id": "g1", "name": "사용자 그래프"})
    report = apply_preset(preset, store, on_conflict="rename")
    assert [i.target_id for i in report.items] == ["a1", "g1-2"]
    assert any("renamed without rewriting" in w for w in report.warnings)


def test_invalid_item_document_writes_nothing(tmp_path: Path) -> None:
    folder = make_preset(tmp_path)
    write(folder / "graphs" / "g1.yaml", {"kind": "graph", "id": "g1"})  # name 없음
    store = InMemoryDefinitionStore()
    with pytest.raises(PresetError):
        apply_preset(load_preset(folder), store)
    assert store.list_ids("agent") == []


def test_bad_manifest(tmp_path: Path) -> None:
    with pytest.raises(PresetError):
        load_preset(tmp_path)  # 매니페스트 없음
    write(tmp_path / MANIFEST_FILE, {"kind": "preset", "id": "bad id!", "name": "x"})
    with pytest.raises(PresetError):
        load_preset(tmp_path)
    (tmp_path / MANIFEST_FILE).write_text("- not a mapping", encoding="utf-8")
    with pytest.raises(PresetError):
        load_preset(tmp_path)


def test_discover_multiple_paths(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    make_preset(first, "p1")
    make_preset(second, "p1")  # 같은 id → 앞 경로가 이김
    make_preset(second, "p2")
    (second / "broken").mkdir()
    (second / "broken" / MANIFEST_FILE).write_text(":", encoding="utf-8")
    (second / "not-a-preset").mkdir()
    make_preset(second, ".hidden")
    found = discover_presets([first, tmp_path / "missing", second])
    assert [p.id for p in found.presets] == ["p1", "p2"]
    assert found.get("p1") is not None
    assert found.get("p1").directory == first / "p1"  # type: ignore[union-attr]
    assert len(found.problems) == 2


def test_unknown_policy_rejected(preset: Preset) -> None:
    with pytest.raises(ValueError, match="policy"):
        apply_preset(preset, InMemoryDefinitionStore(), on_conflict="merge")  # type: ignore[arg-type]


def test_validate_item_rejects_item_without_writing(preset: Preset) -> None:
    """주입한 검사가 오류를 내면 그 항목만 `failed`, 덮어쓰기 대상은 그대로(1R.37 후속)."""
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    seen: list[tuple[str, str]] = []

    def check(kind: str, doc: Mapping[str, Any]) -> list[str]:
        seen.append((kind, str(doc["id"])))
        return ["rule.broken(/name)"] if kind == "agent" else []

    report = apply_preset(preset, store, on_conflict="overwrite", validate_item=check)
    assert seen == [("agent", "a1"), ("graph", "g1")]
    assert [(i.id, i.action) for i in report.items] == [("a1", "failed"), ("g1", "created")]
    assert report.items[0].error == f"{ITEM_INVALID}: rule.broken(/name)"
    assert not report.ok
    assert store.get("agent", "a1").document["name"] == "사용자 것"


def test_validate_item_skipped_items_are_not_checked(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    calls: list[str] = []

    def check(kind: str, doc: Mapping[str, Any]) -> list[str]:
        calls.append(kind)
        return []

    apply_preset(preset, store, validate_item=check)
    assert calls == ["graph"]


# ---------------------------------------------------------------- 의존 순서(5R.15)


def _nested_preset(root: Path) -> Preset:
    """팀 구성 parent가 자식 팀 구성 child와 에이전트 a1을 쓴다. 매니페스트는 거꾸로 적는다."""
    folder = root / "nest"
    write(folder / "graphs" / "parent.yaml", {"kind": "graph", "id": "parent", "name": "부모"})
    write(folder / "graphs" / "child.yaml", {"kind": "graph", "id": "child", "name": "자식"})
    write(folder / "agents" / "a1.yaml", {"kind": "agent", "id": "a1", "name": "에이전트"})
    write(
        folder / MANIFEST_FILE,
        {
            "kind": "preset",
            "id": "nest",
            "name": "중첩",
            "items": ["graphs/parent.yaml", "graphs/child.yaml", "agents/a1.yaml"],
        },
    )
    return load_preset(folder)


USES: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("graph", "parent"): [("agent", "a1"), ("graph", "child"), ("resource", "outside")],
    ("graph", "child"): [("agent", "a1"), ("graph", "child")],  # 자기 자신은 무시
}


def uses(kind: str, doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    return USES.get((kind, str(doc["id"])), [])


def test_dependencies_order_writes_used_definitions_first(tmp_path: Path) -> None:
    preset = _nested_preset(tmp_path)
    store = InMemoryDefinitionStore()
    report = apply_preset(preset, store, dependencies=uses)
    assert [(i.kind, i.id) for i in report.items] == [
        ("agent", "a1"),
        ("graph", "child"),
        ("graph", "parent"),
    ]
    assert report.ok
    assert report.warnings == []
    # 의존 함수가 없으면 매니페스트 순서 그대로
    plain = apply_preset(preset, InMemoryDefinitionStore())
    assert [i.id for i in plain.items] == ["parent", "child", "a1"]


def test_order_items_cycle_keeps_manifest_order_and_errors_warn(tmp_path: Path) -> None:
    items = load_items(_nested_preset(tmp_path))

    def cyclic(kind: str, doc: Mapping[str, Any]) -> list[tuple[str, str]]:
        other = {"parent": "child", "child": "parent"}.get(str(doc["id"]))
        return [("graph", other)] if other else []

    assert [i.id for i in order_items(items, cyclic)] == ["child", "parent", "a1"]

    def broken(kind: str, doc: Mapping[str, Any]) -> list[tuple[str, str]]:
        if doc["id"] == "parent":
            raise ValueError("secret-value")
        return []

    warnings: list[str] = []
    assert [i.id for i in order_items(items, broken, warnings=warnings)] == [
        "parent",
        "child",
        "a1",
    ]
    assert warnings == ["dependency check failed for graph/parent (ValueError)"]
    assert "secret-value" not in warnings[0]
