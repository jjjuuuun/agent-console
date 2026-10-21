"""layers_for·effective_settings: 4층 + 리소스 연결 첨부, 출처, 생략 = 상속, 병합 규칙, 경고."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    Graph,
    Resource,
    ResourceContentRef,
    ResourceTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_resources import (
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    SchemaResourceType,
    content_text,
    new_resource_types,
)
from agent_console_settings import Layer
from agent_console_teams import (
    AGENT_SETTINGS_FIELDS,
    TeamPlan,
    agent_layers,
    delegation_max_depth,
    effective_settings,
    layers_for,
    merge_rules,
    node_bundle,
    node_settings,
    resolve_settings,
    team_plan,
    user_settings,
)
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]


class MemoType(SchemaResourceType):
    """테스트 전용 리소스 종류(임의 이름): 본문을 `notes` 칸에 한 항목으로."""

    descriptor = ResourceTypeDescriptor(
        id="memo",
        title="메모",
        config_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        slot_key="title",
        contributes=["notes"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("notes", [f"{resource.id}:{content_text(content)}"])]


def _memo(rid: str, title: str) -> Resource:
    return Resource(
        id=rid,
        type="memo",
        name=rid,
        config={"title": title},
        content=ResourceContentRef(file="c.md"),
    )


def _plan(k: Kit, graph: Graph) -> TeamPlan:
    return team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)


def _team(k: Kit, team_settings: dict[str, Any] | None = None, **node_config: Any) -> Graph:
    nodes = [
        k.person(),
        k.worker("lead", who="pl", **node_config),
        k.material("guide", "node-memo"),
    ]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("r1", "attach", "guide", "lead"),
    ]
    return k.graph(nodes, edges, settings=team_settings)


WS = WorkspaceSettings.model_validate(
    {
        "agent_defaults": {
            "model": "m-common",
            "tools": ["Read"],
            "resources": [{"ref": "c-memo"}],
        },
        "settings_merge": {"/tools": "union"},
    }
)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_four_layers_with_provenance_and_omission_inherits(k: Kit) -> None:
    graph = _team(
        k,
        {"model": "m-team", "resources": [{"ref": "t-memo"}]},
        settings={"system_prompt": "노드 지침", "tools": ["Write"]},
    )
    agent = Agent.model_validate({"id": "pl", "name": "PL", "description": "설명", "backend": "bk"})
    plan = _plan(k, graph)
    layers = layers_for(plan, "lead", agent=agent, workspace=WS)
    assert [layer.id for layer in layers] == ["common", "team", "agent", "node"]
    # 에이전트 층은 지정한 설정 필드만(식별 필드·모델 기본값 없음)
    assert layers[2].value == {"backend": "bk"}

    eff = effective_settings(plan, "lead", agents={"pl": agent}, workspace=WS)
    assert eff.value.model == "m-team"
    assert eff.provenance["/model"] == "team"
    assert eff.value.backend == "bk"
    assert eff.provenance["/backend"] == "agent"
    assert eff.provenance["/system_prompt"] == "node"
    # 공통 규칙 /tools = union
    assert eff.value.tools == ["Read", "Write"]
    assert eff.provenance["/tools/0"] == "common"
    assert eff.provenance["/tools/1"] == "node"
    # 첨부: 공통 → 팀 구성 → 노드(리소스 연결) 순서, 원소별 출처
    assert [a.ref for a in eff.value.resources or []] == ["c-memo", "t-memo", "node-memo"]
    assert [eff.provenance[f"/resources/{i}"] for i in range(3)] == ["common", "team", "node"]
    assert [(i.id, i.label) for i in eff.layers] == [
        ("common", "공통"),
        ("team", "팀 구성"),
        ("agent", "에이전트"),
        ("node", "이 팀의 노드"),
    ]
    assert eff.inapplicable == []


def test_explicit_null_and_empty_list_are_set_values() -> None:
    k = Kit()
    graph = _team(k, settings={"model": None, "tools": []})
    eff = effective_settings(_plan(k, graph), "lead", workspace=WS)
    assert eff.value.model is None
    assert eff.provenance["/model"] == "node"
    assert eff.value.tools == ["Read"]  # union: 빈 목록은 아무것도 더하지 않는다
    graph2 = k.graph(
        _team(k).nodes, _team(k).edges, settings={"settings_merge": {"/tools": "replace"}}
    )
    graph2.nodes[1].config["settings"] = {"tools": []}
    eff2 = effective_settings(_plan(k, graph2), "lead", workspace=WS)
    assert eff2.value.tools == []  # 팀 구성 규칙이 공통 규칙을 덮어씀


def test_merge_rules_and_user_settings_layers() -> None:
    graph = Graph.model_validate(
        {
            "id": "g",
            "name": "g",
            "settings": {
                "settings_merge": {"/limits": "intersect"},
                "chat": {"reply_display": "merged"},
                "delegation": {"max_depth": 2},
            },
        }
    )
    assert merge_rules(WS, graph) == {"/tools": "union", "/limits": "intersect"}
    us = user_settings(WS, graph)
    assert us.value["chat"]["reply_display"] == "merged"
    assert us.source_of("/chat/reply_display") == "team"
    assert us.value["chat"]["busy_policy"] == "queue"
    assert us.source_of("/chat/busy_policy") == "defaults"
    assert delegation_max_depth(WS, graph) == 2
    assert delegation_max_depth(WS, None) is None
    # 기본값이 있는 묶음도 지정하지 않으면 공통 층 값이 아니다
    assert us.layers_under("/chat") == ["defaults", "team"]


def test_legacy_default_backend_is_read_as_common_backend() -> None:
    ws = WorkspaceSettings.model_validate({"default_backend": "old"})
    assert agent_layers(None, ws)[0].value == {"backend": "old"}
    ws2 = WorkspaceSettings.model_validate(
        {"default_backend": "old", "agent_defaults": {"backend": "new"}}
    )
    assert agent_layers(None, ws2)[0].value == {"backend": "new"}


def test_widening_and_invalid_value_warnings() -> None:
    k = Kit()
    ws = WorkspaceSettings.model_validate({"agent_defaults": {"limits": {"directories": ["/w"]}}})
    graph = _team(k, settings={"limits": {"directories": ["/w", "/x"]}, "session": "bogus"})
    eff = effective_settings(_plan(k, graph), "lead", workspace=ws)
    codes = {w.code: w for w in eff.warnings}
    assert codes["settings.widened"].path == "/limits/directories"
    assert codes["settings.widened"].details["layer"] == "node"
    assert codes["settings.invalid_value"].path == "/session"
    assert "bogus" not in codes["settings.invalid_value"].message
    assert eff.value.session is None
    assert eff.value.limits is not None
    assert eff.value.limits.directories == ["/w", "/x"]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_inapplicable_fields_for_delegated_member(k: Kit) -> None:
    nodes = [k.worker("lead"), k.worker("mate")]
    edges = [k.edge("d1", "invoke", "lead", "mate")]
    plan = _plan(k, k.graph(nodes, edges))
    mate = effective_settings(plan, "mate", strategies=k.strategy_map)
    assert "/backend" in mate.inapplicable
    assert "/model" not in mate.inapplicable
    assert len(mate.inapplicable) == len(AGENT_SETTINGS_FIELDS) - 3
    assert effective_settings(plan, "lead", strategies=k.strategy_map).inapplicable == []


def test_bundle_from_effective_settings_keeps_layer_order_and_sources() -> None:
    k = Kit()
    types = new_resource_types()
    types.register("memo", MemoType())
    resources = InMemoryResources(
        [_memo("c-memo", "공통"), _memo("t-memo", "팀"), _memo("node-memo", "노드")],
        contents={"c-memo": "C", "t-memo": "T", "node-memo": "N"},
    )
    graph = _team(k, {"resources": [{"ref": "t-memo"}]})
    ns = node_settings(
        _plan(k, graph), "lead", workspace=WS, resource_types=types, resources=resources
    )
    composed = node_bundle(ns, resource_types=types, resources=resources, accepted_slots=["x"])
    assert composed.bundle.slots["notes"] == ["c-memo:C", "t-memo:T", "node-memo:N"]
    assert [(s.ref, s.layer) for s in composed.bundle.sources["notes"]] == [
        ("c-memo", "common"),
        ("t-memo", "team"),
        ("node-memo", "node"),
    ]
    assert [i.code for i in composed.issues] == ["resource.slot_unsupported"]


def test_attachment_replace_by_slot_key_and_remove_across_layers() -> None:
    k = Kit()
    types = new_resource_types()
    types.register("memo", MemoType())
    resources = InMemoryResources(
        [_memo("c-memo", "공통"), _memo("t-memo", "팀"), _memo("node-memo", "팀")],
        contents={"c-memo": "C", "t-memo": "T", "node-memo": "N"},
    )
    nodes = [k.person(), k.worker("lead", who="pl"), k.material("guide", "node-memo")]
    edges = [k.edge("r1", "attach", "guide", "lead", mode="replace")]
    graph = k.graph(nodes, edges, settings={"resources": [{"ref": "t-memo"}]})
    agent = Agent.model_validate(
        {"id": "pl", "name": "PL", "resources": [{"ref": "c-memo", "mode": "remove"}]}
    )
    ns = node_settings(
        _plan(k, graph),
        "lead",
        agents={"pl": agent},
        workspace=WS,
        resource_types=types,
        resources=resources,
    )
    # 공통 c-memo는 에이전트 층이 빼고, 팀 t-memo는 같은 슬롯 키(title=팀)의 노드 첨부가 바꾼다
    assert [(p.attachment.ref, p.layer) for p in ns.attachments] == [("node-memo", "node")]


def test_layers_are_data_extra_layer_can_be_inserted() -> None:
    k = Kit()
    graph = _team(k)
    layers = layers_for(_plan(k, graph), "lead", agent=None, workspace=WS)
    layers.insert(2, Layer("project", "프로젝트", {"model": "m-project"}))
    ns = resolve_settings(layers, rules=merge_rules(WS, graph))
    assert ns.effective.value.model == "m-project"
    assert ns.effective.provenance["/model"] == "project"
