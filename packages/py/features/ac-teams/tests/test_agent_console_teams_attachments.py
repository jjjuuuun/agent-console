"""첨부 위치 찾기·덮어쓰기 검사·`x-secret` 가리기(1R.37 후속, 임의 이름 노드·연결 종류)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    AgentDefaults,
    Issue,
    Resource,
    ResourceAttachment,
    ResourceTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_registry import Registry
from agent_console_resources import (
    SECRET_SCHEMA_KEY,
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    ResourceType,
    SchemaResourceType,
    new_resource_types,
)
from agent_console_teams import (
    agent_attachments,
    attachment_issues,
    graph_attachments,
    mask_effective_secrets,
    mask_node_settings,
    node_bundle,
    node_settings,
    settings_attachments,
    team_plan,
)
from agent_console_teams.testing import KITS, Kit

PLAIN = "plain-value-123"


class VaultType(SchemaResourceType):
    """예제 종류: `key`는 비밀(`x-secret`), 평문이면 일반 규칙이 error(`resource.plain_secret`)."""

    descriptor = ResourceTypeDescriptor(
        id="vault",
        title="금고",
        config_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", SECRET_SCHEMA_KEY: True},
                "label": {"type": "string"},
            },
        },
        contributes=["notes"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("notes", f"{resource.id}:{resource.config.get('key')}")]


class LooseVaultType(VaultType):
    """평문 검사가 없는 종류(`validate`를 직접 구현한 플러그인 등) — 가리기만이 안전망."""

    descriptor = VaultType.descriptor.model_copy(update={"id": "loose"})

    def validate(self, resource: Resource) -> list[Issue]:
        return []


def _types() -> Registry[ResourceType]:
    types = new_resource_types()
    types.register("vault", VaultType())
    types.register("loose", LooseVaultType())
    return types


def _resources(key: str = "secret://K") -> InMemoryResources:
    return InMemoryResources([Resource(id="v", type="vault", name="v", config={"key": key})])


def _att(**override: Any) -> dict[str, Any]:
    return {"ref": "v", "config_override": override} if override else {"ref": "v"}


def test_agent_and_settings_override_paths() -> None:
    agent = Agent.model_validate(
        {"id": "a", "name": "a", "resources": [_att(), _att(key=PLAIN), _att(label="ok")]}
    )
    issues = attachment_issues(agent_attachments(agent), types=_types(), resources=_resources())
    assert [(i.severity, i.code, i.path) for i in issues] == [
        ("error", "resource.plain_secret", "/resources/1/config_override/key")
    ]
    assert all(PLAIN not in i.model_dump_json() for i in issues)
    ws = WorkspaceSettings(
        agent_defaults=AgentDefaults(resources=[ResourceAttachment.model_validate(_att(key=PLAIN))])
    )
    [issue] = attachment_issues(settings_attachments(ws), types=_types(), resources=_resources())
    assert issue.path == "/agent_defaults/resources/0/config_override/key"


def test_resource_own_problem_is_not_blamed_on_attachment() -> None:
    """리소스 자체가(이전 데이터) 평문이어도 덮어쓰지 않은 키면 첨부 탓이 아니다."""
    legacy = _resources(key=PLAIN)
    agent = Agent.model_validate({"id": "a", "name": "a", "resources": [_att(label="x")]})
    assert attachment_issues(agent_attachments(agent), types=_types(), resources=legacy) == []
    agent = Agent.model_validate({"id": "a", "name": "a", "resources": [_att(key=PLAIN)]})
    [issue] = attachment_issues(agent_attachments(agent), types=_types(), resources=legacy)
    assert issue.path == "/resources/0/config_override/key"


def test_missing_resource_is_warning_at_ref() -> None:
    agent = Agent.model_validate(
        {"id": "a", "name": "a", "resources": [{"ref": "gone", "config_override": {"k": 1}}]}
    )
    [issue] = attachment_issues(
        agent_attachments(agent), types=_types(), resources=InMemoryResources([])
    )
    assert (issue.severity, issue.code, issue.path) == (
        "warning",
        "resource.not_found",
        "/resources/0/ref",
    )


@pytest.mark.parametrize("k", KITS)
def test_graph_team_node_and_edge_paths(k: Kit) -> None:
    nodes = [
        k.person(),
        k.worker("lead", settings={"resources": [_att(key=PLAIN)]}),
        k.material("box", "v"),
    ]
    edges = [
        k.edge("e1", "entry", "me", "lead"),
        k.edge("r1", "attach", "box", "lead", config_override={"key": PLAIN}),
    ]
    graph = k.graph(nodes, edges, settings={"resources": [_att(key=PLAIN)]})
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    issues = attachment_issues(
        graph_attachments(graph, plan=plan), types=_types(), resources=_resources()
    )
    assert sorted(i.path or "" for i in issues) == [
        "/edges/1/config/config_override/key",
        "/nodes/1/config/settings/resources/0/config_override/key",
        "/settings/resources/0/config_override/key",
    ]
    # 계획이 없으면 연결은 검사하지 않는다(해석할 수 없는 그래프)
    assert (
        len(attachment_issues(graph_attachments(graph), types=_types(), resources=_resources()))
        == 2
    )


def test_masking_effective_settings_and_bundle() -> None:
    """이전에 저장된 평문(검사 전 데이터)은 유효 설정·묶음 미리보기에서 가린다."""
    k = Kit()
    types = _types()
    legacy = InMemoryResources(
        [Resource(id="v", type="loose", name="v", config={"key": PLAIN, "label": "L"})]
    )
    nodes = [k.person(), k.worker("lead", settings={"resources": [_att(key="also-" + PLAIN)]})]
    graph = k.graph(nodes, [k.edge("e1", "entry", "me", "lead")])
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    ns = node_settings(plan, "lead", resource_types=types, resources=legacy)
    shown = mask_effective_secrets(ns.effective, types=types, resources=legacy)
    assert PLAIN not in shown.model_dump_json()
    assert ns.effective.value.resources is not None  # 원본은 그대로
    raw = node_bundle(ns, resource_types=types, resources=legacy)
    assert PLAIN in raw.bundle.model_dump_json()  # 가리지 않으면 새어 나간다
    masked, lookup = mask_node_settings(ns, types=types, resources=legacy)
    bundle = node_bundle(masked, resource_types=types, resources=lookup)
    assert PLAIN not in bundle.bundle.model_dump_json()
    assert bundle.bundle.slots["notes"] == "v:***"
    found = lookup.get_resource("v")
    assert found is not None
    assert found.config["label"] == "L"
    ref_only = _resources()
    clean = node_settings(
        team_plan(
            k.graph([k.person(), k.worker("lead", settings={"resources": [_att()]})], []),
            node_types=k.node_types,
            edge_types=k.edge_types,
        ),
        "lead",
        resource_types=types,
        resources=ref_only,
    )
    masked, lookup = mask_node_settings(clean, types=types, resources=ref_only)
    out = node_bundle(masked, resource_types=types, resources=lookup)
    assert out.bundle.slots["notes"] == "v:secret://K"  # 참조는 그대로
