"""선언 모델·공용 JSON Schema·마크다운 도우미 테스트."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from extdocs_common import TOOL_DIR, load_data
from extdocs_md import anchors, github_slug, hand_text, headings, replace_facts, section_text
from extdocs_model import ExtensionPointTable, ToolTable, schema_text
from extdocs_points import SCHEMA_FILE
from pydantic import ValidationError

DESIGN_EXAMPLE = """\
[tool.agent-console.extension-points.wiki-search-index]
title = "위키 검색 색인"
area = "wiki"
design_id = "X48"
summary = "위키 검색을 다른 색인 구현으로 바꾼다"
registration = { kind = "entry-point", group = "agent_console_wiki:SEARCH_INDEX_GROUP" }
interface = ["agent_console_wiki:WikiSearchIndex"]
settings = ["modules.options.mod-wiki.search.backend", "wiki.search_backend"]
builtin = "entry-points"
example = { kind = "package", path = "examples/extensions/agent-console-example-wiki-search" }
guide = "wiki.md#wiki-search-index"
"""


def test_design_example_parses() -> None:
    raw = tomllib.loads(DESIGN_EXAMPLE)["tool"]["agent-console"]
    table = ToolTable.model_validate(raw)
    point = table.extension_points.root["wiki-search-index"]
    assert point.example[0].kind == "package"
    assert point.registration.group == "agent_console_wiki:SEARCH_INDEX_GROUP"


def test_schema_file_matches_model() -> None:
    assert (TOOL_DIR / SCHEMA_FILE).read_text(encoding="utf-8") == schema_text()


def test_json_schema_agrees_with_model() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(schema_text())
    raw = tomllib.loads(DESIGN_EXAMPLE)["tool"]["agent-console"]["extension-points"]
    jsonschema.validate(raw, schema)
    ExtensionPointTable.model_validate(raw)
    bad = {"Bad_Slug": raw["wiki-search-index"]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
    with pytest.raises(ValidationError):
        ExtensionPointTable.model_validate(bad)
    typo = {"x": {**raw["wiki-search-index"], "tyop": 1}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(typo, schema)


def test_example_kind_requirements() -> None:
    base = {"title": "t", "area": "wiki", "summary": "s", "registration": {"kind": "injection"}}
    with pytest.raises(ValidationError):
        ExtensionPointTable.model_validate({"a": {**base, "example": {"kind": "package"}}})
    with pytest.raises(ValidationError):
        ExtensionPointTable.model_validate({"a": {**base, "example": {"kind": "contract-tests"}}})
    with pytest.raises(ValidationError):
        ExtensionPointTable.model_validate({"a": {**base, "guide": "no-extension#x"}})


def test_data_files_load() -> None:
    data = load_data()
    assert data.areas
    assert data.readme_sections
    assert len(data.lint_rules) == 7
    assert "_default" in data.registration_templates


def test_github_slug() -> None:
    assert github_slug("설치·제거") == "설치제거"
    assert github_slug("`wiki-search-index` 색인") == "wiki-search-index-색인"
    assert github_slug("A [링크](x.md) B") == "a-링크-b"


def test_headings_skip_fences_and_dedupe() -> None:
    text = "# A\n\n```\n# not\n```\n\n## B\n\n## B\n"
    assert [h.anchor for h in headings(text)] == ["a", "b", "b-1"]
    assert "b-1" in anchors(text)


def test_section_and_hand_text() -> None:
    text = (
        "# P\n\n## one\n\n<!-- extdocs:todo -->\n\n<!-- extdocs:facts one -->\n- x\n"
        "<!-- /extdocs:facts -->\n\n## two\n\n글.\n"
    )
    one = section_text(text, "one")
    assert one is not None
    assert hand_text(one) == ""
    two = section_text(text, "two")
    assert two is not None
    assert hand_text(two) == "글."
    replaced = replace_facts(text, {"one": "- y\n"})
    assert "- y\n<!-- /extdocs:facts -->" in replaced
    assert "- x" not in replaced


def test_first_doc_line_reads_type_alias_attribute_docstring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``type X = ...`` 별칭은 "Type alias." 대신 정의 뒤 문자열의 첫 줄을 쓴다."""
    import importlib

    from extdocs_common import first_doc_line

    (tmp_path / "alias_doc_mod.py").write_text(
        'type Documented = int\n"""설치자 옵션 → 형식.\n\n자세히."""\n\ntype Bare = str\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module("alias_doc_mod")
    assert first_doc_line(mod.Documented) == "설치자 옵션 → 형식."
    assert first_doc_line(mod.Bare) == ""
