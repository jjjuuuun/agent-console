"""범위 종류(X29): 기본 데이터·병합·끄기·틀 해석·검사·플러그인 로더."""

from __future__ import annotations

import importlib.metadata

import pytest

from agent_console_contracts.memory import (
    MemoryAccessContext,
    MemoryScopeKindSpec,
    MemoryScopeRef,
    MemoryScopeSummary,
)
from agent_console_memory import (
    MEMORY_SCOPE_KINDS_GROUP,
    MemoryScopeKind,
    ScopeKindOrigins,
    as_scope_kinds,
    check_scope_kinds,
    load_default_scope_kinds,
    load_scope_kind_plugins,
    merge_scope_kinds,
    new_scope_kind_registry,
    plugin_scope_kinds,
    render_template,
    template_context_fields,
    template_problems,
)
from agent_console_memory.testing import sample_context, sample_scope_kinds

PLUGIN_TARGET = "agent_console_memory.testing:sample_plugin_scope_kinds"


def test_default_data_matches_design() -> None:
    defaults = load_default_scope_kinds()
    assert {k: v.id for k, v in defaults.items()} == {
        "shared": "",
        "project": "{/project_id}",
        "team": "{/graph_id}",
    }
    catalog = merge_scope_kinds()
    assert [k.origin for k in catalog.kinds] == [ScopeKindOrigins.DEFAULT] * 3
    ctx = sample_context()
    assert [catalog.resolve(k, ctx) for k in catalog.ids()] == [
        MemoryScopeRef(kind="shared", id=""),
        MemoryScopeRef(kind="project", id="p1"),
        MemoryScopeRef(kind="team", id="g1"),
    ]


def test_include_defaults_false_gives_empty_catalog() -> None:
    catalog = merge_scope_kinds(include_defaults=False)
    assert catalog.kinds == ()
    listing = catalog.listing()
    assert listing.kinds == []
    assert listing.include_defaults is False


def test_user_override_and_disable() -> None:
    catalog = merge_scope_kinds(
        defaults=sample_scope_kinds(("a", "b", "c")),
        user={
            "b": None,
            "c": {"label": "바꾼 이름", "id": "{/root_graph_id}"},
            "d": MemoryScopeKindSpec(label="새 범위", id="{/graph_id}/{/agent_id}"),
            "ghost": None,
        },
    )
    assert catalog.ids() == ["a", "c", "d"]
    c = catalog.get("c")
    assert c is not None
    assert c.origin == "user"
    assert c.overrides == "default"
    assert catalog.resolve("c", sample_context(root_graph_id="outer")) == MemoryScopeRef(
        kind="c", id="outer"
    )
    assert catalog.resolve("d", sample_context()) == MemoryScopeRef(kind="d", id="g1/agent-a")
    assert catalog.resolve("b", sample_context()) is None
    infos = {i.kind: i for i in catalog.listing().kinds}
    assert infos["b"].disabled is True
    assert "ghost" not in infos
    assert infos["d"].context_fields == ["graph_id", "agent_id"]
    assert infos["a"].context_fields == []
    assert catalog.listing(include_disabled=False).kinds[-1].kind == "d"


def test_empty_template_value_means_unavailable() -> None:
    assert render_template("{/project_id}", MemoryAccessContext()) is None
    assert render_template("{/graph_id}/{/agent_id}", MemoryAccessContext(graph_id="g")) is None
    assert render_template("fixed", MemoryAccessContext()) == "fixed"
    assert render_template("{/node_path}", MemoryAccessContext(node_path=["a", "b"])) == "a/b"
    assert render_template("{/node_path/1}", MemoryAccessContext(node_path=["a", "b"])) == "b"


@pytest.mark.parametrize(
    ("template", "count"),
    [("", 0), ("{/graph_id}", 0), ("{/nope}", 1), ("{graph_id}", 1), ("{/graph_id", 1), ("}", 1)],
)
def test_template_problems(template: str, count: int) -> None:
    assert len(template_problems(template)) == count


def test_template_context_fields_ignore_unknown() -> None:
    assert template_context_fields("{/project_id}-{/zzz}") == ["project_id"]


