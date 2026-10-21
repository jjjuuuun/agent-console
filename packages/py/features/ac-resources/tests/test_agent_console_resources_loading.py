"""종류 등록: entry point·모듈·선언형 데이터, 플러그인 제거 시 목록에서 사라짐."""

from __future__ import annotations

import sys
import types as pytypes
from collections.abc import Iterator
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from agent_console_contracts import (
    Resource,
    ResourceAttachment,
    ResourceContentRef,
    ResourceTypeDescriptor,
)
from agent_console_resources import (
    RESOURCE_TYPES_GROUP,
    AttachmentLayer,
    Content,
    ContributeContext,
    Contribution,
    DeclarativeTypeError,
    InMemoryResources,
    SchemaResourceType,
    as_resource_type,
    compose_bundle,
    declarative_type_from_data,
    list_descriptors,
    load_declarative_types,
    load_resource_types,
    new_resource_types,
)

_MOD = "ac_resources_test_plugin_mod"


class Alpha(SchemaResourceType):
    descriptor = ResourceTypeDescriptor(id="alpha", title="A", contributes=["a"])

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("a", [resource.id])]


class Beta(Alpha):
    descriptor = ResourceTypeDescriptor(id="beta", title="B", contributes=["b"])

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return [Contribution("b", [resource.id])]


@pytest.fixture
def plugin_module() -> Iterator[str]:
    mod = pytypes.ModuleType(_MOD)
    mod.Alpha = Alpha  # type: ignore[attr-defined]
    mod.Beta = Beta  # type: ignore[attr-defined]
    mod.not_a_type = object()  # type: ignore[attr-defined]
    sys.modules[_MOD] = mod
    yield _MOD
    del sys.modules[_MOD]


def _ep(name: str, attr: str) -> EntryPoint:
    return EntryPoint(name=name, value=f"{_MOD}:{attr}", group=RESOURCE_TYPES_GROUP)


def test_entry_points_register_and_removal_hides_type(plugin_module: str) -> None:
    full = new_resource_types()
    reports = load_resource_types(full, entry_points=[_ep("alpha", "Alpha"), _ep("beta", "Beta")])
    assert all(r.status == "loaded" for r in reports)
    assert [d.id for d in list_descriptors(full)] == ["alpha", "beta"]

    # beta 플러그인을 뺀 설치(= entry point 없음)
    without = new_resource_types()
    load_resource_types(without, entry_points=[_ep("alpha", "Alpha")])
    assert [d.id for d in list_descriptors(without)] == ["alpha"]
    lookup = InMemoryResources(
        [Resource(id="ra", type="alpha", name="ra"), Resource(id="rb", type="beta", name="rb")]
    )
    layers = [AttachmentLayer("t", [ResourceAttachment(ref="ra"), ResourceAttachment(ref="rb")])]
    result = compose_bundle(layers, types=without, resources=lookup)
    assert result.bundle.slots == {"a": ["ra"]}
    assert [i.code for i in result.issues] == ["resource.unknown_type"]

    # enabled로 끄기
    off = new_resource_types()
    reports = load_resource_types(
        off, entry_points=[_ep("alpha", "Alpha"), _ep("beta", "Beta")], enabled={"beta"}
    )
    assert {r.key: r.status for r in reports} == {"alpha": "skipped", "beta": "loaded"}


def test_bad_plugin_is_reported_not_raised(plugin_module: str) -> None:
    reg = new_resource_types()
    reports = load_resource_types(
        reg,
        entry_points=[_ep("bad", "not_a_type"), _ep("missing", "Nope")],
        modules=[f"{plugin_module}:Alpha", "nope.module:X"],
    )
    status = {
        r.source.split()[-1] if r.source.startswith("module") else r.key: r.status for r in reports
    }
    assert status["bad"] == "failed"
    assert status["missing"] == "failed"
    assert status[f"{plugin_module}:Alpha"] == "loaded"
    assert status["nope.module:X"] == "failed"
    assert "Alpha" in reg


def test_as_resource_type_rejects_objects_without_descriptor() -> None:
    with pytest.raises(TypeError):
        as_resource_type(object())
    assert as_resource_type(Alpha).descriptor.id == "alpha"


