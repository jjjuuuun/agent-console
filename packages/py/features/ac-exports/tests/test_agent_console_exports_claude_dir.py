"""기본 형식 `claude-dir`: 정의 → `.claude` 산출물(가짜 카탈로그, 파일 쓰기 없음)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_claude_format import (
    ClaudeMapping,
    parse_agent_md,
    parse_frontmatter,
    parse_mcp,
    parse_rule,
    parse_settings,
)
from agent_console_contracts import ExportSelection
from agent_console_exports import ExportIssueCodes, ExportOutput
from agent_console_exports.claude_dir import ClaudeDirExporter, claude_dir_exporter


@dataclass(frozen=True)
class Dep:
    kind: str
    id: str
    node_id: str | None = None
    shared: bool = False
    mode: str = "add"
    config_override: Mapping[str, Any] | None = None


@dataclass
class FakeCatalog:
    docs: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    bodies: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    deps: dict[tuple[str, str], list[Dep]] = field(default_factory=dict)

    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        return self.docs.get((kind, id))

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        return self.bodies.get((kind, id), {})

    def dependencies(self, kind: str, id: str) -> Sequence[Dep]:
        return self.deps.get((kind, id), [])

    def resource(
        self, id: str, type: str, config: dict[str, Any], body: bytes | None = None, **extra: Any
    ) -> None:
        doc: dict[str, Any] = {
            "kind": "resource",
            "id": id,
            "type": type,
            "name": id,
            "config": config,
            **extra,
        }
        if body is not None:
            doc["content"] = {"file": "content.md"}
            self.bodies[("resource", id)] = {"content.md": body}
        self.docs[("resource", id)] = doc


def catalog() -> FakeCatalog:
    c = FakeCatalog()
    c.docs[("agent", "lead")] = {
        "kind": "agent",
        "id": "lead",
        "name": "lead",
        "system_prompt": "너는 리더다.",
        "tools": ["Read"],
        "model": "opus",
        "limits": {"network": False},
    }
    c.docs[("agent", "rev")] = {
        "kind": "agent",
        "id": "rev",
        "name": "code-reviewer",
        "description": "리뷰",
        "system_prompt": "리뷰한다.",
        "attributes": {"claude_frontmatter": {"color": "blue"}},
    }
    c.resource("guide", "instruction", {}, "# 공용 지침\n".encode())
    c.resource("style", "rule", {"paths": ["src/**"], "name": "style"}, "세미콜론\n".encode())
    c.resource("pdf", "skill", {"name": "pdf"}, description="pdf 도구")
    c.bodies[("resource", "pdf")] = {"SKILL.md": b"---\nname: pdf\n---\n# x\n", "a.py": b"1"}
    c.resource("lint", "hook", {"event": "PostToolUse", "matcher": "Edit", "command": "lint"})
    c.resource("perm", "tool-permission", {"tools": ["Read"], "commands": ["ls"]})
    c.resource(
        "gh",
        "mcp-server",
        {
            "name": "github",
            "transport": "stdio",
            "command": "npx",
            "env": {"TOKEN": "secret://GH_TOKEN", "PLAIN": "abc"},
        },
    )
    c.resource("own-note", "instruction", {"text": "리뷰 메모"})
    c.resource("thing", "file", {})
    c.deps[("agent", "rev")] = [
        Dep("resource", "own-note"),
        Dep("resource", "pdf"),
        Dep("resource", "gh"),
        Dep("resource", "lint"),
        Dep("resource", "style"),
        Dep("resource", "thing"),
        Dep("resource", "guide", shared=True),
    ]
    c.deps[("graph", "team")] = [
        Dep("agent", "lead", node_id="n-lead"),
        Dep("agent", "rev", node_id="n-rev"),
        Dep("resource", "perm", node_id="n-lead"),
        Dep("resource", "guide", shared=True),
        Dep("resource", "gone", shared=True, mode="remove"),
    ]
    c.docs[("graph", "team")] = {"kind": "graph", "id": "team"}
    return c


def files_of(out: ExportOutput) -> dict[str, str]:
    return {f.path: f.data.decode("utf-8") for f in out.files}


def codes(out: ExportOutput) -> list[str]:
    return [w.code for w in out.warnings]


def test_descriptor_and_factory() -> None:
    exporter = claude_dir_exporter({})
    assert exporter.descriptor.id == "claude-dir"
    assert exporter.descriptor.kinds == ["agent", "resource", "graph"]
    props = exporter.descriptor.config_schema["properties"]
    assert "default" not in props["main_node"]  # 기본 없음(추론하지 않음)
    custom = claude_dir_exporter({"mapping": {"agent_kind": "persona"}})
    assert custom.descriptor.kinds[0] == "persona"
    with pytest.raises(ValueError, match="모르는 옵션"):
        claude_dir_exporter({"x": 1})


def test_agent_export_with_attachments() -> None:
    out = ClaudeDirExporter().plan([ExportSelection(kind="agent", id="rev")], catalog(), {})
    files = files_of(out)
    agent = parse_agent_md(files[".claude/agents/rev.md"], default_name="x")
    assert agent.name == "code-reviewer"
    assert agent.prompt == "리뷰한다.\n\n리뷰 메모"
    assert agent.extra["color"] == "blue"
    assert agent.extra["skills"] == ["pdf"]
    assert agent.extra["mcpServers"] == ["github"]
    assert agent.extra["hooks"] == {
        "PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "lint"}]}]
    }
    assert sorted(p for p in files if p.startswith(".claude/skills/")) == [
        ".claude/skills/pdf/SKILL.md",
        ".claude/skills/pdf/a.py",
    ]
    assert parse_rule(files[".claude/rules/style.md"]).paths == ["src/**"]
    assert files["CLAUDE.md"] == "# 공용 지침\n"  # 공통 층(shared)
    mcp = parse_mcp(json.loads(files[".mcp.json"]))
    assert mcp["github"]["env"] == {"TOKEN": "${GH_TOKEN}"}
    assert "abc" not in files[".mcp.json"]
    assert ExportIssueCodes.SECRET_OMITTED in codes(out)
    assert ExportIssueCodes.SCOPE_WIDENED in codes(out)  # 규칙은 프로젝트 전체로
    assert ExportIssueCodes.TYPE_UNSUPPORTED in codes(out)  # file 종류


def test_graph_export_main_node_and_options() -> None:
    c = catalog()
    out = ClaudeDirExporter().plan(
        [ExportSelection(kind="graph", id="team")],
        c,
        {
            "main_node": "n-lead",
            "instructions_mode": "separate_files",
            "agent_file_name": "{name}.md",
            "include_shared_resources": False,
        },
    )
    files = files_of(out)
    assert ".claude/agents/lead.md" not in files  # 주 노드 에이전트는 CLAUDE.md로
    assert ".claude/agents/code-reviewer.md" in files
    assert files["CLAUDE.md"].startswith("너는 리더다.")
    assert ".claude/instructions/own-note.md" not in files  # 구성원 지침은 에이전트 본문
    settings = parse_settings(json.loads(files[".claude/settings.json"]))
    assert settings.allow == ["Read"]
    assert json.loads(files[".claude/settings.json"])["model"] == "opus"
    assert "공용 지침" not in files["CLAUDE.md"]
    assert codes(out).count(ExportIssueCodes.SEMANTICS_APPROXIMATE) == 2  # 팀 + remove
    dropped = [w for w in out.warnings if w.code == ExportIssueCodes.FIELDS_DROPPED]
    assert any(w.details.get("keys") == ["limits"] for w in dropped)
    assert any(w.details.get("keys") == ["commands"] for w in dropped)

    separate = ClaudeDirExporter().plan(
        [ExportSelection(kind="resource", id="guide")], c, {"instructions_mode": "separate_files"}
    )
    sep = files_of(separate)
    assert sep["CLAUDE.md"] == "@.claude/instructions/guide.md\n"
    assert sep[".claude/instructions/guide.md"] == "# 공용 지침\n"


def test_graph_export_follows_child_teams() -> None:
    """중첩 팀 노드의 자식 팀 구성(쓰는 정의 종류 = 팀 구성)도 따라가 구성원을 내보낸다(5R.15).
    주 노드는 고른 팀 구성 것만 보고, 순환해도 한 번씩만 읽는다."""
    c = catalog()
    c.deps[("graph", "team")] = [
        Dep("agent", "lead", node_id="n-lead"),
        Dep("graph", "sub", node_id="n-sub"),
    ]
    c.deps[("graph", "sub")] = [
        Dep("agent", "rev", node_id="n-lead"),  # 자식의 같은 노드 id는 주 노드가 아니다
        Dep("graph", "team", node_id="n-back"),
    ]
    c.docs[("graph", "sub")] = {"kind": "graph", "id": "sub"}
    out = ClaudeDirExporter().plan(
        [ExportSelection(kind="graph", id="team")], c, {"main_node": "n-lead"}
    )
    files = files_of(out)
    assert ".claude/agents/rev.md" in files  # 자식 팀 구성의 구성원
    assert ".claude/agents/lead.md" not in files  # 주 노드는 CLAUDE.md로
    assert files["CLAUDE.md"].startswith("너는 리더다.")
    approx = [w for w in out.warnings if w.code == ExportIssueCodes.SEMANTICS_APPROXIMATE]
    graphs = [str(w.details["graph"]) for w in approx if "graph" in w.details]
    assert sorted(graphs) == ["sub", "team"]


def test_main_node_is_never_guessed() -> None:
    c = catalog()
    out = ClaudeDirExporter().plan([ExportSelection(kind="graph", id="team")], c, {})
    files = files_of(out)
    assert ".claude/agents/lead.md" in files  # 주 노드 없음 → 모두 구성원
    assert "너는 리더다." not in files.get("CLAUDE.md", "")
    bad = ClaudeDirExporter().plan(
        [ExportSelection(kind="graph", id="team")], c, {"main_node": "nope"}
    )
    [error] = [w for w in bad.warnings if w.severity == "error"]
    assert error.code == ExportIssueCodes.MAIN_NODE_NOT_FOUND
    assert error.path == "/options/main_node"


def test_name_conflicts_and_missing() -> None:
    c = catalog()
    c.resource("pdf2", "skill", {"name": "pdf"})
    c.bodies[("resource", "pdf2")] = {"SKILL.md": b"x"}
    out = ClaudeDirExporter().plan(
        [
            ExportSelection(kind="resource", id="pdf"),
            ExportSelection(kind="resource", id="pdf2"),
            ExportSelection(kind="resource", id="missing"),
            ExportSelection(kind="agent", id="ghost"),
        ],
        c,
        {"secret_style": "omit"},
    )
    assert codes(out).count(ExportIssueCodes.NAME_CONFLICT) == 1
    assert codes(out).count(ExportIssueCodes.NOT_FOUND) == 2
    assert files_of(out)[".claude/skills/pdf/SKILL.md"].startswith("---")


def test_skill_without_main_file_gets_one() -> None:
    c = FakeCatalog()
    c.resource("s", "skill", {}, description="설명")
    c.bodies[("resource", "s")] = {"ref.md": b"r"}
    out = ClaudeDirExporter().plan([ExportSelection(kind="resource", id="s")], c, {})
    meta, _ = parse_frontmatter(files_of(out)[".claude/skills/s/SKILL.md"])
    assert meta == {"name": "s", "description": "설명"}


def test_mapping_is_data() -> None:
    c = FakeCatalog()
    c.resource("x", "my-instruction", {"text": "custom"})
    exporter = ClaudeDirExporter(mapping=ClaudeMapping(instruction_type="my-instruction"))
    out = exporter.plan([ExportSelection(kind="resource", id="x")], c, {})
    assert files_of(out)["CLAUDE.md"] == "custom\n"


def test_hook_probe_setting_does_not_change_exported_hook_commands() -> None:
    """F-16: `observe.hook_probe`가 켜져 있어도 `.claude` 내보내기는 원래 hook 명령을 낸다."""
    c = catalog()
    for key in (("agent", "rev"), ("agent", "lead")):
        c.docs[key] = {**c.docs[key], "observe": {"hook_probe": True}}
    c.deps[("graph", "team")].append(Dep("resource", "lint", node_id="n-lead"))
    agent_out = ClaudeDirExporter().plan([ExportSelection(kind="agent", id="rev")], c, {})
    agent = parse_agent_md(files_of(agent_out)[".claude/agents/rev.md"], default_name="x")
    assert agent.extra["hooks"] == {
        "PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "lint"}]}]
    }
    graph_out = ClaudeDirExporter().plan(
        [ExportSelection(kind="graph", id="team")], c, {"main_node": "n-lead"}
    )
    files = files_of(graph_out)
    settings = json.loads(files[".claude/settings.json"])
    commands = [
        h["command"] for entries in settings["hooks"].values() for e in entries for h in e["hooks"]
    ]
    assert commands == ["lint"]
    for text in (*files_of(agent_out).values(), *files.values()):
        assert "hook_probe" not in text
        assert "hook-probe" not in text
