"""compose_bundle: 층 순서·add/replace/remove·종류별 combine·출처·이슈."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    AgentSettings,
    Issue,
    Resource,
    ResourceAttachment,
    ResourceContentRef,
    ResourceTypeDescriptor,
)
from agent_console_registry import Registry
from agent_console_resources import (
    ATTACHMENT_STRATEGY,
    AttachmentLayer,
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    ResourceType,
    SchemaResourceType,
    attachment_slot_key,
    build_bundle,
    compose_bundle,
    content_text,
    new_resource_types,
    placed_from_resolved,
    resolve_attachments,
    resource_strategies,
    unsupported_slots,
)
from agent_console_settings import Layer, resolve_layers


# ---------------------------------------------------------------- 테스트 전용 종류(임의 이름)
class NoteType(SchemaResourceType):
    """본문을 `notes` 칸에 한 항목으로. 슬롯 키 = config `slot`."""

    descriptor = ResourceTypeDescriptor(
        id="note",
        title="메모",
        config_schema={
            "type": "object",
            "properties": {"slot": {"type": "string"}, "first": {"type": "boolean"}},
            "additionalProperties": False,
        },
        slot_key="slot",
        contributes=["notes"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        combine = "prepend" if resource.config.get("first") else None
        return [Contribution("notes", [f"{resource.id}:{content_text(content)}"], combine)]


class ServerMapType(SchemaResourceType):
    """객체 칸(`servers`)에 키별 병합(`merge`)으로 기여한다."""

    descriptor = ResourceTypeDescriptor(
        id="server-map", title="서버", combine="merge", contributes=["servers"]
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("servers", {resource.id: dict(resource.config)})]


class BrokenType(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(id="broken", title="깨짐", contributes=["notes"])

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        raise RuntimeError("boom")


def _types(*items: ResourceType) -> Registry[ResourceType]:
    reg = new_resource_types()
    for item in items or (NoteType(), ServerMapType(), BrokenType()):
        reg.register(item.descriptor.id, item)
    return reg


def _note(rid: str, **config: Any) -> Resource:
    return Resource(
        id=rid, type="note", name=rid, config=config, content=ResourceContentRef(file="content.md")
    )


RESOURCES = InMemoryResources(
    [
        _note("team-md", slot="claude"),
        _note("node-md"),
        _note("agent-md", slot="claude"),
        _note("lead", first=True),
        Resource(id="s1", type="server-map", name="s1", config={"cmd": "a"}),
        Resource(id="s2", type="server-map", name="s2", config={"cmd": "b"}),
        Resource(id="bad", type="broken", name="bad"),
        Resource(id="ghost", type="not-installed", name="ghost"),
        Resource(id="wrong", type="note", name="wrong", config={"slot": 3}),
    ],
    contents={"team-md": "T", "node-md": "N", "agent-md": "A", "lead": "L"},
)


def _att(ref: str, mode: str = "add", **extra: Any) -> ResourceAttachment:
    return ResourceAttachment.model_validate({"ref": ref, "mode": mode, **extra})


def _codes(issues: tuple[Issue, ...] | list[Issue]) -> list[str]:
    return [i.code for i in issues]


# ---------------------------------------------------------------- 층 순서
def test_team_then_node_append_in_layer_order_with_sources() -> None:
    result = compose_bundle(
        [
            AttachmentLayer("common", None, "공통"),
            AttachmentLayer("team", [_att("team-md")], "팀 구성"),
            AttachmentLayer("agent", [], "에이전트"),
            AttachmentLayer("node", [_att("node-md")], "이 팀의 노드"),
        ],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots == {"notes": ["team-md:T", "node-md:N"]}
    assert [(s.ref, s.layer) for s in result.bundle.sources["notes"]] == [
        ("team-md", "team"),
        ("node-md", "node"),
    ]
    assert [(p.attachment.ref, p.layer) for p in result.attachments] == [
        ("team-md", "team"),
        ("node-md", "node"),
    ]
    assert result.issues == ()


def test_per_contribution_combine_prepend() -> None:
    result = compose_bundle(
        [AttachmentLayer("team", [_att("team-md")]), AttachmentLayer("node", [_att("lead")])],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["lead:L", "team-md:T"]


def test_type_combine_merge_for_object_slot() -> None:
    result = compose_bundle(
        [AttachmentLayer("a", [_att("s1")]), AttachmentLayer("b", [_att("s2")])],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["servers"] == {"s1": {"cmd": "a"}, "s2": {"cmd": "b"}}


# ---------------------------------------------------------------- remove · replace
def test_remove_drops_upper_layer_attachment() -> None:
    result = compose_bundle(
        [
            AttachmentLayer("team", [_att("team-md"), _att("node-md")]),
            AttachmentLayer("node", [_att("team-md", "remove")]),
        ],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["node-md:N"]
    assert [p.attachment.ref for p in result.attachments] == ["node-md"]


def test_replace_by_slot_key_keeps_position() -> None:
    result = compose_bundle(
        [
            AttachmentLayer("team", [_att("team-md"), _att("node-md")]),
            AttachmentLayer("node", [_att("agent-md", "replace")]),  # 같은 slot=claude
        ],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["agent-md:A", "node-md:N"]
    assert [(s.ref, s.layer, s.mode) for s in result.bundle.sources["notes"]] == [
        ("agent-md", "node", "replace"),
        ("node-md", "team", "add"),
    ]


def test_replace_same_ref_with_config_override() -> None:
    result = compose_bundle(
        [
            AttachmentLayer("team", [_att("team-md")]),
            AttachmentLayer("node", [_att("team-md", "replace", config_override={"first": True})]),
        ],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["team-md:T"]
    assert result.attachments[0].attachment.config_override == {"first": True}


def test_unmatched_replace_and_remove_are_info() -> None:
    result = compose_bundle(
        [AttachmentLayer("node", [_att("node-md", "replace"), _att("lead", "remove")])],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["node-md:N"]
    infos = {i.code: i for i in result.issues}
    assert infos["resource.replace_unmatched"].severity == "info"
    assert infos["resource.remove_unmatched"].severity == "info"


def test_replace_without_lookup_matches_ref_only() -> None:
    placed, _ = resolve_attachments(
        [
            AttachmentLayer("t", [_att("team-md")]),
            AttachmentLayer("n", [_att("agent-md", "replace")]),
        ]
    )
    assert [p.attachment.ref for p in placed] == ["team-md", "agent-md"]


# ---------------------------------------------------------------- 문제 보고
def test_missing_resource_unknown_type_invalid_config_and_broken_type() -> None:
    result = compose_bundle(
        [
            AttachmentLayer(
                "team",
                [_att("nope"), _att("ghost"), _att("wrong"), _att("bad"), _att("node-md")],
            )
        ],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots == {"notes": ["node-md:N"]}
    codes = _codes(result.issues)
    assert "resource.not_found" in codes
    assert "resource.unknown_type" in codes
    assert "resource.invalid_config" in codes
    assert "resource.type_failed" in codes
    invalid = next(i for i in result.issues if i.code == "resource.invalid_config")
    assert invalid.path == "/slot"
    assert invalid.details["layer"] == "team"


def test_duplicate_add_contributes_once() -> None:
    result = compose_bundle(
        [AttachmentLayer("team", [_att("node-md")]), AttachmentLayer("node", [_att("node-md")])],
        types=_types(),
        resources=RESOURCES,
    )
    assert result.bundle.slots["notes"] == ["node-md:N"]
    assert "resource.duplicate" in _codes(result.issues)


def test_content_unreadable_warns() -> None:
    lookup = InMemoryResources([_note("x")], contents={})
    result = compose_bundle([AttachmentLayer("t", [_att("x")])], types=_types(), resources=lookup)
    assert "resource.content_unreadable" in _codes(result.issues)
    assert result.bundle.slots["notes"] == ["x:None"]


def test_unsupported_slots_warn_but_stay_in_bundle() -> None:
    result = compose_bundle(
        [AttachmentLayer("t", [_att("node-md"), _att("s1")])],
        types=_types(),
        resources=RESOURCES,
        accepted_slots=["notes"],
    )
    assert set(result.bundle.slots) == {"notes", "servers"}
    warn = [i for i in result.issues if i.code == "resource.slot_unsupported"]
    assert len(warn) == 1
    assert warn[0].details == {"slot": "servers", "resources": ["s1"]}
    assert unsupported_slots(result.bundle, ["notes"]) == ["servers"]


def test_unknown_combine_falls_back_to_append() -> None:
    class Odd(NoteType):
        descriptor = NoteType.descriptor.model_copy(update={"id": "odd", "combine": "nope"})

    lookup = InMemoryResources(
        [
            Resource(id="o1", type="odd", name="o1", content=ResourceContentRef(file="c")),
            Resource(id="o2", type="odd", name="o2", content=ResourceContentRef(file="c")),
        ],
        contents={"o1": "1", "o2": "2"},
    )
    result = compose_bundle(
        [AttachmentLayer("t", [_att("o1"), _att("o2")])], types=_types(Odd()), resources=lookup
    )
    assert result.bundle.slots["notes"] == ["o1:1", "o2:2"]
    assert "resource.merge.unknown_strategy" in _codes(result.issues)


def test_duplicate_layer_ids_raise() -> None:
    with pytest.raises(ValueError, match="겹칩니다"):
        compose_bundle(
            [AttachmentLayer("a", []), AttachmentLayer("a", [])],
            types=_types(),
            resources=RESOURCES,
        )


# ---------------------------------------------------------------- 설정 층 병합과 연결
def test_contract_x_merge_uses_keyed_attachments_from_settings_resolution() -> None:
    schema = AgentSettings.model_json_schema()
    table = resource_strategies(slot_key_of=attachment_slot_key(_types(), RESOURCES))
    layers = [
        Layer("common", value={"model": "m", "resources": [{"ref": "team-md"}]}),
        Layer(
            "node",
            value={"resources": [{"ref": "agent-md", "mode": "replace"}, {"ref": "node-md"}]},
        ),
    ]
    resolved = resolve_layers(layers, schema=schema, strategies=table)
    assert not resolved.issues
    placed = placed_from_resolved(resolved)
    assert [(p.attachment.ref, p.layer) for p in placed] == [
        ("agent-md", "node"),
        ("node-md", "node"),
    ]
    bundle = build_bundle(placed, types=_types(), resources=RESOURCES, strategies=table)
    assert bundle.bundle.slots["notes"] == ["agent-md:A", "node-md:N"]
    assert ATTACHMENT_STRATEGY == "keyed_attachments"