def test_check_scope_kinds_reports_paths() -> None:
    issues = check_scope_kinds(
        {
            "ok": {"label": "x", "id": "{/graph_id}"},
            "off": None,
            "bad id!": {},
            "t": {"label": "x", "id": "{/oops}"},
            "e": {"id": ""},
        }
    )
    paths = sorted(i.path or "" for i in issues)
    assert paths == ["/scope_kinds/bad id!", "/scope_kinds/e", "/scope_kinds/t/id"]
    assert {i.code for i in issues} == {"memory.settings_invalid"}


def test_merge_rejects_bad_user_template() -> None:
    with pytest.raises(ValueError, match="id 틀"):
        merge_scope_kinds(include_defaults=False, user={"x": {"label": "x", "id": "{/nope}"}})


def test_annotate_marks_unknown_kinds() -> None:
    catalog = merge_scope_kinds(include_defaults=False, user={"a": {"label": "A", "id": ""}})
    summaries = [
        MemoryScopeSummary(scope=MemoryScopeRef(kind="a", id=""), entries=1),
        MemoryScopeSummary(scope=MemoryScopeRef(kind="gone", id="x"), entries=2),
    ]
    assert [s.kind_known for s in catalog.annotate(summaries)] == [True, False]
    assert catalog.label("gone") == "gone"


def _ep(
    name: str, value: str, group: str = MEMORY_SCOPE_KINDS_GROUP
) -> importlib.metadata.EntryPoint:
    return importlib.metadata.EntryPoint(name=name, value=value, group=group)


def test_plugin_loader_with_fake_entry_point() -> None:
    registry = new_scope_kind_registry()
    reports = load_scope_kind_plugins(
        registry,
        entry_points=[
            _ep("good", PLUGIN_TARGET),
            _ep("broken", "agent_console_memory.testing:missing"),
            _ep("other-group", PLUGIN_TARGET, group="something.else"),
        ],
    )
    assert [(r.key, r.status) for r in reports] == [("broken", "failed"), ("good", "loaded")]
    kinds = plugin_scope_kinds(registry)
    assert [k.id for k in kinds] == ["sample-computed"]
    assert kinds[0].origin.startswith(ScopeKindOrigins.PLUGIN_PREFIX)
    catalog = merge_scope_kinds(
        defaults=sample_scope_kinds(("a", "b", "c")),
        plugins=kinds,
        user={"c": {"label": "c2", "id": ""}},
    )
    assert catalog.ids() == ["a", "b", "sample-computed", "c"]
    assert catalog.resolve("sample-computed", sample_context(root_run_id="run-123")) == (
        MemoryScopeRef(kind="sample-computed", id="run-")
    )
    info = next(i for i in catalog.listing().kinds if i.kind == "sample-computed")
    assert info.id is None
    assert info.context_fields == []


def test_plugin_enabled_filter_and_mapping_shape() -> None:
    registry = new_scope_kind_registry()
    reports = load_scope_kind_plugins(
        registry, enabled=set(), entry_points=[_ep("good", PLUGIN_TARGET)]
    )
    assert reports[0].status == "skipped"
    kinds = as_scope_kinds(lambda: {"w": {"label": "W", "id": "{/run_id}"}}, origin="plugin:x")
    assert kinds[0].template == "{/run_id}"
    assert kinds[0].origin == "plugin:x"
    with pytest.raises(TypeError):
        as_scope_kinds(42, origin="plugin:x")
    with pytest.raises(TypeError):
        as_scope_kinds([object()], origin="plugin:x")


def test_plugin_overrides_default_records_origin() -> None:
    plugin = MemoryScopeKind(id="a", label="from plugin", template="{/run_id}", origin="plugin:p")
    catalog = merge_scope_kinds(defaults=sample_scope_kinds(("a", "b", "c")), plugins=[plugin])
    a = catalog.get("a")
    assert a is not None
    assert a.origin == "plugin:p"
    assert a.overrides == "default"


def test_resolver_exception_means_unavailable() -> None:
    def boom(_ctx: MemoryAccessContext) -> str | None:
        raise RuntimeError("x")

    kind = MemoryScopeKind(id="z", label="z", resolver=boom)
    assert kind.resolve(MemoryAccessContext()) is None
