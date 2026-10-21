"""저장 전 검사 `validate_resource`·`scrub_issue_values`(1R.37)."""

from __future__ import annotations

from typing import Any

from agent_console_contracts import Issue, Resource, ResourceAttachment, ResourceTypeDescriptor
from agent_console_registry import Registry
from agent_console_resources import (
    OVERRIDE_SECRET_SUSPECTED,
    SECRET_MASK,
    SECRET_SCHEMA_KEY,
    Content,
    ContributeContext,
    Contribution,
    InMemoryResources,
    MaskedResources,
    ResourceType,
    SchemaResourceType,
    declarative_type_from_data,
    find_plain_secrets,
    mask_attachment,
    mask_plain_secrets,
    new_resource_types,
    scrub_issue_values,
    validate_attachment,
    validate_resource,
)
from agent_console_resources._validate import value_at

SECRET = "sk-live-123456"


class LeakyType(SchemaResourceType):
    """예제 플러그인 종류: 평문 값을 실수로 메시지에 넣는다(검사기가 지워야 한다)."""

    descriptor = ResourceTypeDescriptor(
        id="leaky",
        title="새는 종류",
        config_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        return [
            Issue(
                severity="error",
                code="example.plain",
                message=f"평문 {resource.config['env'][key]} 금지",
                path=pointer,
            )
            for pointer, key in (
                (p, p.rsplit("/", 1)[1]) for p in find_plain_secrets(resource.config, ("env",))
            )
        ]

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        return []


class BrokenType(LeakyType):
    descriptor = ResourceTypeDescriptor(id="broken", title="깨진 종류")

    def validate(self, resource: Resource) -> list[Issue]:
        raise RuntimeError(SECRET)


def _types() -> Registry[ResourceType]:
    types = new_resource_types()
    types.register("leaky", LeakyType())
    types.register("broken", BrokenType())
    return types


def test_value_at() -> None:
    doc = {"env": {"a/b": "x", "l": [1, {"k": "v"}]}}
    assert value_at(doc, "/env/a~1b") == "x"
    assert value_at(doc, "/env/l/1/k") == "v"
    assert value_at(doc, "/env/l/9") is None
    assert value_at(doc, "/nope") is None
    assert value_at(doc, None) is None
    assert value_at(doc, "env") is None


def test_validate_resource_scrubs_values_from_messages() -> None:
    res = Resource(id="r", type="leaky", name="r", config={"env": {"API_KEY": SECRET}, "n": "x"})
    issues = validate_resource(res, _types())
    codes = {i.code for i in issues}
    assert codes == {"example.plain", "resource.invalid_config"}
    plain = next(i for i in issues if i.code == "example.plain")
    assert plain.path == "/env/API_KEY"
    assert SECRET not in plain.message
    assert "***" in plain.message
    assert all(SECRET not in i.model_dump_json() for i in issues)


def test_validate_resource_unknown_and_failing_type() -> None:
    types = _types()
    unknown = validate_resource(Resource(id="r", type="nope", name="r"), types)
    assert [(i.severity, i.code) for i in unknown] == [("warning", "resource.unknown_type")]
    failed = validate_resource(Resource(id="r", type="broken", name="r"), types)
    assert [(i.severity, i.code) for i in failed] == [("error", "resource.type_failed")]
    assert SECRET not in failed[0].message


def test_scrub_keeps_short_values_and_unrelated_issues() -> None:
    issue = Issue(severity="error", code="c", message="a ab abc", path="/v")
    assert scrub_issue_values([issue], {"v": "ab"})[0].message == "a ab abc"
    assert scrub_issue_values([issue], {"v": "abc"})[0].message == "a ab ***"
    same = Issue(severity="info", code="c", message="m")
    assert scrub_issue_values([same], {})[0] is same


def test_declarative_type_keeps_x_secret_hint() -> None:
    """선언형 종류도 config 스키마에 `x-secret`을 달 수 있다(디스크립터에 그대로).

    2R.4: `pattern` 없이도 `x-secret` 위치의 평문은 일반 규칙으로 거부된다(`resource.plain_secret`).
    """
    data = {
        "id": "api",
        "title": "API",
        "config_schema": {
            "type": "object",
            "properties": {"token": {"type": "string", SECRET_SCHEMA_KEY: True}},
        },
        "contributes": [{"slot": "s", "template": "{name}"}],
    }
    item = declarative_type_from_data(data)
    props = item.descriptor.config_schema["properties"]
    assert props["token"][SECRET_SCHEMA_KEY] is True
    [issue] = item.validate(Resource(id="r", type="api", name="r", config={"token": "plain-x"}))
    assert (issue.severity, issue.code, issue.path) == ("error", "resource.plain_secret", "/token")
    assert "plain-x" not in issue.model_dump_json()
    ref = Resource(id="r", type="api", name="r", config={"token": "secret://T"})
    assert item.validate(ref) == []


def test_schema_type_rejects_plain_at_nested_x_secret_positions() -> None:
    """일반 규칙은 `mask_plain_secrets`와 같은 키워드를 따라간다(값 없는 이슈, 위치만)."""
    data = {
        "id": "nested",
        "title": "N",
        "config_schema": {
            "type": "object",
            "properties": {
                "env": {"type": "object", "additionalProperties": {SECRET_SCHEMA_KEY: True}},
                "list": {"type": "array", "items": {SECRET_SCHEMA_KEY: True}},
                "both": {"allOf": [{"properties": {"t": {SECRET_SCHEMA_KEY: True}}}]},
            },
        },
        "contributes": [{"slot": "s", "template": "{name}"}],
    }
    item = declarative_type_from_data(data)
    config = {
        "env": {"A": "p1", "B": "secret://B", "C": None},
        "list": ["secret://L", 5],
        "both": {"t": "p2"},
    }
    issues = item.validate(Resource(id="r", type="nested", name="r", config=config))
    assert [(i.code, i.path) for i in issues] == [
        ("resource.plain_secret", "/env/A"),
        ("resource.plain_secret", "/list/1"),
        ("resource.plain_secret", "/both/t"),
    ]


def test_mask_plain_secrets_follows_schema() -> None:
    schema = {
        "type": "object",
        "properties": {
            "env": {"type": "object", "additionalProperties": {SECRET_SCHEMA_KEY: True}},
            "list": {"type": "array", "items": {SECRET_SCHEMA_KEY: True}},
            "both": {"allOf": [{"properties": {"t": {SECRET_SCHEMA_KEY: True}}}]},
            "name": {"type": "string"},
        },
    }
    value: dict[str, Any] = {
        "env": {"A": SECRET, "B": "secret://B", "C": None},
        "list": [SECRET, "secret://L"],
        "both": {"t": 5, "u": "keep"},
        "name": SECRET,
    }
    masked = mask_plain_secrets(value, schema)
    assert masked == {
        "env": {"A": SECRET_MASK, "B": "secret://B", "C": None},
        "list": [SECRET_MASK, "secret://L"],
        "both": {"t": SECRET_MASK, "u": "keep"},
        "name": SECRET,  # 표시 없는 칸은 그대로
    }
    assert value["env"]["A"] == SECRET  # 원본 불변


def test_validate_attachment_and_mask_attachment() -> None:
    types = new_resource_types()
    types.register("leaky", LeakyType())
    lookup = InMemoryResources(
        [Resource(id="r", type="leaky", name="r", config={"env": {"A": "secret://A"}})]
    )
    att = ResourceAttachment(ref="r", config_override={"env": {"A": SECRET}})
    issues = validate_attachment(att, types=types, resources=lookup, path="/x/0")
    assert [(i.code, i.path) for i in issues] == [("example.plain", "/x/0/config_override/env/A")]
    assert SECRET not in issues[0].message
    custom = validate_attachment(
        att, types=types, resources=lookup, override_path="/e/config/ov", ref_path="/n/pick"
    )
    assert [i.path for i in custom] == ["/e/config/ov/env/A"]
    assert validate_attachment(ResourceAttachment(ref="r"), types=types, resources=lookup) == []
    unknown = InMemoryResources([Resource(id="r", type="nope", name="r")])
    [warn] = validate_attachment(att, types=types, resources=unknown, ref_path="/n/pick")
    assert (warn.code, warn.path) == ("resource.unknown_type", "/n/pick")
    # LeakyType 스키마에는 x-secret이 없으므로 가리기는 그대로 둔다
    assert mask_attachment(att, types=types, resources=lookup) is att
    wrapped = MaskedResources(lookup, types)
    assert wrapped.get_resource("missing") is None
    assert wrapped.read_content(Resource(id="r", type="leaky", name="r")) is None


def test_validate_attachment_unknown_resource_uses_suspicion_rule() -> None:
    types = new_resource_types()
    att = ResourceAttachment(
        ref="later",
        config_override={"env": {"API_KEY": SECRET, "PATH": "/bin", "T": "secret://T"}, "n": 1},
    )
    issues = validate_attachment(att, types=types, resources=InMemoryResources([]), path="/r/0")
    assert [(i.severity, i.code, i.path) for i in issues] == [
        ("warning", "resource.not_found", "/r/0/ref"),
        ("error", OVERRIDE_SECRET_SUSPECTED, "/r/0/config_override/env/API_KEY"),
    ]
    assert all(SECRET not in i.model_dump_json() for i in issues)
