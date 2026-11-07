"""계약 0.14.0(7R.3, design §7R.7): 하위 모듈 `wiki` 1.0.0, `common` 1.10.0, `projects` 3.3.0,
`sdd` 1.2.0, `modules` 1.5.0.

- 설계 문서의 YAML 예(§7R.1.1 위키 규칙·§7R.1.2 위키·§7R.1.3 기본 문법·§7R.1.4 리소스 접근·§7R.1.5
  설정)가 모델로 읽히고 JSON으로 왕복한다. 모르는 키는 보존한다.
- 문법 모델은 모든 키가 None 기본(= 상속)이다.
- 도구 이름·설명 기본값은 패키지 데이터 → 스키마 기본값에만 있다(소스 문자열 상수에 없음).
- 0.13 응답(새 필드 없음)이 그대로 읽힌다.
"""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from ruamel.yaml import YAML

from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    CopyKindInfo,
    ErrorCodes,
    KnownIssueCodes,
    KnownUiWidgets,
    SpecTemplateSummary,
    WsServerMessage,
    wiki,
)
from agent_console_contracts.schema import build_schema
from agent_console_contracts.schema_help import lint_contract_help

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_contracts"


def _load(text: str) -> Any:
    return YAML(typ="safe").load(io.StringIO(text))


# ---------------------------------------------------------------- 버전


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_0() -> None:
    """0.14.0에서 정한 버전 이상이다(정확한 지금 값은 0.14.4 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 0)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0140 = {
        "common": "1.10.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.3.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.0.0",
        "modules": "1.5.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0140)
    for sub, version in v0140.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub
    # wiki는 memory·sdd와 같은 층(modules 바로 아래)
    assert CONTRACT_SUBMODULES.index("wiki") == CONTRACT_SUBMODULES.index("modules") - 1


def test_wiki_models_live_in_wiki_submodule() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        "WikiDefinition",
        "WikiRulesDefinition",
        "WikiPageTemplate",
        "WikiWriteRule",
        "WikiLintRule",
        "WikiSyntax",
        "WikiLinkRule",
        "WikiFrontMatter",
        "WikiScheme",
        "WikiLintDefaults",
        "EffectiveWikiSyntax",
        "WikiInfo",
        "WikiCapabilities",
        "WikiLimits",
        "WikiSummary",
        "WikiView",
        "WikiPageSummary",
        "WikiPageView",
        "WikiLink",
        "WikiBacklink",
        "WikiPageVersion",
        "WikiAuthor",
        "WikiSearchResult",
        "WikiGraph",
        "WikiIssue",
        "WikiLintReport",
        "WikiMoveRequest",
        "WikiMoveResult",
        "WikiPageWrite",
        "WikiImportResult",
        "WikiChanged",
        "WikiAccessConfig",
        "WikiToolNames",
        "WikiEventPayload",
        "WikiSettings",
        "WikiWriteCheckSetting",
    } <= set(grouped["wiki"])
    assert "WikiChangedMessage" in grouped["modules"]


# ---------------------------------------------------------------- YAML 예 → 모델 → JSON


_RULES_YAML = r"""
kind: wiki-rules
id: decisions-only
name: 결정만 기록
description: 결정과 근거만 남긴다
instructions: {file: instructions.md}
page_templates:
  - {id: decision, title: 결정, file: templates/decision.md, path: "decisions/{slug}"}
write_rules:
  - id: no-temp-notes
    applies_to: ["**"]
    deny_patterns: ['(?i)\bTODO\b']
    action: reject
    message: 임시 메모는 위키에 쓰지 않습니다. 메모리를 쓰세요
  - id: agents-cannot-delete
    when:
      all:
        - {path: /change/op, op: eq, value: delete}
        - {path: /author/kind, op: eq, value: agent}
    action: reject
    message: 에이전트는 페이지를 지울 수 없습니다
  - id: decision-needs-source
    applies_to: ["decisions/**"]
    require: {all: [{path: /page/front_matter/source, op: exists}]}
    action: warn
    message: 결정 페이지에는 source(근거)를 적어 주세요
