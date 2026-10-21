"""`.claude` 형식 변환: 읽기·쓰기와 왕복(render(parse(x))가 의미상 같다)."""

from __future__ import annotations

import json

import pytest

from agent_console_claude_format import (
    AgentFile,
    ClaudeLayout,
    ClaudeMapping,
    HookSpec,
    agent_document,
    agent_file_from_document,
    dump_json,
    mcp_config_from_entry,
    mcp_entry_from_config,
    parse_agent_md,
    parse_env_ref,
    parse_frontmatter,
    parse_hooks,
    parse_mcp,
    parse_rule,
    parse_settings,
    parse_skill,
    render_agent_md,
    render_frontmatter,
    render_mcp,
    render_rule,
    render_settings,
    render_skill,
    str_list,
    valid_skill_name,
)

AGENT_MD = """---
name: code-reviewer
description: 코드 리뷰를 맡긴다
tools: Read, Grep, Bash(git diff:*)
disallowedTools:
  - Write
model: sonnet
color: blue
skills:
  - api-conventions
---

너는 리뷰어다.

- 꼼꼼히 본다.
"""


def test_frontmatter_basics() -> None:
    assert parse_frontmatter("no front") == ({}, "no front")
    assert parse_frontmatter("---\n: [bad\n---\nx")[0] == {}
    assert parse_frontmatter("---\n---\nbody") == ({}, "body")
    assert render_frontmatter({}, "\n\nbody\n\n") == "body\n"
    text = render_frontmatter({"z": 1, "a": "한글"}, "본문")
    assert text.index("z:") < text.index("a:")  # 순서 유지
    assert "한글" in text
    assert parse_frontmatter(text) == ({"z": 1, "a": "한글"}, "\n본문\n")
    assert str_list("a, b,,c") == ["a", "b", "c"]
    assert str_list(["x", " "]) == ["x"]
    assert str_list(3) is None
    assert dump_json({"가": 1}).endswith("}\n")


def test_mapping_and_layout_are_data() -> None:
    assert ClaudeMapping.from_options(None) == ClaudeMapping()
    custom = ClaudeMapping.from_options({"skill_type": "my-skill"})
    assert custom.skill_type == "my-skill"
    with pytest.raises(ValueError, match="모르는 키"):
        ClaudeMapping.from_options({"nope": "x"})
    with pytest.raises(ValueError, match="문자열"):
        ClaudeMapping.from_options({"skill_type": ""})
    layout = ClaudeLayout.from_options({"claude_dir": ".my"})
    assert layout.in_claude_dir("agents", "a.md") == ".my/agents/a.md"


def test_agent_parse_render_roundtrip() -> None:
    agent = parse_agent_md(AGENT_MD, default_name="fallback")
    assert agent.name == "code-reviewer"
    assert agent.tools == ["Read", "Grep", "Bash(git diff:*)"]
    assert agent.disallowed_tools == ["Write"]
    assert agent.model == "sonnet"
    assert agent.prompt.startswith("너는 리뷰어다.")
    assert agent.extra == {"color": "blue", "skills": ["api-conventions"]}
    again = parse_agent_md(render_agent_md(agent), default_name="x")
    assert again == agent


def test_agent_inherit_model_and_no_frontmatter() -> None:
    agent = parse_agent_md("---\nmodel: inherit\n---\nhi", default_name="a")
    assert agent.model is None
    assert agent.name == "a"
    plain = parse_agent_md("just a prompt", default_name="p")
    assert plain.prompt == "just a prompt"
    assert plain.tools is None


def test_agent_document_roundtrip() -> None:
    agent = parse_agent_md(AGENT_MD, default_name="x")
    doc = agent_document(agent)
    assert doc["kind"] == "agent"
    assert doc["system_prompt"] == agent.prompt
    assert doc["disallowed_tools"] == ["Write"]
    assert doc["attributes"]["claude_frontmatter"] == {
        "color": "blue",
        "skills": ["api-conventions"],
    }
    back, dropped = agent_file_from_document({**doc, "id": "code-reviewer"})
    assert back == agent
    assert dropped == []
    _, dropped = agent_file_from_document({"id": "a", "name": "A", "limits": {}, "backend": "x"})
    assert dropped == ["backend", "limits"]
    custom = agent_document(AgentFile(name="n"), mapping=ClaudeMapping(agent_kind="persona"))
    assert custom["kind"] == "persona"
    assert "system_prompt" not in custom  # 생략 = 상속


