"""가져오기: 원본 읽기 전용, 후보 스캔, 충돌 처리, 비밀 비저장, 출처 공장 로딩."""

from __future__ import annotations

import json
import os
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from agent_console_contracts import (
    Agent,
    ImportCandidate,
    ImportRequest,
    ImportSelection,
    ImportSourceDescriptor,
    Resource,
)
from agent_console_imports import (
    ImportItem,
    ImportService,
    ImportSourceContext,
    ImportSourceFactory,
    ScanResult,
    UnknownImportSourceError,
    build_import_sources,
    load_import_source_factories,
    new_import_source_factories,
)
from agent_console_imports.claude import (
    PROJECT_SOURCE_ID,
    USER_SOURCE_ID,
    ClaudeDirectorySource,
    claude_sources,
    parse_frontmatter,
    slugify,
)
from agent_console_registry import Registry
from agent_console_secret_rules import SecretRules
from agent_console_store import InMemoryDefinitionStore

PLAIN_SECRET = "ghp_plain_value_123456"


def make_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "rules" / "web").mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# 전역 지침\n짧게 답한다.\n", encoding="utf-8")
    (claude / "agents" / "pl.md").write_text(
        "---\nname: pl\ndescription: 설계와 분해\ntools: Read, Grep\nmodel: sonnet\n"
        "color: blue\n---\n당신은 PL입니다.\n",
        encoding="utf-8",
    )
    (claude / "agents" / "notes.txt").write_text("무시", encoding="utf-8")
    (claude / "rules" / "web" / "style.md").write_text(
        "---\npaths: ['src/**']\n---\n세미콜론을 쓴다.\n", encoding="utf-8"
    )
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Read", "Bash(npm test:*)"], "deny": ["WebFetch"]}}),
        encoding="utf-8",
    )
    return home


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("프로젝트 규칙", encoding="utf-8")
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://example.invalid/mcp",
                        "headers": {"Authorization": f"Bearer {PLAIN_SECRET}"},
                    },
                    "local tool": {
                        "command": "npx",
                        "args": ["-y", "tool"],
                        "env": {"TOKEN": "${MY_TOKEN}", "KEEP": "secret://kept"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return project


def snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    """폴더 아래 모든 파일의 (내용, 수정 시각, 모드)."""
    out: dict[str, tuple[bytes, int, int]] = {}
    for current, _, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            st = path.stat()
            out[str(path)] = (path.read_bytes(), st.st_mtime_ns, st.st_mode)
    return out


def sources(tmp_path: Path) -> list[ClaudeDirectorySource]:
    found = claude_sources(
        ImportSourceContext(home=make_home(tmp_path), project_dir=make_project(tmp_path))
    )
    assert all(isinstance(s, ClaudeDirectorySource) for s in found)
    return [s for s in found if isinstance(s, ClaudeDirectorySource)]


def test_helpers() -> None:
    assert slugify("My Agent!") == "my-agent"
    assert slugify("---") == "item"
    meta, body = parse_frontmatter("---\nname: a\n---\nbody")
    assert meta == {"name": "a"}
    assert body == "body"
    assert parse_frontmatter("no front") == ({}, "no front")
    assert parse_frontmatter("---\n: [bad\n---\nx")[0] == {}


def test_scan_user_claude_candidates(tmp_path: Path) -> None:
    user, _ = sources(tmp_path)
    assert user.descriptor.id == USER_SOURCE_ID
    assert user.descriptor.available
    scan = user.scan()
    by_kind = {(c.candidate.kind, c.candidate.resource_type) for c in scan.items}
    assert by_kind == {
        ("resource", "instruction"),
        ("agent", None),
        ("resource", "rule"),
        ("resource", "tool-permission"),
    }
    agent = next(i for i in scan.items if i.candidate.kind == "agent")
    model = Agent.model_validate({**agent.document, "id": agent.candidate.suggested_id})
    assert model.tools == ["Read", "Grep"]
    assert model.model == "sonnet"
    assert model.system_prompt == "당신은 PL입니다."
    assert model.attributes["claude_frontmatter"] == {"color": "blue"}
    assert agent.candidate.warnings[0].keys == ["color"]
    rule = next(i for i in scan.items if i.candidate.id.startswith("rule:"))
    assert rule.candidate.warnings == []
    assert rule.document["config"] == {"paths": ["src/**"], "name": "web-style"}
    assert rule.content == "세미콜론을 쓴다.\n".encode()
    perms = next(i for i in scan.items if i.candidate.resource_type == "tool-permission")
    assert perms.document["config"] == {
        "tools": ["Read", "Bash(npm test:*)"],
        "disallowed_tools": ["WebFetch"],
    }


def test_mcp_plain_secrets_are_not_kept(tmp_path: Path) -> None:
    _, project = sources(tmp_path)
    scan = project.scan()
    mcp = {i.candidate.name: i for i in scan.items if i.candidate.resource_type == "mcp-server"}
    assert set(mcp) == {"github", "local-tool"}
    github = mcp["github"]
    assert PLAIN_SECRET not in json.dumps(github.document)
    assert github.document["config"]["headers"] == {
        "Authorization": "secret://GITHUB_AUTHORIZATION"
    }
    assert github.candidate.warnings[0].keys == ["headers/Authorization"]
    local = mcp["local-tool"].document["config"]
    assert local["env"] == {"TOKEN": "secret://MY_TOKEN", "KEEP": "secret://kept"}
    assert mcp["local-tool"].candidate.warnings == []
    instructions = [i for i in scan.items if i.candidate.resource_type == "instruction"]
    assert [i.candidate.suggested_id for i in instructions] == ["project-claude"]


def test_missing_folders_are_empty(tmp_path: Path) -> None:
    [user, project] = claude_sources(
        ImportSourceContext(home=tmp_path / "nohome", project_dir=tmp_path / "noproj")
    )
    assert not user.descriptor.available
    assert user.scan().items == []
    assert project.scan().items == []
    assert claude_sources(ImportSourceContext()) == []


def test_service_preview_apply_and_originals_unchanged(tmp_path: Path) -> None:
    found = sources(tmp_path)
    before = snapshot(tmp_path)
    store = InMemoryDefinitionStore()
    service = ImportService(found, store)
    assert [d.id for d in service.descriptors()] == [USER_SOURCE_ID, PROJECT_SOURCE_ID]

    preview = service.preview(USER_SOURCE_ID)
    assert preview.root is not None
    assert not any(c.conflict for c in preview.candidates)
    picks = [ImportSelection(candidate_id=c.id) for c in preview.candidates]
    result = service.apply(ImportRequest(source=USER_SOURCE_ID, items=picks))
    assert {i.action for i in result.items} == {"created"}

    instruction = next(c for c in preview.candidates if c.id.startswith("instruction:"))
    stored = store.get("resource", instruction.suggested_id).model(Resource)
    assert stored.type == "instruction"
    assert stored.attributes["imported_from"]["source"] == USER_SOURCE_ID
    assert store.read_content("resource", stored.id) == "# 전역 지침\n짧게 답한다.\n".encode()

    again = service.preview(USER_SOURCE_ID)
    assert all(c.conflict for c in again.candidates)
    agent_key = next(c.id for c in again.candidates if c.kind == "agent")
    modes = service.apply(
        ImportRequest(
            source=USER_SOURCE_ID,
            items=[
                ImportSelection(candidate_id=agent_key, on_conflict="skip"),
                ImportSelection(candidate_id=agent_key, on_conflict="rename"),
                ImportSelection(candidate_id=agent_key, on_conflict="overwrite"),
                ImportSelection(candidate_id=agent_key, target_id="bad id!"),
                ImportSelection(candidate_id="missing"),
            ],
        )
    )
    assert [i.action for i in modes.items] == [
        "skipped",
        "renamed",
        "overwritten",
        "failed",
        "failed",
    ]
    assert modes.items[1].target_id == "pl-2"
    assert sorted(store.list_ids("agent")) == ["pl", "pl-2"]

    service.apply(
        ImportRequest(
            source=PROJECT_SOURCE_ID,
            items=[
                ImportSelection(candidate_id=c.id)
                for c in service.preview(PROJECT_SOURCE_ID).candidates
            ],
        )
    )
    for rid in store.list_ids("resource"):
        assert PLAIN_SECRET not in json.dumps(store.get("resource", rid).document)

    assert snapshot(tmp_path) == before  # 원본 무변경

    with pytest.raises(UnknownImportSourceError):
        service.preview("nope")


class _OneItem:
    descriptor = ImportSourceDescriptor(id="one", title="하나")

    def scan(self) -> ScanResult:
        candidate = ImportCandidate(id="x", path="mem", kind="agent", name="X", suggested_id="x")
        return ScanResult(root=None, items=[ImportItem(candidate, {"name": "X"})])


def custom_factory(ctx: ImportSourceContext) -> list[_OneItem]:
    assert ctx.options == {"flag": True}
    return [_OneItem()]


def broken_factory(ctx: ImportSourceContext) -> list[_OneItem]:
    raise RuntimeError("boom")


def test_factory_loading_is_extensible() -> None:
    registry = new_import_source_factories()
    group = "agent_console.import_sources"
    reports = load_import_source_factories(
        registry,
        entry_points=[
            EntryPoint("claude", "agent_console_imports.claude:claude_sources", group),
            EntryPoint("notcallable", "agent_console_imports.claude:USER_SOURCE_ID", group),
        ],
    )
    assert sorted((r.key, r.status) for r in reports) == [
        ("claude", "loaded"),
        ("notcallable", "failed"),
    ]
    registry.register("custom", custom_factory, source="test")
    registry.register("broken", broken_factory, source="test")
    built = build_import_sources(registry, ImportSourceContext(options={"custom": {"flag": True}}))
    assert [s.descriptor.id for s in built] == ["one"]  # claude: 홈·프로젝트 없음, broken: 건너뜀
    store = InMemoryDefinitionStore()
    result = ImportService(built, store).apply(
        ImportRequest(source="one", items=[ImportSelection(candidate_id="x")])
    )
    assert result.items[0].action == "created"
    assert store.get("agent", "x").model(Agent).name == "X"


def test_installed_entry_point_registers_claude_factory() -> None:
    registry = new_import_source_factories()
    load_import_source_factories(registry)
    assert "claude" in registry


def test_symlinks_out_of_source_are_not_read(tmp_path: Path) -> None:
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / "agents").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("밖의 비밀", encoding="utf-8")
    (claude / "CLAUDE.md").symlink_to(outside)
    (claude / "agents" / "evil.md").symlink_to(outside)
    linked = tmp_path / "linked-rules"
    linked.mkdir()
    (linked / "r.md").write_text("밖의 규칙", encoding="utf-8")
    (claude / "rules").symlink_to(linked, target_is_directory=True)
    (claude / "settings.json").symlink_to(tmp_path / "outside.json")
    (tmp_path / "outside.json").write_text('{"permissions": {"allow": ["X"]}}', encoding="utf-8")
    (claude / "agents" / "ok.md").write_text("---\nname: ok\n---\n안", encoding="utf-8")
    [user] = claude_sources(ImportSourceContext(home=home))
    names = [i.candidate.name for i in user.scan().items]
    assert names == ["ok"]


def test_mcp_args_and_url_secrets_are_masked(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gh": {
                        "command": "npx",
                        "args": [
                            "srv",
                            "--token",
                            "ghp_PLAIN1",
                            "--api-key=PLAIN2",
                            "-v",
                            "sk-PLAIN3abcdef",
                        ],
                        "url": "https://u:PLAIN4@x.invalid/p?api_key=PLAIN5&page=2",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    [source] = claude_sources(ImportSourceContext(project_dir=project))
    [item] = [i for i in source.scan().items if i.candidate.resource_type == "mcp-server"]
    stored = json.dumps(item.document)
    for plain in ("PLAIN1", "PLAIN2", "PLAIN3", "PLAIN4", "PLAIN5"):
        assert plain not in stored
    config = item.document["config"]
    assert config["args"][:2] == ["srv", "--token"]
    assert config["args"][2].startswith("secret://")
    assert "-v" in config["args"]
    assert "page=2" in config["url"]
    [warning] = item.candidate.warnings
    assert warning.code == "import.secret_suspected"
    assert "url/userinfo" in warning.keys


def test_mcp_secret_rules_are_injected_and_cover_embedded_tokens(tmp_path: Path) -> None:
    """2R.4: 출처는 앱이 넘긴 규칙(사용자 추가분 포함)을 쓰고, 문자열 안 토큰 모양도 바꾼다."""
    project = tmp_path / "p"
    project.mkdir()
    args = [
        "srv",
        "--header=Authorization: Bearer abc123456789",
        "--corp",
        "PLAIN6",
        "--key-file",
        "k",
    ]
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"gh": {"command": "npx", "args": args}}}), encoding="utf-8"
    )
    rules = SecretRules().with_extra(key_names=["corp"])
    ctx = ImportSourceContext(project_dir=project, secret_rules=lambda: rules)
    [source] = build_import_sources(_claude_only(), ctx)
    [item] = [i for i in source.scan().items if i.candidate.resource_type == "mcp-server"]
    out = item.document["config"]["args"]
    assert "abc123456789" not in json.dumps(out)
    assert "PLAIN6" not in json.dumps(out)
    assert out[1].startswith("secret://")
    assert out[3].startswith("secret://")
    assert out[4:] == ["--key-file", "k"]  # 오탐 예외: 비밀이 아닌 접미
    # 기본 규칙만 쓰면 사용자 이름(`--corp`)은 그대로
    [base] = build_import_sources(_claude_only(), ImportSourceContext(project_dir=project))
    [base_item] = [i for i in base.scan().items if i.candidate.resource_type == "mcp-server"]
    assert base_item.document["config"]["args"][3] == "PLAIN6"


