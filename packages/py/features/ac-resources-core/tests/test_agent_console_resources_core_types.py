"""기본 4종: entry point 등록, 칸 값 형식, 팀 공용 + 노드 지침 순서, 비밀 참조, 경로 안전."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from agent_console_contracts import Resource, ResourceAttachment, ResourceContentRef
from agent_console_registry import Registry
from agent_console_resources import (
    SECRET_SCHEMA_KEY,
    AttachmentLayer,
    InMemoryResources,
    ResourceType,
    compose_bundle,
    list_descriptors,
    load_resource_types,
    new_resource_types,
)
from agent_console_resources_core import (
    FileType,
    InstructionType,
    McpServerType,
    ToolPermissionType,
    safe_relative_name,
)

CORE_IDS = ["file", "instruction", "mcp-server", "tool-permission"]


def test_imports_standalone() -> None:
    module = importlib.import_module("agent_console_resources_core")
    for name in module.__all__:
        assert hasattr(module, name), name


def test_installed_entry_points_register_all_four() -> None:
    reg = new_resource_types()
    reports = load_resource_types(reg, enabled=set(CORE_IDS))
    loaded = sorted(r.key for r in reports if r.status == "loaded" and r.key)
    assert loaded == CORE_IDS
    for desc in list_descriptors(reg):
        assert desc.contributes, desc.id
        assert desc.declarative is False


def test_removing_a_core_type_hides_it_and_skips_its_resources() -> None:
    reg = new_resource_types()
    load_resource_types(reg, enabled={"instruction"})
    assert [d.id for d in list_descriptors(reg)] == ["instruction"]
    lookup = InMemoryResources(
        [
            _instr("i", "지침"),
            Resource(id="t", type="tool-permission", name="t", config={"tools": ["Read"]}),
        ],
        {"i": "본문"},
    )
    result = compose_bundle(
        [AttachmentLayer("team", [ResourceAttachment(ref="i"), ResourceAttachment(ref="t")])],
        types=reg,
        resources=lookup,
    )
    assert result.bundle.slots == {"instructions": ["본문"]}
    assert [i.code for i in result.issues] == ["resource.unknown_type"]


def _types() -> Registry[ResourceType]:
    reg = new_resource_types()
    for item in (InstructionType(), FileType(), McpServerType(), ToolPermissionType()):
        reg.register(item.descriptor.id, item)
    return reg


def _instr(rid: str, title: str, **config: Any) -> Resource:
    return Resource(
        id=rid,
        type="instruction",
        name=rid,
        config={"title": title, **config},
        content=ResourceContentRef(file="content.md", media_type="text/markdown"),
    )


# ---------------------------------------------------------------- instruction
def test_team_shared_instruction_then_node_instruction_in_order() -> None:
    lookup = InMemoryResources(
        [_instr("team-claude-md", "CLAUDE.md"), _instr("pl-guide", "PL 지침", heading=True)],
        {"team-claude-md": "팀 규칙", "pl-guide": "계획부터 세운다"},
    )
    result = compose_bundle(
        [
            AttachmentLayer("common", None),
            AttachmentLayer("team", [ResourceAttachment(ref="team-claude-md")]),
            AttachmentLayer("agent", None),
            AttachmentLayer("node", [ResourceAttachment(ref="pl-guide")]),
        ],
        types=_types(),
        resources=lookup,
    )
    assert result.bundle.slots == {"instructions": ["팀 규칙", "## PL 지침\n\n계획부터 세운다"]}
    assert [(s.ref, s.layer, s.resource_type) for s in result.bundle.sources["instructions"]] == [
        ("team-claude-md", "team", "instruction"),
        ("pl-guide", "node", "instruction"),
    ]
    assert result.issues == ()


def test_instruction_replace_by_title_and_prepend_and_inline_text() -> None:
    lookup = InMemoryResources(
        [
            _instr("team-md", "CLAUDE.md"),
            _instr("my-md", "CLAUDE.md"),
            Resource(
                id="first",
                type="instruction",
                name="first",
                config={"text": "맨 앞", "position": "prepend"},
            ),
            Resource(id="empty", type="instruction", name="empty", config={}),
        ],
        {"team-md": "팀", "my-md": "내 것"},
    )
    result = compose_bundle(
        [
            AttachmentLayer("team", [ResourceAttachment(ref="team-md")]),
            AttachmentLayer(
                "node",
                [
                    ResourceAttachment(ref="my-md", mode="replace"),
                    ResourceAttachment(ref="first"),
                    ResourceAttachment(ref="empty"),
                ],
            ),
        ],
        types=_types(),
        resources=lookup,
    )
    assert result.bundle.slots["instructions"] == ["맨 앞", "내 것"]
    assert [i.code for i in result.issues] == ["resource.content_missing"]


def test_instruction_rejects_unknown_config() -> None:
    issues = InstructionType().validate(_instr("x", "t", position="middle"))
    assert [i.code for i in issues] == ["resource.invalid_config"]


# ---------------------------------------------------------------- mcp-server
def _mcp(**config: Any) -> Resource:
    return Resource(id="m", type="mcp-server", name="m", config=config)


def test_mcp_server_secret_refs_only_and_value_not_leaked() -> None:
    bad = _mcp(name="gh", command="gh-mcp", env={"GITHUB_TOKEN": "ghp_supersecret"})
    issues = McpServerType().validate(bad)
    codes = {i.code for i in issues}
    assert "resource.plain_secret" in codes
    plain = next(i for i in issues if i.code == "resource.plain_secret")
    assert plain.path == "/env/GITHUB_TOKEN"
    assert all("ghp_supersecret" not in i.model_dump_json() for i in issues)

    lookup = InMemoryResources([bad])
    result = compose_bundle(
        [AttachmentLayer("t", [ResourceAttachment(ref="m")])], types=_types(), resources=lookup
    )
    assert result.bundle.slots == {}
    assert "ghp_supersecret" not in result.bundle.model_dump_json()


def test_mcp_server_entries_keep_secret_refs() -> None:
    lookup = InMemoryResources(
        [
            Resource(
                id="local",
                type="mcp-server",
                name="local",
                config={
                    "name": "fs",
                    "command": "fs-mcp",
                    "args": ["--ro"],
                    "env": {"KEY": "secret://fs_key"},
                },
            ),
            Resource(
                id="remote",
                type="mcp-server",
                name="remote",
                config={
                    "name": "gh",
                    "transport": "http",
                    "url": "https://example.invalid/mcp",
                    "headers": {"Authorization": "secret://gh_token"},
                },
            ),
        ]
    )
    result = compose_bundle(
        [AttachmentLayer("t", [ResourceAttachment(ref="local"), ResourceAttachment(ref="remote")])],
        types=_types(),
        resources=lookup,
        accepted_slots=["instructions"],
    )
    assert result.bundle.slots["mcp_servers"] == [
        {
            "name": "fs",
            "type": "stdio",
            "command": "fs-mcp",
            "args": ["--ro"],
            "env": {"KEY": "secret://fs_key"},
        },
        {
            "name": "gh",
            "type": "http",
            "url": "https://example.invalid/mcp",
            "headers": {"Authorization": "secret://gh_token"},
        },
    ]
    assert [i.code for i in result.issues] == ["resource.slot_unsupported"]


@pytest.mark.parametrize(
    "config",
    [
        {"name": "a"},  # stdio인데 command 없음
        {"name": "a", "transport": "sse"},  # url 없음
        {"name": "bad name", "command": "x"},
        {"name": "a", "command": "x", "unknown": 1},
    ],
)
def test_mcp_server_schema_rejects(config: dict[str, Any]) -> None:
    assert any(i.severity == "error" for i in McpServerType().validate(_mcp(**config)))


# ---------------------------------------------------------------- file
def test_file_entries_and_binary_content() -> None:
    lookup = InMemoryResources(
        [
            Resource(
                id="spec",
                type="file",
                name="spec",
                content=ResourceContentRef(file="docs/spec.md", media_type="text/markdown"),
            ),
            Resource(
                id="bin",
                type="file",
                name="bin",
                config={"name": "data/blob.bin"},
                content=ResourceContentRef(file="blob"),
            ),
        ],
        {"spec": "# 스펙", "bin": b"\xff\x00"},
    )
    result = compose_bundle(
        [AttachmentLayer("t", [ResourceAttachment(ref="spec"), ResourceAttachment(ref="bin")])],
        types=_types(),
        resources=lookup,
    )
    assert result.bundle.slots["files"] == [
        {
            "name": "spec.md",
            "content": "# 스펙",
            "encoding": "utf-8",
            "media_type": "text/markdown",
        },
        {"name": "data/blob.bin", "content": "/wA=", "encoding": "base64"},
    ]


@pytest.mark.parametrize("name", ["../x", "/etc/passwd", "C:/x", "a\\b", "a/./b", ""])
def test_file_rejects_unsafe_names(name: str) -> None:
    assert not safe_relative_name(name)
    res = Resource(
        id="f", type="file", name="f", config={"name": name}, content=ResourceContentRef(file="c")
    )
    assert any(i.severity == "error" for i in FileType().validate(res))


def test_file_requires_content() -> None:
    codes = [i.code for i in FileType().validate(Resource(id="f", type="file", name="f"))]
    assert codes == ["resource.content_missing"]


# ---------------------------------------------------------------- tool-permission
def test_tool_permission_entries() -> None:
    lookup = InMemoryResources(
        [
            Resource(
                id="ro",
                type="tool-permission",
                name="ro",
                config={"tools": ["Read", "Grep"], "disallowed_tools": ["Bash"]},
            ),
            Resource(id="cmd", type="tool-permission", name="cmd", config={"commands": ["git"]}),
        ]
    )
    result = compose_bundle(
        [
            AttachmentLayer("team", [ResourceAttachment(ref="ro")]),
            AttachmentLayer("node", [ResourceAttachment(ref="cmd")]),
        ],
        types=_types(),
        resources=lookup,
    )
    assert result.bundle.slots["tools"] == [
        {"tools": ["Read", "Grep"], "disallowed_tools": ["Bash"]},
        {"commands": ["git"]},
    ]
    empty = Resource(id="e", type="tool-permission", name="e", config={})
    assert any(i.severity == "error" for i in ToolPermissionType().validate(empty))


@pytest.mark.parametrize("name", ["a\x00b", "a\nb", "tab\there", "x\x7f", "c1\x85"])
def test_file_rejects_control_characters(name: str) -> None:
    assert not safe_relative_name(name)


def test_invalid_config_messages_do_not_echo_values() -> None:
    res = Resource(
        id="m",
        type="mcp-server",
        name="m",
        config={"name": "bad name sk-LEAK", "transport": "sk-LEAK", "url": "u"},
    )
    issues = McpServerType().validate(res)
    assert {i.path for i in issues if i.code == "resource.invalid_config"} >= {
        "/name",
        "/transport",
    }
    assert "sk-LEAK" not in repr(issues)


def test_mcp_server_secret_fields_are_marked_in_schema() -> None:
    """화면이 문구가 아닌 구조화 힌트(`x-secret`)로 비밀 칸을 알 수 있다(1R.37 후속)."""
    props = McpServerType.descriptor.config_schema["properties"]
    for name in ("env", "headers"):
        assert props[name]["additionalProperties"][SECRET_SCHEMA_KEY] is True
    marked = [k for k, v in props.items() if SECRET_SCHEMA_KEY in str(v)]
    assert sorted(marked) == ["env", "headers"]
    # 주석은 검사에 영향이 없다(참조 값은 통과)
    ok = _mcp(name="gh", command="gh-mcp", env={"T": "secret://T"}, headers={"A": "secret://A"})
    assert [i for i in McpServerType().validate(ok) if i.severity == "error"] == []
