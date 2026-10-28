"""내보내기 REST(2R.11)와 수용 기준 R1.2: `.claude` 픽스처 가져오기 → 내보내기 → 원본과 의미 비교.

가짜 HOME·임시 폴더만 쓴다. 원본 픽스처는 읽기만 하는지(내용·시각·모드) 확인한다.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

from agent_console_claude_format import (
    parse_agent_md,
    parse_mcp,
    parse_rule,
    parse_settings,
)
from agent_console_server.testing import API, TEST_TOKEN, make_settings, seed, server

PLAIN = "ghp_plain_value_123456"


def make_fixture(project: Path) -> None:
    """가져올 `.claude` 프로젝트: 지침·에이전트·skill·규칙·권한·hook·MCP 서버."""
    claude = project / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "skills" / "pdf" / "scripts").mkdir(parents=True)
    (claude / "rules" / "web").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# 프로젝트 지침\n\n짧게 답한다.\n", encoding="utf-8")
    (claude / "agents" / "reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: 리뷰를 맡긴다\ntools: Read, Grep\n"
        "model: sonnet\ncolor: blue\n---\n\n너는 리뷰어다.\n\n- 꼼꼼히 본다.\n",
        encoding="utf-8",
    )
    (claude / "agents" / "writer.md").write_text(
        "---\nname: writer\ndescription: 문서를 쓴다\n---\n문서를 쓴다.\n", encoding="utf-8"
    )
    (claude / "skills" / "pdf" / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: pdf 다루기\n---\n# 사용법\n스크립트를 쓴다.\n",
        encoding="utf-8",
    )
    (claude / "skills" / "pdf" / "scripts" / "run.py").write_bytes(b"print('pdf')\n")
    (claude / "rules" / "web" / "style.md").write_text(
        '---\npaths:\n  - "src/**/*.ts"\n---\n\n세미콜론을 쓴다.\n', encoding="utf-8"
    )
    (claude / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read", "Bash(npm test:*)"], "deny": ["WebFetch"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "./check.sh", "timeout": 30}],
                        }
                    ],
                    "Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}],
                },
            }
        ),
        encoding="utf-8",
    )
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "gh-mcp"],
                        "env": {"GH_TOKEN": "${GH_TOKEN}"},
                    },
                    "web": {
                        "type": "http",
                        "url": "https://example.invalid/mcp",
                        "headers": {"Authorization": f"Bearer {PLAIN}"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    out: dict[str, tuple[bytes, int, int]] = {}
    for current, _, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            st = path.stat()
            out[str(path)] = (path.read_bytes(), st.st_mtime_ns, st.st_mode)
    return out


def read_tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def semantics(files: dict[str, bytes]) -> dict[str, Any]:
    """`.claude` 산출물의 의미(파일 이름·키 순서·공백·목록 표기와 무관)."""
    text = {k: v.decode("utf-8") for k, v in files.items() if not k.endswith(".py")}
    agents = {}
    for path, body in text.items():
        if path.startswith(".claude/agents/"):
            agent = parse_agent_md(body, default_name=Path(path).stem)
            agents[agent.name] = (
                agent.description,
                agent.tools,
                agent.disallowed_tools,
                agent.model,
                agent.prompt,
                agent.extra,
            )
    rules = {}
    for path, body in text.items():
        if path.startswith(".claude/rules/"):
            rule = parse_rule(body)
            rules[rule.body.strip()] = rule.paths
    skills = {
        path.removeprefix(".claude/skills/"): data
        for path, data in files.items()
        if path.startswith(".claude/skills/")
    }
    settings = parse_settings(json.loads(text[".claude/settings.json"]))
    mcp = parse_mcp(json.loads(text[".mcp.json"]))
    return {
        "claude_md": text["CLAUDE.md"].strip(),
        "agents": agents,
        "rules": rules,
        "skills": skills,
        "allow": sorted(settings.allow or []),
        "deny": sorted(settings.deny or []),
        "hooks": sorted((h.event, h.matcher, h.command, h.timeout_seconds) for h in settings.hooks),
        "mcp": mcp,
    }


def setup(tmp_path: Path) -> tuple[Path, Path, Path, Any]:
    project = tmp_path / "project"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "keep.md").write_text("원본", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    make_fixture(project)
    settings = make_settings(
        tmp_path,
        options={
            "mod-imports": {"project_dir": str(project)},
            "mod-exports": {
                "home": str(home),  # 보호 위치 기준(4R.18: 자기 옵션)
                "roots": [
                    {"id": "out", "label": "출력", "path": "out"},
                    {"id": "home", "path": str(home)},
                    {"id": "claude-home", "path": str(home / ".claude")},
                ],
            },
        },
    )
    return project, home, out, settings


def import_all(client: Any) -> None:
    preview = client.post(f"{API}/resources/import/preview", json={"source": "project-claude"})
    assert preview.status_code == 200, preview.text
    picks = [{"candidate_id": c["id"]} for c in preview.json()["candidates"]]
    result = client.post(
        f"{API}/resources/import", json={"source": "project-claude", "items": picks}
    )
    assert result.status_code == 200, result.text
    assert {i["action"] for i in result.json()["items"]} == {"created"}, result.json()


def all_items(client: Any) -> list[dict[str, str]]:
    agents = [{"kind": "agent", "id": a["id"]} for a in client.get(f"{API}/agents").json()]
    resources = [{"kind": "resource", "id": r["id"]} for r in client.get(f"{API}/resources").json()]
    return agents + resources


def test_claude_roundtrip_import_export_is_semantically_equal(tmp_path: Path) -> None:
    project, home, _, settings = setup(tmp_path)
    before = snapshot(tmp_path / "project")
    home_before = snapshot(home)
    with server(settings) as client:
        import_all(client)
        items = all_items(client)
        types = {r["type"] for r in client.get(f"{API}/resources").json()}
        assert {"instruction", "skill", "rule", "hook", "tool-permission", "mcp-server"} <= types

        [exporter] = client.get(f"{API}/exporters").json()
        assert exporter["id"] == "claude-dir"
        request = {"exporter": "claude-dir", "items": items}
        plan = client.post(f"{API}/exports/plan", json=request)
        assert plan.status_code == 200, plan.text
        assert {f["action"] for f in plan.json()["files"]} == {"create"}

        archive = client.post(f"{API}/exports/archive", json=request)
        assert archive.status_code == 200, archive.text
        assert archive.headers["content-type"] == "application/zip"
        assert 'filename="claude-dir.zip"' in archive.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            exported = {name: z.read(name) for name in z.namelist()}

    original = read_tree(project)
    got, want = semantics(exported), semantics(original)
    # 평문 헤더는 가져올 때 secret:// 참조로 바뀌었고, 내보낼 때 ${이름}이 된다(평문 없음)
    web_header = got["mcp"]["web"]["headers"]["Authorization"]
    assert web_header.startswith("${")
    assert PLAIN not in web_header
    want["mcp"]["web"]["headers"]["Authorization"] = web_header
    assert got == want
    for name, data in exported.items():
        assert PLAIN.encode() not in data, name
    assert snapshot(tmp_path / "project") == before  # 원본 무변경
    assert snapshot(home) == home_before


def test_folder_write_roots_and_safety(tmp_path: Path) -> None:
    _, home, out, settings = setup(tmp_path)
    home_before = snapshot(home)
    with server(settings) as client:
        import_all(client)
        items = all_items(client)
        roots = client.get(f"{API}/exports/roots")
        assert roots.status_code == 200
        assert [r["id"] for r in roots.json()] == ["out", "home"]  # ~/.claude 루트는 빠진다
        del client.headers["X-Console-Token"]
        assert client.get(f"{API}/exports/roots").status_code == 401
        client.headers["X-Console-Token"] = TEST_TOKEN

        write = {"exporter": "claude-dir", "items": items, "root": "out", "subdir": "proj"}
        first = client.post(f"{API}/exports/write", json=write)
        assert first.status_code == 200, first.text
        assert {f["action"] for f in first.json()["files"]} == {"create"}
        assert (out / "proj" / ".claude" / "skills" / "pdf" / "scripts" / "run.py").exists()

        again = client.post(f"{API}/exports/plan", json=write)
        assert {f["action"] for f in again.json()["files"]} == {"skip"}
        (out / "proj" / "CLAUDE.md").write_text("바뀜", encoding="utf-8")
        conflict = client.post(f"{API}/exports/plan", json=write)
        actions = {f["path"]: f["action"] for f in conflict.json()["files"]}
        assert actions["CLAUDE.md"] == "conflict"
        refused = client.post(f"{API}/exports/write", json=write)  # 기본 fail
        assert refused.status_code == 409
        assert refused.json()["error"]["details"]["paths"] == ["CLAUDE.md"]
        assert (out / "proj" / "CLAUDE.md").read_text(encoding="utf-8") == "바뀜"
        over = client.post(f"{API}/exports/write", json={**write, "on_conflict": "overwrite"})
        assert over.status_code == 200
        assert (out / "proj" / "CLAUDE.md").read_text(encoding="utf-8") != "바뀜"

        escape = client.post(f"{API}/exports/write", json={**write, "subdir": "../x"})
        assert escape.status_code == 422
        assert escape.json()["error"]["details"]["issues"][0]["path"] == "/subdir"
        protected = client.post(
            f"{API}/exports/write", json={**write, "root": "home", "subdir": ""}
        )
        assert protected.status_code == 422  # .claude/… 는 보호 위치
        claude_root = client.post(f"{API}/exports/write", json={**write, "root": "claude-home"})
        assert claude_root.status_code == 404
        unknown = client.post(f"{API}/exports/write", json={**write, "root": "nope"})
        assert unknown.status_code == 404
        bad_kind = client.post(
            f"{API}/exports/plan",
            json={"exporter": "claude-dir", "items": [{"kind": "settings", "id": "settings"}]},
        )
        assert bad_kind.status_code == 422
        missing = client.post(
            f"{API}/exports/plan",
            json={"exporter": "claude-dir", "items": [{"kind": "agent", "id": "ghost"}]},
        )
        assert missing.status_code == 404
        assert client.post(f"{API}/exports/plan", json={"exporter": "nope"}).status_code == 404
    assert snapshot(home) == home_before


def test_team_export_warns_and_uses_main_node(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        seed(client)
        fast = client.get(f"{API}/agents/fast")
        updated = client.put(
            f"{API}/agents/fast",
            json={**fast.json(), "system_prompt": "너는 입구 담당이다."},
            headers={"If-Match": fast.headers["ETag"]},
        )
        assert updated.status_code == 200, updated.text
        request = {
            "exporter": "claude-dir",
            "items": [{"kind": "graph", "id": "flow"}],
            "options": {"main_node": "a"},
        }
        plan = client.post(f"{API}/exports/plan", json=request)
        assert plan.status_code == 200, plan.text
        body = plan.json()
        codes = [w["code"] for w in body["warnings"]]
        assert "export.semantics_approximate" in codes
        paths = [f["path"] for f in body["files"]]
        assert ".claude/agents/slow.md" in paths
        assert ".claude/agents/fast.md" not in paths  # 주 노드 에이전트 → CLAUDE.md
        assert "CLAUDE.md" in paths
        dropped = [w for w in body["warnings"] if w["code"] == "export.fields_dropped"]
        assert any("backend" in w["details"]["keys"] for w in dropped)
        bad = client.post(
            f"{API}/exports/archive", json={**request, "options": {"main_node": "you"}}
        )
        assert bad.status_code == 422  # 에이전트 노드가 아님(error 경고)
        invalid = client.post(
            f"{API}/exports/plan", json={**request, "options": {"secret_style": "loud"}}
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["details"]["issues"][0]["path"] == "/options/secret_style"
        assert client.get(f"{API}/exports/roots").json() == []  # 루트 없음 → 폴더 쓰기 꺼짐