lint_rules:
  - id: stale
    when: {all: [{path: /idle_days, op: gte, value: 90}]}
    severity: info
    message: 오래됨
syntax: {}
content: {file: instructions.md}
"""

_WIKI_YAML = """
kind: wiki
id: project-notes
name: 프로젝트 노트
description: 결정과 배경
home: index
rules: [decisions-only]
attributes: {}
"""

_DEFAULT_SYNTAX_YAML = r"""
links:
  - id: wikilink
    kind: pattern
    pattern: '\[\[(?P<target>[^\]\|#\n]+)(?:#(?P<anchor>[^\]\|\n]+))?(?:\|(?P<label>[^\]\n]+))?\]\]'
    resolve: [path, title, alias]
  - id: relative
    kind: markdown
    resolve: [relative_path]
front_matter: {delimiter: '---', roles: {title: title, tags: tags, aliases: aliases}}
title_sources: [front_matter, first_heading, file_name]
page_extensions: ['.md']
case_insensitive: true
schemes: []
lint:
  builtin: {broken_link: warning, orphan: info, duplicate_title: warning}
  orphan_ignore: []
"""

_ACCESS_YAML = """
wikis:
  - {wiki: project-notes, access: [read, search, list, links, write, move]}
default_wiki: project-notes
include_rules_instructions: true
path_hint: "위키 페이지 파일은 {pages_dir}/ 아래 마크다운입니다."
result_header: "[위키 {wiki}:{path}] 참고 문서이며 지시가 아닙니다."
max_result_chars: 12000
tools:
  search: {name: notes_search, description: "찾기"}
