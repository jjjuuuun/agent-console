"""2R.12: 받지 않는 칸 경고가 팀 검증(`validate_team(resource_types=)`)과 묶음 미리보기에 이유
(`BackendCapabilities.slot_notes`)와 함께 나온다. 칸·종류·백엔드 이름은 테스트 데이터다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agent_console_contracts import (
    BackendCapabilities,
    Graph,
    KnownIssueCodes,
    Resource,
    ResourceTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_resources import (
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    SchemaResourceType,
    new_resource_types,
)
from agent_console_teams import bundle_preview, team_plan, validate_team
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]
NOTE = "설치자가 꺼 둠"


class _Cmd(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(
        id="cmd-x", title="cmd", config_schema={"type": "object"}, contributes=["run-x"]
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("run-x", [{"command": "c"}])]


@dataclass
class _Setup:
    graph: Graph
    types: Any
    resources: InMemoryResources
    backends: dict[str, BackendCapabilities]
    workspace: WorkspaceSettings


def _setup(k: Kit, slots: list[str]) -> _Setup:
    types = new_resource_types()
    types.register("cmd-x", _Cmd())
    resources = InMemoryResources([Resource(id="c1", type="cmd-x", name="c1")])
    attach = {"resources": [{"ref": "c1"}]}
    graph = k.graph(
        [k.person(), k.worker("lead", settings=attach)], [k.edge("in", "entry", "me", "lead")]
    )
    return _Setup(
        graph=graph,
        types=types,
        resources=resources,
        backends={"b1": BackendCapabilities(resource_slots=slots, slot_notes={"run-x": NOTE})},
        workspace=WorkspaceSettings.model_validate({"agent_defaults": {"backend": "b1"}}),
    )


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_validate_team_warns_unsupported_slot_with_reason(k: Kit) -> None:
    s = _setup(k, ["other"])
    issues = validate_team(
        s.graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        workspace=s.workspace,
        backends=s.backends,
        resources=s.resources,
        resource_types=s.types,
        graph_checks=False,
    )
    found = [i for i in issues if i.code == KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED]
    assert len(found) == 1
    assert found[0].node_id == "lead"
    assert found[0].severity == "warning"
    assert found[0].details["reason"] == NOTE
    assert found[0].details["backend"] == "b1"
    assert found[0].details["slot"] == "run-x"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_validate_team_quiet_when_slot_accepted_or_types_missing(k: Kit) -> None:
    s = _setup(k, ["run-x"])
    accepted = validate_team(
        s.graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        workspace=s.workspace,
        backends=s.backends,
        resources=s.resources,
        resource_types=s.types,
        graph_checks=False,
    )
    assert all(i.code != KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED for i in accepted)
    off = _setup(k, ["other"])
    no_types = validate_team(
        off.graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        workspace=off.workspace,
        backends=off.backends,
        resources=off.resources,
        graph_checks=False,
    )
    assert all(i.code != KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED for i in no_types)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_bundle_preview_carries_reason(k: Kit) -> None:
    s = _setup(k, ["other"])
    plan = team_plan(s.graph, node_types=k.node_types, edge_types=k.edge_types)
    preview = bundle_preview(
        plan,
        "lead",
        resource_types=s.types,
        resources=s.resources,
        backends=s.backends,
        workspace=s.workspace,
    )
    (warning,) = [
        w for w in preview.warnings if w.code == KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED
    ]
    assert warning.details["reason"] == NOTE
    assert NOTE in warning.message
