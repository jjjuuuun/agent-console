"""2R.12: `skill`(여러 파일)·`rule`(경로 조건 지침)·`hook`(명령형) 종류 — 등록, 칸 값, 대체 칸,
이벤트 이름 자유 문자열, 명령 평문 비밀 거부."""

from __future__ import annotations

import base64
from typing import Any

from agent_console_contracts import Resource, ResourceAttachment
from agent_console_resources import (
    PLAIN_SECRET,
    SLOT_FALLBACK,
    AttachmentLayer,
    InMemoryResources,
    compose_bundle,
    list_descriptors,
    load_resource_types,
    new_resource_types,
    validate_resource,
)
from agent_console_resources_core import (
    DEFAULT_PATHS_HEADER,
    HookType,
    RuleType,
    SkillType,
    render_rule_file,
)

NEW_IDS = ["hook", "rule", "skill"]


def _types() -> Any:
    reg = new_resource_types()
    load_resource_types(reg, enabled={*NEW_IDS, "instruction"})
    return reg


def _compose(resources: InMemoryResources, *refs: str, accepted: list[str] | None = None) -> Any:
    return compose_bundle(
        [AttachmentLayer("node", [ResourceAttachment(ref=r) for r in refs])],
        types=_types(),
        resources=resources,
        accepted_slots=accepted,
    )


def test_entry_points_register_new_types_with_descriptors() -> None:
    reg = new_resource_types()
    load_resource_types(reg, enabled=set(NEW_IDS))
    descriptors = {d.id: d for d in list_descriptors(reg)}
    assert sorted(descriptors) == NEW_IDS
    skill = descriptors["skill"]
    assert skill.content is not None
    assert skill.content.multi_file is True
    assert skill.contributes == ["skills"]
    assert descriptors["rule"].contributes == ["rules", "instructions"]
    assert descriptors["hook"].content is None
    assert descriptors["hook"].contributes == ["hooks"]


def test_hook_event_is_free_string_with_examples_only() -> None:
    schema = HookType().descriptor.config_schema
    event = schema["properties"]["event"]
    assert event["type"] == "string"
    assert "enum" not in event
    assert event["examples"]  # 제안 목록(데이터)
    custom = HookType(event_examples=["OnSomething"]).descriptor.config_schema
    assert custom["properties"]["event"]["examples"] == ["OnSomething"]
    resource = Resource(
        id="h", type="hook", name="h", config={"event": "AnyMadeUpEvent", "command": "lint"}
    )
    assert [i for i in HookType().validate(resource) if i.severity == "error"] == []


def test_skill_contributes_files_from_multi_file_body() -> None:
    lookup = InMemoryResources(
        [Resource(id="review", type="skill", name="리뷰", config={"name": "code-review"})],
        {
            "review": {
                "SKILL.md": "---\nname: code-review\n---\n본문".encode(),
                "scripts/run.sh": b"#!/bin/sh\necho hi\n",
                "bin.dat": b"\xff\xfe",
            }
        },
    )
    result = _compose(lookup, "review")
    (item,) = result.bundle.slots["skills"]
    assert item["name"] == "code-review"
    names = [f["name"] for f in item["files"]]
    assert names == ["SKILL.md", "bin.dat", "scripts/run.sh"]
    by_name = {f["name"]: f for f in item["files"]}
    assert by_name["SKILL.md"]["media_type"] == "text/markdown"
    assert by_name["bin.dat"]["encoding"] == "base64"
    assert base64.b64decode(by_name["bin.dat"]["content"]) == b"\xff\xfe"
    assert result.bundle.sources["skills"][0].resource_type == "skill"


def test_skill_name_defaults_to_id_and_is_validated() -> None:
    ok = Resource(id="my-skill", type="skill", name="s")
    assert [i for i in SkillType().validate(ok) if i.severity == "error"] == []
    bad = Resource(id="s", type="skill", name="s", config={"name": "has space"})
    assert any(i.path == "/name" for i in SkillType().validate(bad))


