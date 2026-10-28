"""5.7R.33w: `DefinitionKind.portable`과 `write_guard`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_store import (
    DEFAULT_KINDS,
    SETTINGS_KIND,
    DefinitionKind,
    DefinitionStore,
    FileDefinitionStore,
    InMemoryDefinitionStore,
)


def test_default_portable_flags() -> None:
    assert {k.name: k.is_portable for k in DEFAULT_KINDS} == {
        "graph": True,
        "agent": True,
        "settings": False,
        "resource": True,
    }
    assert SETTINGS_KIND.portable is False


def test_singleton_is_never_portable() -> None:
    kind = DefinitionKind("prefs", singleton_file="prefs.yaml", portable=True)
    assert kind.is_singleton
    assert kind.is_portable is False
    assert DefinitionKind("x", directory="x", portable=False).is_portable is False


class DeniedError(Exception):
    pass


def _deny(
    kind: DefinitionKind, id: str, document: Mapping[str, Any], files: Mapping[str, bytes]
) -> None:
    if document.get("name") == "bad":
        raise DeniedError(id)


def _stores(tmp_path: Path) -> list[DefinitionStore]:
    return [
        FileDefinitionStore(tmp_path / "ws", write_guard=_deny),
        InMemoryDefinitionStore(write_guard=_deny),
    ]


@pytest.mark.parametrize("which", [0, 1])
def test_guard_blocks_before_anything_is_written(tmp_path: Path, which: int) -> None:
    store = _stores(tmp_path)[which]
    ok = store.create("agent", {"id": "a1", "name": "good"})
    with pytest.raises(DeniedError):
        store.create("agent", {"id": "a2", "name": "bad"})
    with pytest.raises(DeniedError):
        store.save("agent", {"id": "a1", "name": "bad"})
    assert store.list_ids("agent") == ["a1"]
    assert store.get("agent", "a1").version_hash == ok.version_hash
    assert len(store.list_versions("agent", "a1")) == 1
    store.create("agent", {"id": "a3", "name": "fine"})


def test_guard_sees_body_files_and_blocks_restore(tmp_path: Path) -> None:
    seen: list[tuple[str, dict[str, bytes]]] = []
    blocked = {"on": False}

    def guard(
        kind: DefinitionKind, id: str, document: Mapping[str, Any], files: Mapping[str, bytes]
    ) -> None:
        seen.append((id, dict(files)))
        if blocked["on"]:
            raise DeniedError(id)

    store = FileDefinitionStore(tmp_path, write_guard=guard)
    doc = {"id": "r1", "type": "instruction", "name": "n", "content": {"file": "a.md"}}
    first = store.create("resource", doc)
    store.write_file("resource", "r1", "a.md", b"hello", expected_version=first.version_hash)
    assert seen[-1] == ("r1", {"a.md": b"hello"})
    second = store.get("resource", "r1")
    blocked["on"] = True
    with pytest.raises(DeniedError):
        store.restore_version(
            "resource", "r1", first.version_hash, expected_version=second.version_hash
        )
    assert store.read_file("resource", "r1", "a.md") == b"hello"
