"""4R.9: 묶음 미리보기 백엔드 선택 훅(`PreviewNotes.preview_notes`)과 카탈로그 연결.

칸·종류·백엔드·이슈 코드 이름은 테스트 데이터다(이 패키지는 어느 것도 모른다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_contracts import (
    AgentSettings,
    BackendCapabilities,
    BackendDescriptor,
    Issue,
    Resource,
    ResourceBundle,
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
from agent_console_teams import (
    PreviewNotes,
    TeamIssueCodes,
    bundle_preview,
    catalog_from_registries,
    team_plan,
)
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]


class _Cmd(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(
        id="cmd-x", title="cmd", config_schema={"type": "object"}, contributes=["run-x"]
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("run-x", [{"command": "c"}])]


@dataclass
class _Notes:
    seen: list[tuple[AgentSettings, ResourceBundle]] = field(default_factory=list)
    fail: bool = False

    def preview_notes(self, effective: AgentSettings, bundle: ResourceBundle) -> list[Issue]:
        if self.fail:
            raise RuntimeError("boom")
        self.seen.append((effective, bundle))
        if effective.observe is None or effective.observe.hook_probe is not True:
            return []
        return [Issue(severity="info", code="x.note", message="켜짐")]


def _preview(k: Kit, notes: dict[str, Any] | None, *, observe: dict[str, Any] | None) -> Any:
    types = new_resource_types()
    types.register("cmd-x", _Cmd())
    resources = InMemoryResources([Resource(id="c1", type="cmd-x", name="c1")])
    settings: dict[str, Any] = {"resources": [{"ref": "c1"}]}
    if observe is not None:
        settings["observe"] = observe
    graph = k.graph(
        [k.person(), k.worker("lead", settings=settings)], [k.edge("in", "entry", "me", "lead")]
    )
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    return bundle_preview(
        plan,
        "lead",
        resource_types=types,
        resources=resources,
        backends={"b1": BackendCapabilities(resource_slots=["run-x"])},
        workspace=WorkspaceSettings.model_validate({"agent_defaults": {"backend": "b1"}}),
        notes=notes,
    )


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_notes_hook_adds_issue_with_effective_and_bundle(k: Kit) -> None:
    hook = _Notes()
    assert isinstance(hook, PreviewNotes)
    preview = _preview(k, {"b1": hook}, observe={"hook_probe": True})
    assert [w.code for w in preview.warnings] == ["x.note"]
    effective, bundle = hook.seen[0]
    assert effective.backend == "b1"
    assert bundle.slots["run-x"] == [{"command": "c"}]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_notes_absent_or_off_or_other_backend(k: Kit) -> None:
    assert _preview(k, None, observe={"hook_probe": True}).warnings == []
    assert _preview(k, {"b1": _Notes()}, observe=None).warnings == []
    assert _preview(k, {"b2": _Notes()}, observe={"hook_probe": True}).warnings == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_notes_hook_failure_becomes_warning(k: Kit) -> None:
    preview = _preview(k, {"b1": _Notes(fail=True)}, observe={"hook_probe": True})
    (warning,) = preview.warnings
    assert warning.code == TeamIssueCodes.VALIDATOR_FAILED
    assert warning.details == {"backend": "b1"}


def test_catalog_collects_preview_notes_hooks() -> None:
    @dataclass
    class _Entry:
        key: str
        item: Any

    class _Plain:
        descriptor = BackendDescriptor(id="plain", title="p")

    class _WithNotes(_Notes):
        descriptor = BackendDescriptor(id="noted", title="n")

    class _Registry:
        def list(self, *, all_versions: bool) -> list[_Entry]:
            return [_Entry("plain", _Plain()), _Entry("noted", _WithNotes())]

    class _Registries:
        backends = _Registry()

    catalog = catalog_from_registries(_Registries())
    assert set(catalog.backends) == {"plain", "noted"}
    assert set(catalog.preview_notes) == {"noted"}
