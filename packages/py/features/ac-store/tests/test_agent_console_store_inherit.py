"""'생략 = 상속' 보존(1R.4): 저장 전 구간에서 생략, null, 빈 목록이 구분된다.

`definitions` 픽스처가 파일+SQLite 이력, 파일(메모리 이력), 인메모리 세 구성에 같은 스위트를 돌린다.
"""

from pathlib import Path
from typing import Any

from agent_console_contracts import Agent, Graph, GraphSettings, WorkspaceSettings
from agent_console_store import DefinitionStore, FileDefinitionStore, open_sqlite

OMITTED: dict[str, Any] = {"id": "a-omit", "name": "생략"}
NULLED: dict[str, Any] = {
    "id": "a-null",
    "name": "null",
    "model": None,
    "limits": None,
    "tools": None,
}
EMPTY: dict[str, Any] = {"id": "a-empty", "name": "빈 목록", "tools": [], "labels": []}


def test_dict_documents_round_trip_exactly(definitions: DefinitionStore) -> None:
    for doc in (OMITTED, NULLED, EMPTY):
        stored = definitions.create("agent", doc)
        assert stored.document == doc  # 기본값이 채워지지 않는다
        assert definitions.get("agent", doc["id"]).document == doc


def test_omitted_null_and_empty_are_distinct_after_reading(definitions: DefinitionStore) -> None:
    for doc in (OMITTED, NULLED, EMPTY):
        definitions.create("agent", doc)
    omitted = definitions.get("agent", "a-omit").model(Agent)
    nulled = definitions.get("agent", "a-null").model(Agent)
    empty = definitions.get("agent", "a-empty").model(Agent)
    assert not {"model", "limits", "tools"} & omitted.model_fields_set
    assert {"model", "limits", "tools"} <= nulled.model_fields_set
    assert "tools" in empty.model_fields_set
    assert empty.tools == []
    assert "tools" not in omitted.model_fields_set


def test_model_instances_are_stored_without_defaults(definitions: DefinitionStore) -> None:
    agent = Agent.model_validate({"id": "m", "name": "M"})
    stored = definitions.create("agent", agent)
    assert "limits" not in stored.document
    assert "tools" not in stored.document
    assert definitions.get("agent", "m").document == agent.model_dump(
        mode="json", exclude_unset=True
    )
    explicit = Agent(id="e", name="E", tools=[], model=None)
    assert definitions.create("agent", explicit).document["tools"] == []
    assert definitions.get("agent", "e").document["model"] is None


def test_settings_singleton_keeps_omitted_groups(definitions: DefinitionStore) -> None:
    stored = definitions.save("settings", WorkspaceSettings.model_validate({}))
    assert "chat" not in stored.document
    assert definitions.get("settings", "settings").document == stored.document
    partial = {"chat": {"busy_policy": "reject"}}
    definitions.save("settings", partial)
    assert definitions.get("settings", "settings").document == partial


def test_graph_partial_nested_layer_and_unknown_fields_survive(
    definitions: DefinitionStore,
) -> None:
    doc = {
        "id": "g",
        "name": "n",
        "settings": {"chat": {"reply_display": "merged"}},
        "legacy_unknown_field": {"keep": True},
    }
    created = definitions.create("graph", doc)
    assert created.document == doc
    graph = definitions.get("graph", "g").model(Graph)
    assert isinstance(graph.settings, GraphSettings)
    assert graph.settings.chat is not None
    assert graph.settings.chat.model_fields_set == {"reply_display"}
    saved = definitions.save(
        "graph", graph.model_copy(deep=True), expected_version=created.version_hash
    )
    assert saved.document == doc


def test_version_hash_and_snapshots_distinguish_omitted_from_null(
    definitions: DefinitionStore,
) -> None:
    a = definitions.create("agent", OMITTED)
    b = definitions.create("agent", {**OMITTED, "id": "a-omit2", "model": None})
    assert a.version_hash != definitions.get("agent", "a-omit2").version_hash
    snap = definitions.get_version("agent", "a-omit2", b.version_hash)
    assert snap.content == b.document
    assert snap.content is not None
    assert snap.content["model"] is None
    first = definitions.get_version("agent", "a-omit", a.version_hash).content
    assert first == OMITTED


def test_saved_over_edit_keeps_the_difference(definitions: DefinitionStore) -> None:
    definitions.create("agent", OMITTED)
    definitions.save("agent", {**OMITTED, "tools": []})
    assert definitions.get("agent", "a-omit").document["tools"] == []
    definitions.save("agent", OMITTED)
    assert "tools" not in definitions.get("agent", "a-omit").document


def test_file_on_disk_has_no_null_filled_keys(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path)
    store.create("agent", Agent.model_validate({"id": "a", "name": "A"}))
    text = (tmp_path / "agents" / "a.yaml").read_text(encoding="utf-8")
    assert "limits" not in text
    assert "null" not in text
    assert "tools" not in text


def test_phase1_null_filled_file_is_read_as_is_not_normalized(tmp_path: Path) -> None:
    """Phase 1 null 채움 파일은 자동 정규화하지 않는다(메인 세션 결정). 있는 그대로 읽힌다."""
    folder = tmp_path / "agents"
    folder.mkdir()
    text = "id: old\nname: 옛 에이전트\nmodel: null\ntools: []\nlimits: null\n"
    (folder / "old.yaml").write_text(text, encoding="utf-8")
    store = FileDefinitionStore(tmp_path)
    doc = store.get("agent", "old").document
    assert doc == {"id": "old", "name": "옛 에이전트", "model": None, "tools": [], "limits": None}
    assert {"model", "tools", "limits"} <= store.get("agent", "old").model(Agent).model_fields_set
    assert (folder / "old.yaml").read_text(
        encoding="utf-8"
    ) == text  # 읽기만으로 파일을 바꾸지 않음


def test_sqlite_version_history_keeps_null_and_empty(tmp_path: Path) -> None:
    db = open_sqlite(tmp_path / "v.sqlite3")
    store = FileDefinitionStore(tmp_path / "ws", versions=db.versions)
    created = store.create("agent", EMPTY)
    db.close()
    again = open_sqlite(tmp_path / "v.sqlite3")
    snap = again.versions.get("agent", "a-empty", created.version_hash)
    assert snap is not None
    assert snap.content == EMPTY
    again.close()