# ---------------------------------------------------------------- 선언형 종류
DECL = """\
id: prompt-fragment
title: 프롬프트 조각
config_schema:
  type: object
  properties:
    title: {type: string}
content: {media_types: [text/markdown], editor: markdown}
slot_key: title
contributes:
  - slot: instructions
    template: "## {title}\\n{content}"
  - slot: lint_rules
    value: {rule: "{title}", tags: ["{id}", "{missing}"]}
    combine: append
  - slot: env_map
    value: {T: "{title}"}
    raw: true
    combine: merge
"""


def test_declarative_type_builds_bundle(tmp_path: Path) -> None:
    folder = tmp_path / "resource-types"
    folder.mkdir()
    (folder / "prompt-fragment.yaml").write_text(DECL, encoding="utf-8")
    (folder / "README.txt").write_text("무시", encoding="utf-8")
    reg = new_resource_types()
    reports = load_declarative_types(folder, reg)
    assert [(r.key, r.status) for r in reports] == [("prompt-fragment", "loaded")]
    desc = list_descriptors(reg)[0]
    assert desc.declarative is True
    assert desc.contributes == ["instructions", "lint_rules", "env_map"]

    lookup = InMemoryResources(
        [
            Resource(
                id="tip",
                type="prompt-fragment",
                name="팁",
                config={"title": "짧게"},
                content=ResourceContentRef(file="content.md"),
            )
        ],
        contents={"tip": "답은 {짧게} 한다."},
    )
    result = compose_bundle(
        [AttachmentLayer("team", [ResourceAttachment(ref="tip")])], types=reg, resources=lookup
    )
    # 본문 안의 {…}는 다시 치환하지 않는다. 모르는 이름은 그대로.
    assert result.bundle.slots == {
        "instructions": ["## 짧게\n답은 {짧게} 한다."],
        "lint_rules": [{"rule": "짧게", "tags": ["tip", "{missing}"]}],
        "env_map": {"T": "짧게"},
    }
    assert result.issues == ()


def test_declarative_errors_are_reported(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("id: x\ntitle: X\ncontributes: []\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("- not a mapping\n", encoding="utf-8")
    (tmp_path / "c.yml").write_text(
        "id: c\ntitle: C\nconfig_schema: {type: 3}\ncontributes: [{slot: s, template: t}]\n",
        encoding="utf-8",
    )
    (tmp_path / "d.yaml").write_text(
        "id: d\ntitle: D\ncontributes: [{slot: s, template: t, value: 1}]\n", encoding="utf-8"
    )
    (tmp_path / "e.yaml").write_text("id: [\n", encoding="utf-8")
    reg = new_resource_types()
    reports = load_declarative_types(tmp_path, reg)
    assert [r.status for r in reports] == ["failed"] * 5
    assert len(reg) == 0
    assert load_declarative_types(tmp_path / "missing", reg) == []


def test_declarative_duplicate_with_plugin_fails(tmp_path: Path, plugin_module: str) -> None:
    reg = new_resource_types()
    load_resource_types(reg, entry_points=[_ep("alpha", "Alpha")])
    (tmp_path / "alpha.yaml").write_text(
        "id: alpha\ntitle: 겹침\ncontributes: [{slot: s, template: t}]\n", encoding="utf-8"
    )
    reports = load_declarative_types(tmp_path, reg)
    assert reports[0].status == "failed"
    assert "DuplicateKeyError" in (reports[0].error or "")


def test_declarative_from_data_validates() -> None:
    with pytest.raises(DeclarativeTypeError):
        declarative_type_from_data({"id": "x", "title": "X", "contributes": [{"slot": "s"}]})
    item = declarative_type_from_data(
        {"id": "x", "title": "X", "contributes": [{"slot": "s", "template": "{name}"}]}
    )
    res = Resource(id="r", type="x", name="이름")
    assert item.validate(res) == []
    out = item.contribute(res, None, ContributeContext(ResourceAttachment(ref="r")))
    assert out == [Contribution("s", ["이름"], None)]