def test_skill_parse_render() -> None:
    files = {
        "SKILL.md": b"---\nname: PDF tools\ndescription: pdf\n---\n# Use\n",
        "scripts/run.py": b"print(1)\n",
    }
    skill = parse_skill("pdf", files)
    assert (skill.name, skill.title, skill.description) == ("pdf", "PDF tools", "pdf")
    assert render_skill(skill.name, skill.files) == files
    made = render_skill("x", {"a.txt": b"a"}, description="d")
    assert parse_frontmatter(made["SKILL.md"].decode())[0] == {"name": "x", "description": "d"}
    assert valid_skill_name("pdf-1.2")
    assert not valid_skill_name("../x")


def test_rule_roundtrip() -> None:
    text = '---\npaths:\n  - "src/**/*.ts"\n  - "a b/*"\n---\n\n규칙 본문\n'
    rule = parse_rule(text)
    assert rule.paths == ["src/**/*.ts", "a b/*"]
    assert rule.body == "규칙 본문\n"
    assert render_rule(rule.paths, rule.body) == text
    assert parse_rule(render_rule([], "본문")) == parse_rule("본문")
    assert parse_rule("---\npaths: src/*.py\ndescription: d\n---\nx").extra == {"description": "d"}


SETTINGS = {
    "permissions": {"allow": ["Read", "Bash(npm test)"], "deny": ["WebFetch"]},
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": "./check.sh", "timeout": 30},
                    {"type": "http", "url": "http://x"},
                ],
            }
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "echo done", "args": ["-n"]}]}],
        "Odd": "nope",
    },
}


def test_settings_parse_and_render() -> None:
    parsed = parse_settings(SETTINGS)
    assert parsed.allow == ["Read", "Bash(npm test)"]
    assert parsed.deny == ["WebFetch"]
    assert parsed.hooks == [
        HookSpec(event="PreToolUse", command="./check.sh", matcher="Bash", timeout_seconds=30),
        HookSpec(event="Stop", command="echo done", extra={"args": ["-n"]}),
    ]
    assert parsed.skipped_hooks == ["/hooks/PreToolUse/0/hooks/1", "/hooks/Odd"]
    rendered = render_settings(allow=parsed.allow, deny=parsed.deny, hooks=parsed.hooks)
    again = parse_settings(json.loads(dump_json(rendered)))
    assert again.allow == parsed.allow
    assert again.hooks == parsed.hooks
    assert render_settings() == {}
    assert parse_settings([]).hooks == []


def test_hooks_group_by_event_and_matcher() -> None:
    hooks = [
        HookSpec("PreToolUse", "a", "Bash"),
        HookSpec("PreToolUse", "b", "Bash"),
        HookSpec("PreToolUse", "c", "Edit"),
    ]
    from agent_console_claude_format import render_hooks

    out = render_hooks(hooks)
    assert [g.get("matcher") for g in out["PreToolUse"]] == ["Bash", "Edit"]
    assert len(out["PreToolUse"][0]["hooks"]) == 2
    assert parse_hooks(out, base="")[0] == hooks


def test_mcp_conversion_secrets() -> None:
    data = {
        "mcpServers": {
            "gh": {"command": "npx", "args": ["gh-mcp"], "env": {"TOKEN": "${GH_TOKEN}"}},
            "web": {"type": "http", "url": "https://x/mcp", "headers": {"A": "plain"}},
            "bad": "skip",
        }
    }
    servers = parse_mcp(data)
    assert sorted(servers) == ["gh", "web"]
    config = mcp_config_from_entry("gh", servers["gh"])
    assert config == {
        "name": "gh",
        "transport": "stdio",
        "command": "npx",
        "args": ["gh-mcp"],
        "env": {"TOKEN": "${GH_TOKEN}"},
    }
    assert parse_env_ref("${GH_TOKEN}") == "GH_TOKEN"
    assert parse_env_ref("plain") is None
    entry = mcp_entry_from_config(
        {
            "name": "gh",
            "transport": "stdio",
            "command": "npx",
            "args": ["--token=secret://GH_ARG"],
            "env": {"TOKEN": "secret://GH_TOKEN", "PLAIN": "abc"},
        },
        fallback_name="r",
    )
    assert entry.entry["env"] == {"TOKEN": "${GH_TOKEN}"}
    assert entry.entry["args"] == ["--token=${GH_ARG}"]
    assert entry.omitted == ["env/PLAIN"]
    omit = mcp_entry_from_config(
        {"transport": "http", "url": "https://x", "headers": {"A": "secret://K"}},
        fallback_name="r",
        secret_style="omit",
    )
    assert omit.name == "r"
    assert "headers" not in omit.entry
    assert omit.omitted == ["headers/A"]
    assert render_mcp({"gh": entry.entry}) == {"mcpServers": {"gh": entry.entry}}