def test_skill_without_files_contributes_nothing() -> None:
    lookup = InMemoryResources([Resource(id="empty", type="skill", name="e")], {"empty": {}})
    assert "skills" not in _compose(lookup, "empty").bundle.slots


def test_rule_item_has_paths_instruction_and_rule_file() -> None:
    rule = Resource.model_validate(
        {
            "id": "api-rules",
            "type": "rule",
            "name": "API 규칙",
            "config": {"paths": ["src/api/**/*.ts"]},
            "content": {"file": "content.md"},
        }
    )
    result = _compose(InMemoryResources([rule], {"api-rules": "검증을 먼저 한다"}), "api-rules")
    (item,) = result.bundle.slots["rules"]
    assert item["paths"] == ["src/api/**/*.ts"]
    assert item["text"] == "검증을 먼저 한다"
    header = DEFAULT_PATHS_HEADER.replace("{paths}", "src/api/**/*.ts")
    assert item["instruction"] == f"{header}\n\n검증을 먼저 한다"
    (file,) = item["files"]
    assert file["name"] == ".claude/rules/api-rules.md"
    assert file["content"].startswith('---\npaths:\n  - "src/api/**/*.ts"\n---\n')


def test_rule_falls_back_to_instructions_when_backend_lacks_rules() -> None:
    rule = Resource(
        id="r",
        type="rule",
        name="r",
        config={"text": "짧게", "paths": ["a/**", "b/*.md"], "paths_header": "경로 {paths}:"},
    )
    result = _compose(InMemoryResources([rule]), "r", accepted=["instructions"])
    assert result.bundle.slots == {"instructions": ["경로 a/**, b/*.md:\n\n짧게"]}
    assert any(i.code == SLOT_FALLBACK for i in result.issues)


def test_rule_without_paths_is_plain_text_and_render_helper() -> None:
    rule = Resource(id="r", type="rule", name="r", config={"text": "항상"})
    item = _compose(InMemoryResources([rule]), "r").bundle.slots["rules"][0]
    assert item["instruction"] == "항상"
    assert render_rule_file([], "x") == "x"
    assert render_rule_file(['a"b'], "x").splitlines()[2] == '  - "a\\"b"'


def test_rule_rejects_unsafe_rules_dir() -> None:
    bad = Resource(id="r", type="rule", name="r", config={"text": "x", "rules_dir": "../out"})
    assert any(i.code == "resource.unsafe_path" for i in RuleType().validate(bad))


def test_hook_contributes_item() -> None:
    hook = Resource(
        id="fmt",
        type="hook",
        name="포맷",
        config={
            "event": "PostToolUse",
            "matcher": "Write|Edit",
            "command": "prettier --write",
            "timeout_seconds": 5,
        },
    )
    result = _compose(InMemoryResources([hook]), "fmt")
    assert result.bundle.slots["hooks"] == [
        {
            "name": "fmt",
            "event": "PostToolUse",
            "matcher": "Write|Edit",
            "command": "prettier --write",
            "timeout_seconds": 5,
        }
    ]


def test_hook_command_with_plain_secret_is_rejected_without_value() -> None:
    token = "ghp_" + "a" * 36
    hook = Resource(
        id="h",
        type="hook",
        name="h",
        config={"event": "Stop", "command": f"notify --token {token}"},
    )
    issues = validate_resource(hook, _types())
    secret = [i for i in issues if i.code == PLAIN_SECRET]
    assert secret
    assert secret[0].path == "/command"
    assert secret[0].severity == "error"
    assert token not in str([i.model_dump() for i in issues])
    # 오류가 있는 첨부는 묶음에서 빠진다
    assert "hooks" not in _compose(InMemoryResources([hook]), "h").bundle.slots


def test_hook_requires_event_and_command() -> None:
    issues = HookType().validate(Resource(id="h", type="hook", name="h", config={}))
    assert {i.code for i in issues if i.severity == "error"} == {"resource.invalid_config"}
