"""매니페스트 선택 키 `featured`·`badges`·`start_graph`와 항목 훑기 `collect_values`(5.2R.6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_presets import (
    MANIFEST_FILE,
    PresetManifest,
    collect_values,
    load_items,
    load_preset,
)


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_manifest_optional_start_keys_default_off() -> None:
    m = PresetManifest.model_validate({"id": "p", "name": "P"})
    assert (m.featured, m.badges, m.start_graph, m.start_graph_id()) == (None, [], None, None)


def test_start_graph_falls_back_to_default_entry_unless_set() -> None:
    base = {"id": "p", "name": "P", "default_entry": "g"}
    assert PresetManifest.model_validate(base).start_graph_id() == "g"
    assert PresetManifest.model_validate({**base, "start_graph": None}).start_graph_id() is None
    assert PresetManifest.model_validate({**base, "start_graph": "h"}).start_graph_id() == "h"
    full = PresetManifest.model_validate({**base, "featured": 1, "badges": ["추천"]})
    assert (full.featured, full.badges) == (1, ["추천"])


def test_collect_values_walks_nested_documents(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    _write(folder / "agents" / "a.yaml", {"id": "a", "name": "A", "backend": "b1"})
    _write(
        folder / "graphs" / "g.yaml",
        {
            "id": "g",
            "name": "G",
            "settings": {"backend": "b2"},
            "nodes": [{"id": "n", "type": "agent", "settings": {"backend": "b1"}}],
        },
    )
    _write(
        folder / MANIFEST_FILE,
        {"id": "p", "name": "P", "items": ["agents/a.yaml", "graphs/g.yaml"]},
    )
    items = load_items(load_preset(folder))
    assert collect_values(items, "backend") == ["b1", "b2"]
    assert collect_values(items, "nothing") == []
    assert collect_values([], "backend") == []
