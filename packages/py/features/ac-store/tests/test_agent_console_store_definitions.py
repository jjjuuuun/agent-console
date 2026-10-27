"""DefinitionStore 공통 스위트: 파일(+SQLite 이력), 파일(메모리 이력), 인메모리에서 모두 통과."""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    Agent,
    DefinitionModel,
    Graph,
    VersionConflictDetails,
    WorkspaceSettings,
)
from agent_console_store import (
    AlreadyExists,
    DefinitionKind,
    DefinitionStore,
    InvalidIdentifier,
    NotFound,
    VersionConflict,
    VersionRequired,
    list_graph_summaries,
    to_versioned_graph,
)


def test_create_get_roundtrip_preserves_unknown_fields(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    doc = make_graph(custom_top={"a": [1, 2]}, attributes={"owner": "kim"})
    created = definitions.create("graph", doc)
    got = definitions.get("graph", "g1")
    assert got.version_hash == created.version_hash
    assert got.document["custom_top"] == {"a": [1, 2]}  # 모르는 최상위 필드 보존
    assert got.document["attributes"] == {"owner": "kim"}
    assert got.model(Graph).id == "g1"


def test_create_duplicate_raises(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    definitions.create("graph", make_graph())
    with pytest.raises(AlreadyExists):
        definitions.create("graph", make_graph())


def test_get_missing_raises(definitions: DefinitionStore) -> None:
    with pytest.raises(NotFound):
        definitions.get("graph", "nope")
    with pytest.raises(NotFound):
        definitions.get("unknown-kind", "x")


def test_invalid_id_rejected(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    with pytest.raises(InvalidIdentifier):
        definitions.get("graph", "../etc/passwd")
    for bad in ("a\n", "a\r", "a\t", "a "):
        with pytest.raises(InvalidIdentifier):
            definitions.get("graph", bad)
        with pytest.raises(InvalidIdentifier):
            definitions.delete("graph", bad)


def test_invalid_id_in_document_rejected(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    with pytest.raises(ValidationError):
        definitions.create("graph", make_graph(id="bad/id"))


def test_singleton_rejects_other_ids(definitions: DefinitionStore) -> None:
    definitions.save("settings", {})
    with pytest.raises(NotFound):
        definitions.get("settings", "other")
    with pytest.raises(NotFound):
        definitions.delete("settings", "other")


def test_save_requires_if_match_for_graph(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    definitions.create("graph", make_graph())
    with pytest.raises(VersionRequired):
        definitions.save("graph", make_graph(nodes=3))


def test_save_with_stale_version_raises_conflict_with_details(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    first = definitions.create("graph", make_graph(nodes=2))
    second = definitions.save(
        "graph", make_graph(nodes=3), expected_version=first.version_hash, message="3개로"
    )
    assert second.version_hash != first.version_hash
    with pytest.raises(VersionConflict) as info:
        definitions.save("graph", make_graph(nodes=4), expected_version=first.version_hash)
    details = info.value.details
    assert isinstance(details, VersionConflictDetails)
    assert details.current_version_hash == second.version_hash
    assert details.saved_at == second.saved_at
    assert (details.node_count, details.edge_count) == (3, 1)
    assert info.value.code == "version_conflict"
    # 충돌한 저장은 반영되지 않는다
    assert definitions.get("graph", "g1").version_hash == second.version_hash


def test_save_missing_graph_raises_not_found(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    with pytest.raises(NotFound):
        definitions.save("graph", make_graph(), expected_version="abc")


def test_agent_save_needs_no_if_match(definitions: DefinitionStore) -> None:
    definitions.create("agent", {"id": "a1", "name": "에이전트", "attributes": {"x": 1}})
    saved = definitions.save("agent", {"id": "a1", "name": "이름 변경"})
    assert saved.model(Agent).name == "이름 변경"


def test_versions_list_and_get_by_hash(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    v1 = definitions.create("graph", make_graph(nodes=2), message="처음")
    v2 = definitions.save("graph", make_graph(nodes=3), expected_version=v1.version_hash)
    versions = definitions.list_versions("graph", "g1")
    assert [v.version_hash for v in versions] == [v2.version_hash, v1.version_hash]  # 최신순
    assert all(v.content is None for v in versions)  # 목록은 본문 없음
    assert versions[1].message == "처음"
    old = definitions.get_version("graph", "g1", v1.version_hash)
    assert old.content is not None
    assert len(old.content["nodes"]) == 2
    with pytest.raises(NotFound):
        definitions.get_version("graph", "g1", "deadbeef")


def test_version_history_survives_delete(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    v1 = definitions.create("graph", make_graph())
    definitions.delete("graph", "g1")
    with pytest.raises(NotFound):
        definitions.get("graph", "g1")
    with pytest.raises(NotFound):
        definitions.delete("graph", "g1")
    assert definitions.get_version("graph", "g1", v1.version_hash).content is not None


def test_graph_summaries_have_counts_and_saved_at(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    definitions.create("graph", make_graph("b", nodes=3, labels=["x"]))
    saved = definitions.create("graph", make_graph("a", nodes=1))
    summaries = list_graph_summaries(definitions)
    assert [s.id for s in summaries] == ["a", "b"]
    a, b = summaries
    assert (a.node_count, a.edge_count) == (1, 0)
    assert (b.node_count, b.edge_count, b.labels) == (3, 1, ["x"])
    assert a.version_hash == saved.version_hash
    assert a.saved_at == saved.saved_at
    assert definitions.list_ids("graph") == ["a", "b"]


def test_versioned_graph_helper(
    definitions: DefinitionStore, make_graph: Callable[..., dict[str, Any]]
) -> None:
    created = definitions.create("graph", make_graph())
    vg = to_versioned_graph(definitions.get("graph", "g1"))
    assert vg.version_hash == created.version_hash
    assert vg.graph.name == "그래프 g1"


def test_settings_singleton_upserts(definitions: DefinitionStore) -> None:
    with pytest.raises(NotFound):
        definitions.get("settings", "settings")
    definitions.save("settings", {"default_entry": "main", "console": {"command_prefix": ">"}})
    got = definitions.get("settings", "settings").model(WorkspaceSettings)
    # 2R.20에서 계약에서 지운 키도 모르는 키로 보존된다.
    assert got.model_extra == {"default_entry": "main", "console": {"command_prefix": ">"}}


def test_custom_hash_function_is_injected(make_graph: Callable[..., dict[str, Any]]) -> None:
    from agent_console_store import InMemoryDefinitionStore

    store = InMemoryDefinitionStore(hash_fn=lambda doc: f"h{len(doc['nodes'])}")
    created = store.create("graph", make_graph(nodes=2))
    assert created.version_hash == "h2"
    # 종류별 hash_fn이 기본값보다 우선한다
    kind = DefinitionKind("graph", "graphs", Graph, require_version=True, hash_fn=lambda d: "fixed")
    assert InMemoryDefinitionStore([kind]).create("graph", make_graph()).version_hash == "fixed"


class Note(DefinitionModel):
    """테스트용 새 종류. 저장소 코드는 이 종류를 모른다."""

    id: str
    name: str = ""


def test_new_kind_registers_without_code_change(definitions: DefinitionStore) -> None:
    kind = DefinitionKind("note", "notes", Note)
    definitions.register_kind(kind)
    definitions.create("note", {"id": "p1", "name": "기본", "extra": True})
    stored = definitions.get("note", "p1")
    assert stored.document["extra"] is True
    assert definitions.list_ids("note") == ["p1"]
    assert "note" in definitions.kinds()
