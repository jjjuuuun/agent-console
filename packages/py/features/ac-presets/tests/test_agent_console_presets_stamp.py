"""`apply_preset(stamp=)`: 만든 항목에 최상위 필드 찍기(프로젝트 범위, design §UX-P.4·5.2R.31)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_presets import (
    MANIFEST_FILE,
    Preset,
    apply_preset,
    apply_stamp,
    load_preset,
    stamp_fields,
)
from agent_console_store import AGENT_KIND, DefinitionKind, InMemoryDefinitionStore


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def preset(tmp_path: Path) -> Preset:
    folder = tmp_path / "p1"
    _write(folder / "agents" / "a1.yaml", {"id": "a1", "name": "에이전트", "project": "old"})
    _write(folder / "graphs" / "g1.yaml", {"id": "g1", "name": "그래프", "nodes": []})
    _write(
        folder / MANIFEST_FILE,
        {"id": "p1", "name": "프리셋", "items": ["agents/a1.yaml", "graphs/g1.yaml"]},
    )
    return load_preset(folder)


def test_stamp_marks_created_items(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    report = apply_preset(preset, store, stamp={"project": "app"})
    assert report.ok
    assert report.warnings == []
    assert store.get("agent", "a1").document["project"] == "app"  # 프리셋 값을 덮어씀
    assert store.get("graph", "g1").document["project"] == "app"


def test_no_stamp_keeps_documents_as_is(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    apply_preset(preset, store)
    assert store.get("agent", "a1").document["project"] == "old"
    assert "project" not in store.get("graph", "g1").document


def test_none_value_removes_field_and_skipped_items_untouched(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("graph", {"id": "g1", "name": "사용자 것", "project": "mine"})
    report = apply_preset(preset, store, stamp={"project": None})
    assert [i.action for i in report.items] == ["created", "skipped"]
    assert "project" not in store.get("agent", "a1").document  # None = 공용(필드 빼기)
    assert store.get("graph", "g1").document["project"] == "mine"


def test_overwrite_and_rename_are_stamped(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    store.create("agent", {"id": "a1", "name": "사용자 것"})
    apply_preset(preset, store, on_conflict="rename", stamp={"project": "app"})
    assert "project" not in store.get("agent", "a1").document
    assert store.get("agent", "a1-2").document["project"] == "app"
    apply_preset(preset, store, on_conflict="overwrite", stamp={"project": "p2"})
    assert store.get("agent", "a1").document["project"] == "p2"


def test_stamp_is_validated_after_stamping(preset: Preset) -> None:
    seen: list[dict[str, Any]] = []

    def check(kind: str, doc: Any) -> list[str]:
        seen.append(dict(doc))
        return []

    apply_preset(preset, InMemoryDefinitionStore(), stamp={"project": "app"}, validate_item=check)
    assert {d.get("project") for d in seen} == {"app"}


def test_fields_unknown_to_kind_model_are_not_stamped(preset: Preset) -> None:
    store = InMemoryDefinitionStore()
    report = apply_preset(preset, store, stamp={"project": "app", "zz_unknown": 1, "id": "x"})
    assert "zz_unknown" not in store.get("agent", "a1").document
    assert store.get("agent", "a1").document["id"] == "a1"
    assert report.warnings == [
        "stamp fields not in agent: zz_unknown, id",
        "stamp fields not in graph: zz_unknown, id",
    ]


def test_stamp_helpers() -> None:
    free = DefinitionKind(name="note", directory="notes")
    assert stamp_fields(free, {"project": "a", "x": 1}) == ({"project": "a", "x": 1}, [])
    assert stamp_fields(AGENT_KIND, {"project": "a", "x": 1}) == ({"project": "a"}, ["x"])
    assert stamp_fields(None, {"id": "z"}) == ({}, ["id"])
    doc = {"id": "a", "project": "p", "tags": ["t"]}
    assert apply_stamp(doc, {"project": None, "more": {"k": 1}}) == {
        "id": "a",
        "tags": ["t"],
        "more": {"k": 1},
    }
    assert doc["project"] == "p"  # 원본은 그대로
