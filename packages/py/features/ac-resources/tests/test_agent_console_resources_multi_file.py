"""2R.12: 여러 파일 본문 읽기(`FileContentLookup`), 대체 칸(`Contribution.fallback`), 칸 설명
(`slot_notes`). 종류·칸 이름은 테스트 데이터다(코드에 없음을 보이려고 일부러 지어낸 이름)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import (
    Resource,
    ResourceAttachment,
    ResourceContentSpec,
    ResourceTypeDescriptor,
)
from agent_console_resources import (
    SLOT_FALLBACK,
    SLOT_UNSUPPORTED,
    AttachmentLayer,
    Content,
    ContentFiles,
    ContributeContext,
    Contribution,
    FileContentLookup,
    InMemoryResources,
    MaskedResources,
    SchemaResourceType,
    compose_bundle,
    content_text,
    new_resource_types,
)


class _Tree(SchemaResourceType):
    """여러 파일 종류(테스트용 이름 `tree-x`): 파일 이름 목록을 칸 `trees`에 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="tree-x",
        title="tree",
        config_schema={"type": "object"},
        content=ResourceContentSpec(multi_file=True),
        contributes=["trees"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        assert isinstance(content, Mapping)
        return [Contribution("trees", [sorted(content)])]


class _Scoped(SchemaResourceType):
    """대체 칸이 있는 종류(`scoped-x`): `special`을 못 받으면 `plain`으로."""

    descriptor = ResourceTypeDescriptor(
        id="scoped-x",
        title="scoped",
        config_schema={"type": "object"},
        contributes=["special", "plain"],
    )

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("special", [{"x": 1}], fallback=Contribution("plain", ["대체 문장"]))]


def _types() -> Any:
    reg = new_resource_types()
    reg.register("tree-x", _Tree())
    reg.register("scoped-x", _Scoped())
    return reg


def _layer(*refs: str) -> list[AttachmentLayer]:
    return [AttachmentLayer("node", [ResourceAttachment(ref=r) for r in refs])]


def test_multi_file_type_reads_files_through_file_lookup() -> None:
    lookup = InMemoryResources(
        [Resource(id="t", type="tree-x", name="t")],
        {"t": {"SKILL.md": b"# s", "scripts/run.sh": b"echo"}},
    )
    assert isinstance(lookup, FileContentLookup)
    result = compose_bundle(_layer("t"), types=_types(), resources=lookup)
    assert result.bundle.slots == {"trees": [["SKILL.md", "scripts/run.sh"]]}
    assert not [i for i in result.issues if i.severity != "info"]


def test_multi_file_without_file_lookup_warns_unreadable() -> None:
    class _Plain:
        def get_resource(self, ref: str) -> Resource | None:
            return Resource(id=ref, type="tree-x", name=ref)

        def read_content(self, resource: Resource) -> Content:
            return None

    result = compose_bundle(_layer("t"), types=_types(), resources=_Plain())
    codes = [i.code for i in result.issues]
    assert "resource.content_unreadable" in codes


def test_masked_lookup_passes_files_through() -> None:
    inner = InMemoryResources([Resource(id="t", type="tree-x", name="t")], {"t": {"a.md": b"x"}})
    masked = MaskedResources(inner, _types())
    files: ContentFiles | None = masked.read_files(Resource(id="t", type="tree-x", name="t"))
    assert files == {"a.md": b"x"}


def test_in_memory_single_body_as_files_and_mapping_as_single() -> None:
    res = Resource.model_validate(
        {"id": "d", "type": "tree-x", "name": "d", "content": {"file": "main.md"}}
    )
    lookup = InMemoryResources([res], {"d": "본문"})
    assert lookup.read_files(res) == {"main.md": "본문".encode()}
    tree = InMemoryResources([res], {"d": {"main.md": b"m", "b.md": b"b"}})
    assert tree.read_content(res) == b"m"
    assert content_text({"a": b"x"}) is None


def test_fallback_used_when_backend_lacks_slot() -> None:
    lookup = InMemoryResources([Resource(id="s", type="scoped-x", name="s")])
    result = compose_bundle(_layer("s"), types=_types(), resources=lookup, accepted_slots=["plain"])
    assert result.bundle.slots == {"plain": ["대체 문장"]}
    fallback = [i for i in result.issues if i.code == SLOT_FALLBACK]
    assert fallback
    assert fallback[0].severity == "info"
    assert fallback[0].details["slot"] == "special"
    assert fallback[0].details["fallback"] == "plain"
    assert not [i for i in result.issues if i.code == SLOT_UNSUPPORTED]


def test_original_slot_kept_when_backend_accepts_it_or_unknown() -> None:
    lookup = InMemoryResources([Resource(id="s", type="scoped-x", name="s")])
    accepted = compose_bundle(
        _layer("s"), types=_types(), resources=lookup, accepted_slots=["special", "plain"]
    )
    assert accepted.bundle.slots == {"special": [{"x": 1}]}
    unknown = compose_bundle(_layer("s"), types=_types(), resources=lookup)
    assert unknown.bundle.slots == {"special": [{"x": 1}]}


def test_unsupported_slot_warning_carries_backend_note() -> None:
    lookup = InMemoryResources([Resource(id="s", type="scoped-x", name="s")])
    result = compose_bundle(
        _layer("s"),
        types=_types(),
        resources=lookup,
        accepted_slots=["other"],
        slot_notes={"special": "설정으로 꺼져 있음"},
    )
    warning = next(i for i in result.issues if i.code == SLOT_UNSUPPORTED)
    assert warning.details["reason"] == "설정으로 꺼져 있음"
    assert "설정으로 꺼져 있음" in warning.message
    assert warning.details["slot"] == "special"
