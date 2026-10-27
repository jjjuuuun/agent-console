"""목록 요약에 정의 범위(`project`)를 싣는다(design §UX-P.4, 5.2R.31).

기본 종류 graph·agent·resource는 `summary_fields`에 `project`가 있다. 값이 없으면(공용) 요약
`extra`에 키가 없다(지금과 같음). 저장소는 값의 뜻을 모른다.
"""

from __future__ import annotations

from typing import Any

from agent_console_store import (
    AGENT_KIND,
    GRAPH_KIND,
    RESOURCE_KIND,
    SCOPE_FIELD,
    SETTINGS_KIND,
    DefinitionStore,
    list_graph_summaries,
)


def _graph(gid: str, **extra: Any) -> dict[str, Any]:
    return {"id": gid, "name": gid, "nodes": [], "edges": [], **extra}


def _resource(rid: str, **extra: Any) -> dict[str, Any]:
    return {"id": rid, "type": "instruction", "name": rid, "config": {}, **extra}


def test_default_kinds_declare_scope_field() -> None:
    assert SCOPE_FIELD == "project"
    for kind in (GRAPH_KIND, AGENT_KIND, RESOURCE_KIND):
        assert SCOPE_FIELD in kind.summary_fields, kind.name
    assert RESOURCE_KIND.summary_fields[0] == "type"
    assert SCOPE_FIELD not in SETTINGS_KIND.summary_fields


def test_summaries_carry_project_only_when_set(definitions: DefinitionStore) -> None:
    definitions.create("agent", {"id": "a1", "name": "A1", "project": "app"})
    definitions.create("agent", {"id": "a2", "name": "A2"})
    definitions.create("resource", _resource("r1", project="app"))
    definitions.create("resource", _resource("r2"))
    definitions.create("graph", _graph("g1", project="app"))
    definitions.create("graph", _graph("g2"))

    agents = {s.id: s.extra for s in definitions.summaries("agent")}
    assert agents == {"a1": {"project": "app"}, "a2": {}}
    resources = {s.id: s.extra for s in definitions.summaries("resource")}
    assert resources == {
        "r1": {"type": "instruction", "project": "app"},
        "r2": {"type": "instruction"},
    }
    graphs = {s.id: s.extra for s in definitions.summaries("graph")}
    assert graphs == {"g1": {"project": "app"}, "g2": {}}


def test_graph_summary_model_has_project(definitions: DefinitionStore) -> None:
    definitions.create("graph", _graph("g1", project="app"))
    definitions.create("graph", _graph("g2"))
    by_id = {s.id: s for s in list_graph_summaries(definitions)}
    assert by_id["g1"].project == "app"
    assert by_id["g2"].project is None
    # 공용은 직렬화에서도 빠지지 않고 null로 내려간다(목록 계약 필드)
    assert by_id["g2"].model_dump(mode="json")["project"] is None


def test_summaries_carry_attributes_copy(definitions: DefinitionStore) -> None:
    """목록 요약에 원문 `attributes`를 싣는다(5.2R.64, 폴더 `ui.folder`·라벨 묶기용)."""
    attrs = {"ui": {"folder": "개발팀/백엔드", "icon": "bot"}, "team_tag": "x"}
    definitions.create("graph", _graph("g1", attributes=attrs))
    definitions.create("graph", _graph("g2"))
    definitions.create("resource", _resource("r1", attributes=attrs))
    definitions.create("agent", {"id": "a1", "name": "A1"})

    raw = {s.id: s for s in definitions.summaries("graph")}
    assert raw["g1"].attributes == attrs
    assert raw["g2"].attributes == {}
    raw["g1"].attributes["ui"]["folder"] = "바뀜"  # 복사본이라 저장소에 새지 않는다
    assert definitions.summaries("graph")[0].attributes == attrs
    assert definitions.summaries("resource")[0].attributes == attrs
    assert definitions.summaries("agent")[0].attributes == {}  # 없으면 빈 dict

    by_id = {s.id: s for s in list_graph_summaries(definitions)}
    assert by_id["g1"].attributes == attrs
    assert by_id["g1"].saved_at is not None
    assert by_id["g2"].model_dump(mode="json")["attributes"] == {}