def _claude_only() -> Registry[ImportSourceFactory]:
    registry = new_import_source_factories()
    registry.register("claude", claude_sources)
    return registry


def _skill_hook_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    claude = home / ".claude"
    skill = claude / "skills" / "pdf"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: PDF 도구\ndescription: pdf 다루기\n---\n# 사용법\n", encoding="utf-8"
    )
    (skill / "scripts" / "run.py").write_bytes(b"print(1)\n")
    (claude / "skills" / "no-main").mkdir()
    (claude / "skills" / "no-main" / "x.md").write_text("주 파일 없음", encoding="utf-8")
    (claude / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": "./check.sh", "timeout": 20},
                                {"type": "http", "url": "https://x"},
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": f"notify --token {PLAIN_SECRET}"}
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return home


def test_skills_and_hooks_are_imported(tmp_path: Path) -> None:
    home = _skill_hook_home(tmp_path)
    before = snapshot(tmp_path)
    [user] = claude_sources(ImportSourceContext(home=home))
    scan = user.scan()
    skill = next(i for i in scan.items if i.candidate.resource_type == "skill")
    assert skill.candidate.name == "PDF 도구"
    assert skill.document["config"] == {"name": "pdf"}
    assert skill.document["description"] == "pdf 다루기"
    assert skill.files is not None
    assert sorted(skill.files) == ["SKILL.md", "scripts/run.py"]
    assert not any(i.candidate.id == "skill:no-main" for i in scan.items)

    hooks = [i for i in scan.items if i.candidate.resource_type == "hook"]
    assert hooks[0].document["config"] == {
        "event": "PreToolUse",
        "command": "./check.sh",
        "matcher": "Bash",
        "timeout_seconds": 20,
    }
    stop = hooks[1]
    assert PLAIN_SECRET not in json.dumps(stop.document)
    assert stop.candidate.warnings[0].code == "import.secret_suspected"
    [unsupported] = [w for w in scan.warnings if w.code == "import.hook_unsupported"]
    assert unsupported.keys == ["/hooks/PreToolUse/0/hooks/1"]

    store = InMemoryDefinitionStore()
    service = ImportService([user], store)
    result = service.apply(
        ImportRequest(
            source=USER_SOURCE_ID,
            items=[ImportSelection(candidate_id=i.candidate.id) for i in scan.items],
        )
    )
    assert {i.action for i in result.items} == {"created"}
    stored = store.get("resource", "skill-pdf").model(Resource)
    assert stored.type == "skill"
    assert [f.path for f in store.list_files("resource", "skill-pdf")] == [
        "SKILL.md",
        "scripts/run.py",
    ]
    # 덮어쓰기: 원본에서 사라진 파일은 지운다
    (home / ".claude" / "skills" / "pdf" / "scripts" / "run.py").unlink()
    service.apply(
        ImportRequest(
            source=USER_SOURCE_ID,
            items=[ImportSelection(candidate_id="skill:pdf", on_conflict="overwrite")],
        )
    )
    assert [f.path for f in store.list_files("resource", "skill-pdf")] == ["SKILL.md"]
    del before[str(home / ".claude" / "skills" / "pdf" / "scripts" / "run.py")]
    assert snapshot(tmp_path) == before


def test_skipped_links_are_reported_in_preview(tmp_path: Path) -> None:
    home = tmp_path / "home"
    claude = home / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "skills").mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("밖", encoding="utf-8")
    (claude / "CLAUDE.md").symlink_to(outside)
    (claude / "agents" / "evil.md").symlink_to(outside)
    linked = tmp_path / "linked"
    linked.mkdir()
    (claude / "rules").symlink_to(linked, target_is_directory=True)
    (claude / "skills" / "linked-skill").symlink_to(linked, target_is_directory=True)
    [user] = claude_sources(ImportSourceContext(home=home))
    service = ImportService([user], InMemoryDefinitionStore())
    preview = service.preview(USER_SOURCE_ID)
    assert preview.candidates == []
    links = [w for w in preview.warnings if w.code == "import.skipped_link"]
    assert sorted(k for w in links for k in w.keys) == sorted(
        str(p)
        for p in (
            claude / "CLAUDE.md",
            claude / "agents" / "evil.md",
            claude / "rules",
            claude / "skills" / "linked-skill",
        )
    )
