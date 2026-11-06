"""단위: 설정 스키마 도움말, 문구 데이터, 리소스 종류, 층 합치기, 범위 결과."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import Graph, Resource
from agent_console_contracts.schema_help import lint_schema_help
from agent_console_example_link import (
    ACCESS_INVALID,
    MODULE_ID,
    NotesAccess,
    NotesResourceType,
    NotesRunScope,
    NotesRunsSettings,
    load_defaults,
    load_resource_type,
    merge_access,
    module,
    notes_slot,
    register,
)
from agent_console_example_link.testing import StaticNotesReader
from agent_console_nodes_core import RESOURCE_TYPES_EXTENSION, TOOL_PROVIDERS
from agent_console_runtime import Registries, Services


def test_settings_schema_help() -> None:
    schema = NotesRunsSettings.model_json_schema()
    assert [i for i in lint_schema_help(schema) if i.severity == "error"] == []
    for name, prop in schema["properties"].items():
        assert prop.get("description"), name
        assert prop.get("x-ui", {}).get("tier") in ("basic", "advanced"), name


def test_settings_defaults_come_from_data_and_tool_name_override() -> None:
    data = load_defaults()
    assert NotesRunsSettings().max_notes_per_call == data["max_notes_per_call"]
    assert NotesRunsSettings().text().name == data["tool"]["name"]
    assert NotesRunsSettings(tool_name="team_notes").text().name == "team_notes"
    with pytest.raises(ValidationError):
        NotesRunsSettings(tool_name="공백 있는 이름")


def test_descriptor_declares_ports() -> None:
    d = module.descriptor
    assert (d.id, d.kind) == (MODULE_ID, "link")
    assert [p.name for p in d.requires] == ["example_notes.reader", "runs.reader"]
    assert [p.name for p in d.provides] == ["runs.scopes"]


def test_resource_type_data_and_schema() -> None:
    rtype = load_resource_type()
    assert notes_slot(rtype) == "example_notes"
    assert rtype.config_schema == NotesAccess.model_json_schema()
    bad = Resource(id="n", type=rtype.id, name="n", config={"limit": 0})
    assert [i.code for i in NotesResourceType(rtype).validate(bad)] == ["resource.invalid_config"]
    with pytest.raises(ValueError, match="contributes"):
        load_resource_type({"id": "x", "title": "x", "contributes": []})


def test_register_plugin_adds_resource_type() -> None:
    regs = Registries()
    register(regs)
    assert load_resource_type().id in regs.extension(RESOURCE_TYPES_EXTENSION)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([], NotesAccess()),
        ("not a list", NotesAccess()),
        ([{"config": {"limit": 2}}, {"config": {"tag": "t"}}], NotesAccess(limit=2, tag="t")),
        ([{"config": {"limit": 2}}, {"config": {"limit": 5}}], NotesAccess(limit=5)),
        ([{"no": "config"}, 3], NotesAccess()),
    ],
)
def test_merge_access_nearest_layer_wins(items: Any, expected: NotesAccess) -> None:
    assert merge_access(items) == (expected, [])


def test_merge_access_invalid() -> None:
    access, issues = merge_access([{"config": {"unknown": 1}}])
    assert access is None
    assert [(i.code, i.details["paths"]) for i in issues] == [(ACCESS_INVALID, ["/unknown"])]


def _graph() -> Graph:
    return Graph.model_validate({"id": "g", "name": "g", "nodes": [], "edges": []})


def test_scope_appends_after_existing_providers_and_skips_without_reader() -> None:
    text = NotesRunsSettings().text()
    reader = StaticNotesReader({None: ()})
    scope = NotesRunScope(lambda: reader, slot="example_notes", text=text, provider_id="p")
    earlier = object()
    found = scope.scope_run(_graph(), Services({TOOL_PROVIDERS: (earlier,)}), project_id="p1")
    assert found is not None
    providers = found.services[TOOL_PROVIDERS]
    assert providers[0] is earlier
    assert (providers[1].id, providers[1].project_id) == ("p", "p1")

    off = NotesRunScope(lambda: None, slot="example_notes", text=text, provider_id="p")
    assert off.scope_run(_graph(), Services({}), project_id=None) is None