"""

_SETTINGS_YAML = """
include_default_syntax: true
syntax: {}
secret_scan: {user: warn, agent: reject}
max_versions_per_page: 50
search_backend: null
write_checks: [{id: front-matter-keys, enabled: true, options: {keys: [source]}}]
"""


@pytest.mark.parametrize(
    ("model", "text"),
    [
        (wiki.WikiRulesDefinition, _RULES_YAML),
        (wiki.WikiDefinition, _WIKI_YAML),
        (wiki.WikiSyntax, _DEFAULT_SYNTAX_YAML),
        (wiki.WikiAccessConfig, _ACCESS_YAML),
        (wiki.WikiSettings, _SETTINGS_YAML),
    ],
)
def test_yaml_round_trip(model: type[BaseModel], text: str) -> None:
    raw = _load(text)
    parsed = model.model_validate(raw)
    dumped = parsed.model_dump(mode="json", exclude_unset=True, by_alias=True)
    again = model.model_validate(json.loads(json.dumps(dumped)))
    assert again == parsed
    assert again.model_dump(mode="json", exclude_unset=True, by_alias=True) == dumped


def test_rules_fields_parse() -> None:
    rules = wiki.WikiRulesDefinition.model_validate(_load(_RULES_YAML))
    assert rules.instructions == wiki.WikiContentRef(file="instructions.md")
    assert [r.id for r in rules.write_rules] == [
        "no-temp-notes",
        "agents-cannot-delete",
        "decision-needs-source",
    ]
    delete_rule = rules.write_rules[1]
    assert delete_rule.when is not None
    assert delete_rule.when.all is not None
    assert delete_rule.when.all[1].path == "/author/kind"
    assert rules.write_rules[2].action == "warn"
    assert rules.write_rules[2].require is not None
    assert rules.lint_rules[0].severity == "info"
    assert rules.page_templates[0].path == "decisions/{slug}"
    # 열린 문자열: 모르는 action도 읽힌다(ac-wiki가 warn으로 읽고 이슈)
    odd = wiki.WikiWriteRule.model_validate({"id": "x", "action": "quarantine"})
    assert odd.action == "quarantine"


def test_default_syntax_data_parses() -> None:
    syntax = wiki.WikiSyntax.model_validate(_load(_DEFAULT_SYNTAX_YAML))
    assert syntax.links is not None
    assert [(r.id, r.kind) for r in syntax.links] == [
        ("wikilink", "pattern"),
        ("relative", "markdown"),
    ]
    assert syntax.links[1].pattern is None
    assert syntax.front_matter is not None
    assert syntax.front_matter.roles == {
        "title": "title",
        "tags": "tags",
        "aliases": "aliases",
    }
    assert syntax.lint is not None
    assert syntax.lint.builtin == {
        "broken_link": "warning",
        "orphan": "info",
        "duplicate_title": "warning",
    }
    assert syntax.schemes == []
    off = wiki.WikiLintDefaults.model_validate({"builtin": {"orphan": None}})
    assert off.builtin == {"orphan": None}


def test_syntax_models_default_every_key_to_none() -> None:
    for model in (wiki.WikiSyntax, wiki.WikiFrontMatter, wiki.WikiLintDefaults):
        empty = model()
        assert all(getattr(empty, name) is None for name in model.model_fields), model
        assert empty.model_dump(exclude_unset=True) == {}
    # 빈 목록은 "이 층에서는 없음"이라 None과 다르게 남는다
    assert wiki.WikiSyntax(links=[]).links == []
    schema = build_schema()["$defs"]["WikiSyntax"]
    assert schema.get("required", []) == []


def test_unknown_keys_are_preserved() -> None:
    for model, text in ((wiki.WikiDefinition, _WIKI_YAML), (wiki.WikiRulesDefinition, _RULES_YAML)):
        raw = _load(text)
        raw["x-team-note"] = {"owner": "someone"}
        raw.setdefault("write_rules", [{"id": "a"}])
        parsed = model.model_validate(raw)
        dumped = parsed.model_dump(mode="json", exclude_unset=True)
        assert dumped["x-team-note"] == {"owner": "someone"}
    rule = wiki.WikiWriteRule.model_validate({"id": "a", "future_key": 1})
    assert rule.model_dump(exclude_unset=True)["future_key"] == 1
    settings = wiki.WikiSettings.model_validate({"future": {"a": 1}})
    assert settings.model_dump(exclude_unset=True) == {"future": {"a": 1}}


def test_wiki_definition_defaults() -> None:
    w = wiki.WikiDefinition.model_validate({"kind": "wiki", "id": "w", "name": "W"})
    assert w.rules == []
    assert w.home is None
    assert w.attributes == {}
    assert w.model_dump(exclude_unset=True) == {"kind": "wiki", "id": "w", "name": "W"}


def test_settings_defaults() -> None:
    s = wiki.WikiSettings()
    assert s.include_default_syntax is True
    assert s.syntax is None
    # 0.14.1: system도 reject(보안 강화, test_agent_console_contracts_v14_1)
    assert s.secret_scan == {"user": "warn", "agent": "reject", "system": "reject"}
    assert s.max_versions_per_page == 50
    assert s.search_backend is None
    assert s.write_checks == []
    prop = build_schema()["$defs"]["WikiSettings"]["properties"]["secret_scan"]
    assert prop["default"] == {"user": "warn", "agent": "reject", "system": "reject"}


# ---------------------------------------------------------------- 접근 설정·도구 이름 기본값


def test_access_tool_defaults_come_from_package_data() -> None:
    data = wiki.wiki_access_defaults()
    assert set(data["tools"]) == set(wiki.WIKI_ACCESS_OPS)
    config = wiki.WikiAccessConfig()
    for op in wiki.WIKI_ACCESS_OPS:
        assert getattr(config.tools, op).name == data["tools"][op]["name"]
    assert config.path_hint == data["path_hint"]
    assert config.result_header == data["result_header"]
    assert config.max_result_chars == data["max_result_chars"]
    assert config.include_rules_instructions is True
    assert config.wikis == []
    assert config.default_wiki is None
    # 스키마 기본값으로만 보인다(웹 폼·서버 모두 여기서 읽는다)
    tools = build_schema()["$defs"]["WikiToolNames"]["properties"]
    for op in wiki.WIKI_ACCESS_OPS:
        assert tools[op]["default"] == data["tools"][op]
    # 생략 = 기본값이며 저장 형식에는 나오지 않는다
    assert wiki.WikiAccessConfig.model_validate({}).model_dump(exclude_unset=True) == {}


def test_tool_names_are_not_string_constants_in_source() -> None:
    names = {t["name"] for t in wiki.wiki_access_defaults()["tools"].values()}
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in names:
            assert f'"{name}"' not in text, (path.name, name)
            assert f"'{name}'" not in text, (path.name, name)


def test_access_entry_and_layer_values() -> None:
    config = wiki.WikiAccessConfig.model_validate(_load(_ACCESS_YAML))
    assert config.wikis[0].access == ["read", "search", "list", "links", "write", "move"]
    assert config.tools.search.name == "notes_search"
    assert config.tools.read.name == wiki.wiki_access_defaults()["tools"]["read"]["name"]
    entry = wiki.WikiAccessEntry.model_validate({"wiki": "w"})
    assert entry.access == ["read", "search", "list", "links"]  # delete·write는 적은 것만
    with pytest.raises(ValueError, match="access"):
        wiki.WikiAccessEntry.model_validate({"wiki": "w", "access": ["publish"]})
    with pytest.raises(ValueError, match="name"):
        wiki.WikiToolText.model_validate({"name": "has space", "description": ""})


def test_schema_widgets_and_subject_paths() -> None:
    defs = build_schema()["$defs"]
    entry = defs["WikiAccessEntry"]["properties"]["wiki"]
    assert entry["x-ui"]["widget"] == KnownUiWidgets.WIKI_REF == "wiki-ref"
    assert defs["WikiAccessConfig"]["properties"]["default_wiki"]["x-ui"]["widget"] == "wiki-ref"
    rule = defs["WikiWriteRule"]["properties"]
    assert rule["applies_to"]["x-ui"]["widget"] == KnownUiWidgets.GLOB == "glob"
    assert rule["deny_patterns"]["x-ui"]["widget"] == KnownUiWidgets.REGEX
    assert rule["when"]["x-ui"]["widget"] == KnownUiWidgets.CONDITION
    assert rule["require"]["x-ui"]["widget"] == KnownUiWidgets.CONDITION
    assert defs["WikiLintRule"]["properties"]["when"]["x-ui"]["widget"] == "condition"
    assert defs["WikiLinkRule"]["properties"]["pattern"]["x-ui"]["widget"] == "regex"
    assert defs["WikiLintDefaults"]["properties"]["orphan_ignore"]["x-ui"]["widget"] == "glob"
    write_path = defs["WikiWriteConditionItem"]["properties"]["path"]
    assert write_path["examples"] == list(wiki.WIKI_WRITE_SUBJECT_PATHS)
    lint_path = defs["WikiLintConditionItem"]["properties"]["path"]
    assert lint_path["examples"] == list(wiki.WIKI_LINT_SUBJECT_PATHS)
    # 판단 대상 최상위 키(§7R.1.1)마다 제안 경로가 하나 이상
    for top in ("change", "author", "page", "before"):
        assert any(p.split("/")[1] == top for p in wiki.WIKI_WRITE_SUBJECT_PATHS), top
    for top in ("idle_days", "age_days", "backlinks", "broken_links", "updated_by_kind"):
        assert f"/{top}" in wiki.WIKI_LINT_SUBJECT_PATHS


def test_wiki_form_models_pass_schema_help_lint() -> None:
    names = set(build_schema()["x-modules"]["wiki"])
    issues = [i for i in lint_contract_help() if i.path.split("/")[2] in names]
    assert issues == [], "\n".join(f"{i.rule} {i.path}: {i.message}" for i in issues)


# ---------------------------------------------------------------- 보기·요청·이벤트


def test_views_and_utf16_link_ranges() -> None:
    text = "가😀 [[대상|라벨]]"
    start = len(text[: text.index("[")].encode("utf-16-le")) // 2
    end = start + len("[[대상|라벨]]".encode("utf-16-le")) // 2
    link = wiki.WikiLink(
        start=start,
        end=end,
        raw="[[대상|라벨]]",
        kind="pattern",
        rule_id="wikilink",
        target="대상",
        label="라벨",
        broken=True,
    )
    encoded = text.encode("utf-16-le")
    assert encoded[link.start * 2 : link.end * 2].decode("utf-16-le") == link.raw
    assert link.resolved is None
    assert link.scheme_target is None
    page = wiki.WikiPageSummary(path="decisions/api-version")
    view = wiki.WikiPageView(page=page, content=text, content_hash="h", links=[link])
    assert view.backlinks == []
    assert view.front_matter == {}
    version = wiki.WikiPageVersion.model_validate(
        {
            "version": 2,
            "op": "move_in",
            "sha256": "h",
            "bytes": 3,
            "author": {"kind": "agent", "run_id": "r1", "node_path": ["team", "writer"]},
            "at": 1.0,
            "from": "old/path",
        }
    )
    assert version.from_ == "old/path"
    assert version.model_dump(mode="json", exclude_unset=True)["from"] == "old/path"
    edge = wiki.WikiGraphEdge.model_validate({"from": "a", "to": "b"})
    assert edge.model_dump(mode="json")["from"] == "a"
    issue = wiki.WikiIssue(
        severity="warning", code=KnownIssueCodes.WIKI_BROKEN_LINK, message="m", page="a", line=3
    )
    assert issue.path is None
    assert issue.page == "a"
    info = wiki.WikiInfo(
        pages_root=".agent-console/wiki-pages",
        limits=wiki.WikiLimits(max_page_bytes=524288, max_pages=10000, graph_max_nodes=500),
    )
    assert info.capabilities.history is False


def test_move_and_event_payload_have_no_body() -> None:
    result = wiki.WikiMoveResult.model_validate(
        {"from": "a", "to": "b", "rewritten": [{"path": "c", "count": 2}], "conflicts": ["d"]}
    )
    assert result.moved is False
    assert result.rewritten[0].count == 2
    payload = wiki.WikiEventPayload(op="write", status="rule_rejected", rule_ids=["no-temp-notes"])
    fields = set(wiki.WikiEventPayload.model_fields)
    assert not fields & {"content", "query", "text", "body"}
    assert payload.code is None
    assert tuple(f"wiki.{op}" for op in wiki.WIKI_ACCESS_OPS) == wiki.KNOWN_WIKI_EVENT_TYPES
    assert wiki.WIKI_ACCESS_OPS == ("read", "search", "list", "links", "write", "move", "delete")


def test_ws_wiki_changed_message() -> None:
    msg = WsServerMessage.model_validate(
        {
            "type": "wiki.changed",
            "payload": {"wiki_id": "notes", "paths": ["index"], "external": True},
        }
    )
    assert msg.root.type == "wiki.changed"
    assert msg.root.payload.external is True


def test_document_constants_exported() -> None:
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_WIKI_LINK_KINDS"] == {"PATTERN": "pattern", "MARKDOWN": "markdown"}
    assert constants["KNOWN_WIKI_RESOLVERS"] == {
        "PATH": "path",
        "TITLE": "title",
        "ALIAS": "alias",
        "RELATIVE_PATH": "relative_path",
    }
    assert constants["KNOWN_WIKI_AUTHOR_KINDS"] == {
        "USER": "user",
        "AGENT": "agent",
        "SYSTEM": "system",
        "EXTERNAL": "external",
    }
    assert set(constants["KNOWN_WIKI_VERSION_OPS"].values()) >= {
        "create",
        "update",
        "delete",
        "move_out",
        "move_in",
        "restore",
        "external",
        "import",
    }
    assert constants["KNOWN_WIKI_LINT_CODES"] == {
        "BROKEN_LINK": "broken_link",
        "ORPHAN": "orphan",
        "DUPLICATE_TITLE": "duplicate_title",
    }
    assert constants["KNOWN_WIKI_FRONT_MATTER_ROLES"] == {
        "TITLE": "title",
        "TAGS": "tags",
        "ALIASES": "aliases",
    }
    assert constants["WIKI_WRITE_SUBJECT_PATHS"] == list(wiki.WIKI_WRITE_SUBJECT_PATHS)
    assert constants["WIKI_LINT_SUBJECT_PATHS"] == list(wiki.WIKI_LINT_SUBJECT_PATHS)
    assert constants["KNOWN_UI_WIDGETS"]["WIKI_REF"] == "wiki-ref"
    assert constants["KNOWN_UI_WIDGETS"]["GLOB"] == "glob"


def test_error_and_issue_codes() -> None:
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_NOT_FOUND] == 404
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_PAGE_NOT_FOUND] == 404
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_PAGE_EXISTS] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_RULE_REJECTED] == 422
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_SECRET_REJECTED] == 422
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_TOO_LARGE] == 422
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_SPACES_UNAVAILABLE] == 409
    # 같은 이름의 오류 코드와 이슈 코드는 같은 값이다
    for name, value in vars(ErrorCodes).items():
        if name.startswith("WIKI_"):
            assert getattr(KnownIssueCodes, name) == value, name
    # 도구 사유 코드 = wiki.<상태>
    for status in ("denied", "conflict", "rate_limited", "wiki_unavailable", "invalid_path"):
        assert f"wiki.{status}" in vars(KnownIssueCodes).values(), status
    for code in (
        "wiki.history_unavailable",
        "wiki.search_degraded",
        "wiki.front_matter_invalid",
        "wiki.rules_missing",
        "wiki.duplicate_rule_id",
        "wiki.broken_link",
        "wiki.orphan",
        "wiki.duplicate_title",
        "wiki.link_pattern_invalid",
        "wiki.parse_timeout",
        "wiki.too_many_pages",
        "wiki.settings_invalid",
        "wiki.unknown_wiki",
        "wiki.secret_suspect",
    ):
        assert code in vars(KnownIssueCodes).values(), code
    assert KnownIssueCodes.SDD_AUTOMATION_SKIPPED == "sdd.automation_skipped"
    assert KnownIssueCodes.TOOLS_INSTRUCTIONS_UNSUPPORTED == "tools.instructions_unsupported"


# ---------------------------------------------------------------- 6R 후보·0.13 호환


def test_copy_kind_title_and_template_kind_are_optional() -> None:
    old_kind = CopyKindInfo.model_validate(
        {"kind": "wiki-rules", "library": True, "portable": True}
    )
    assert old_kind.title is None
    assert "title" not in old_kind.model_dump(exclude_unset=True)
    assert (
        CopyKindInfo(kind="k", library=True, portable=False, title="위키 규칙").title == "위키 규칙"
    )
    old_tpl = SpecTemplateSummary.model_validate({"id": "t", "name": "T"})
    assert old_tpl.kind is None
    assert SpecTemplateSummary(id="t", kind="spec-template").kind == "spec-template"
    defs = build_schema()["$defs"]
    assert "title" not in defs["CopyKindInfo"].get("required", [])
    assert "kind" not in defs["SpecTemplateSummary"].get("required", [])


def test_0_13_ws_messages_still_read() -> None:
    msg = WsServerMessage.model_validate(
        {"type": "sdd.changed", "payload": {"spec_id": "s", "version_hash": "h"}}
    )
    assert msg.root.type == "sdd.changed"


# ---------------------------------------------------------------- 7R.2a 결정(design §7R.18.1)


def test_link_fields_are_always_filled_with_defaults() -> None:
    link = wiki.WikiLink(start=0, end=5, raw="[[a]]", kind="pattern", rule_id="r")
    assert link.label == ""
    assert link.outside is False
    assert link.suggested_path is None
    assert link.status == wiki.KnownWikiLinkStatuses.OK
    required = build_schema()["$defs"]["WikiLink"].get("required", [])
    assert "status" not in required
    assert {v for k, v in vars(wiki.KnownWikiLinkStatuses).items() if k.isupper()} >= {
        "ok",
        "broken",
        "outside",
        "scheme",
    }


def test_preview_link_text_and_template_render_models() -> None:
    preview = wiki.WikiPagePreview.model_validate(
        {
            "page": {"path": "a"},
            "rule_results": [{"rule_id": "no-todo", "action": "reject", "lines": [3]}],
            "would_reject": True,
        }
    )
    assert preview.rule_results[0].lines == [3]
    assert wiki.WikiPagePreviewRequest(content="x").content == "x"
    req = wiki.WikiLinkTextRequest(from_page="a/b", target="c")
    assert req.label is None
    assert req.rule_id is None
    assert wiki.WikiLinkText(rule_id="wikilink", text="[[c|C]]").text == "[[c|C]]"
    render = wiki.WikiTemplateRender(content="본문", missing=["owner"])
    assert render.path is None
    assert wiki.WikiTemplateRenderRequest(values={"owner": "나"}).title is None


def test_template_variables_and_x_ui_variables() -> None:
    tpl = wiki.WikiPageTemplate.model_validate(
        {"id": "d", "file": "d.md", "variables": [{"name": "owner", "title": "담당"}]}
    )
    assert tpl.variables[0].builtin is False
    info = wiki.WikiPageTemplateInfo(
        id="d",
        file="d.md",
        rule_id="r",
        variables=[wiki.WikiTemplateVariable(name="title", builtin=True)],
    )
    assert info.variables[0].builtin is True
    defs = build_schema()["$defs"]
    path_vars = [
        v["name"] for v in defs["WikiPageTemplate"]["properties"]["path"]["x-ui"]["variables"]
    ]
    assert path_vars[:3] == list(wiki.WIKI_TEMPLATE_BUILTIN_VARIABLES)
    access = defs["WikiAccessConfig"]["properties"]
    assert [v["name"] for v in access["path_hint"]["x-ui"]["variables"]] == list(
        wiki.WIKI_PATH_HINT_VARIABLES
    )
    assert [v["name"] for v in access["result_header"]["x-ui"]["variables"]] == list(
        wiki.WIKI_RESULT_HEADER_VARIABLES
    )
    insert = defs["WikiLinkRule"]["properties"]["insert"]["x-ui"]["variables"]
    assert [v["name"] for v in insert] == list(wiki.WIKI_LINK_INSERT_VARIABLES)


def test_enum_tones_rule_refs_widget_and_item_titles() -> None:
    from agent_console_contracts import XUiKeys, x_ui

    assert XUiKeys.VARIABLES == "variables"
    assert XUiKeys.ENUM_TONES == "enum_tones"
    assert x_ui(enum_tones={"a": "danger"}) == {"x-ui": {"enum_tones": {"a": "danger"}}}
    defs = build_schema()["$defs"]
    access = defs["WikiAccessEntry"]["properties"]["access"]["x-ui"]
    assert access["enum_tones"] == {"delete": "danger", "move": "warning"}
    assert set(access["enum_labels"]) == set(wiki.WIKI_ACCESS_OPS)
    action = defs["WikiWriteRule"]["properties"]["action"]
    assert action["x-ui"]["enum_tones"] == {"reject": "danger", "warn": "warning"}
    assert action["examples"] == ["reject", "warn"]
    rules = defs["WikiDefinition"]["properties"]["rules"]["x-ui"]
    assert rules["widget"] == KnownUiWidgets.WIKI_RULE_REFS == "wiki-rule-refs"
    props = defs["WikiRulesDefinition"]["properties"]
    for name in ("write_rules", "lint_rules", "page_templates"):
        assert props[name]["x-ui"]["itemTitle"] == "/id", name


def test_summary_rules_list_and_history_shapes() -> None:
    summary = wiki.WikiSummary.model_validate(
        {
            "id": "w",
            "rules": [{"id": "r", "name": "R", "missing": True}],
            "lint_counts": {"warning": 2},
            "orphans": 1,
            "updated_by": {"kind": "user"},
        }
    )
    assert summary.rules[0].missing is True
    entry = wiki.WikiRuleEntry(kind="write", id="no-todo", rule_id="r", action="reject")
    assert wiki.WikiRulesSummary(entries=[entry]).entries[0].severity is None
    item = wiki.WikiRulesListItem(
        id="r", counts=wiki.WikiRuleCounts(write=2), used_by=[wiki.WikiRef(id="w", name="W")]
    )
    assert item.has_instructions is False
    view = wiki.WikiRulesView.model_validate(
        {"rules": {"kind": "wiki-rules", "id": "r", "name": "R"}, "version_hash": "h"}
    )
    assert view.used_by == []
    history = wiki.WikiHistoryPage.model_validate({"items": [], "pruned": True})
    assert history.pruned is True
    change = wiki.WikiChange.model_validate(
        {
            "wiki": "w",
            "path": "a",
            "version": 1,
            "op": "create",
            "sha256": "h",
            "bytes": 1,
            "author": {"kind": "agent"},
            "at": 1.0,
        }
    )
    assert change.wiki == "w"
    assert wiki.WikiPageList(total=12000, truncated=True).total == 12000
    page = wiki.WikiPageSummary(path="a", orphan=True, home=True)
    assert page.orphan is True
    node = wiki.WikiGraphNode(path="a", home=True, depth=0)
    assert node.depth == 0
    hit = wiki.WikiSearchHit(path="a", marks=[wiki.WikiTextRange(start=0, end=2)])
    assert hit.marks[0].end == 2
    report = wiki.WikiLintReport(generated_at=1.0, counts={"error": 1})
    assert report.counts == {"error": 1}
    assert wiki.WikiLintDefaults(write_rules=False).write_rules is False
    assert wiki.WikiLinkRule(id="w", kind="pattern", insert="[[{target}]]").insert


def test_import_result_items_and_not_found_details() -> None:
    result = wiki.WikiImportResult.model_validate(
        {"items": [{"path": "a", "status": "renamed", "to": "a-2"}], "dry_run": True}
    )
    assert result.items[0].to == "a-2"
    assert not {"created", "overwritten", "renamed", "skipped"} & set(
        wiki.WikiImportResult.model_fields
    )
    assert {v for k, v in vars(wiki.KnownWikiImportStatuses).items() if k.isupper()} >= {
        "created",
        "skipped",
        "overwritten",
        "renamed",
        "rejected",
    }
    details = wiki.WikiPageNotFoundDetails(path="a", has_history=True)
    assert details.has_history is True
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_LINK_INSERT_UNAVAILABLE] == 422
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.WIKI_VERSION_NOT_FOUND] == 404
    for code in (
        "wiki.link_insert_unavailable",
        "wiki.home_missing",
        "wiki.rule_violation",
        "wiki.version_not_found",
    ):
        assert code in vars(KnownIssueCodes).values(), code
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_WIKI_RULE_ENTRY_KINDS"] == {
        "WRITE": "write",
        "LINT": "lint",
        "TEMPLATE": "template",
    }
    assert constants["WIKI_TEMPLATE_BUILTIN_VARIABLES"] == ["title", "slug", "date"]
