"""1R.14 QA 추가 검증: 기본 설정의 CORS 닫힘, 가져오기 경로 탈출(심볼릭 링크), 비밀 치환 범위."""

from __future__ import annotations

import json
from pathlib import Path

from agent_console_server.testing import API, TEST_TOKEN, make_settings, server

OUTSIDE_MARK = "OUTSIDE-SECRET-MARK"


def test_default_settings_deny_every_cross_origin(tmp_path: Path) -> None:
    """allowed_origins가 비어 있으면(기본) 어떤 출처도 CORS·bootstrap을 얻지 못한다."""
    with server(make_settings(tmp_path), with_token=False) as client:
        origin = "http://localhost:5173"
        pre = client.options(
            f"{API}/graphs",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert pre.status_code == 403
        assert "access-control-allow-origin" not in pre.headers
        boot = client.get(
            f"{API}/bootstrap", headers={"Origin": origin, "Sec-Fetch-Site": "cross-site"}
        )
        assert boot.status_code == 403
        assert "token" not in boot.text
        read = client.get(f"{API}/graphs", headers={"Origin": origin})
        assert "access-control-allow-origin" not in read.headers
        write = client.post(
            f"{API}/agents", json={}, headers={"Origin": origin, "X-Console-Token": TEST_TOKEN}
        )
        assert write.status_code == 403  # 올바른 토큰이어도 허용 출처가 아니면 거부
        # 같은 출처(Host와 같은 Origin)는 허용
        same = client.get(f"{API}/bootstrap", headers={"Origin": "http://testserver"})
        assert same.status_code == 200


def test_import_does_not_follow_file_symlink_out_of_claude_dir(tmp_path: Path) -> None:
    home = tmp_path / "fakehome"
    (home / ".claude" / "agents").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text(OUTSIDE_MARK, encoding="utf-8")
    (home / ".claude" / "CLAUDE.md").symlink_to(outside)
    (home / ".claude" / "agents" / "evil.md").symlink_to(outside)
    with server(make_settings(tmp_path), environ={"HOME": str(home)}) as client:
        preview = client.post(f"{API}/resources/import/preview", json={"source": "user-claude"})
        candidates = preview.json()["candidates"]
        assert candidates == []  # 링크는 후보가 되지 않아야 한다
        assert OUTSIDE_MARK not in json.dumps(candidates)


def test_mcp_args_and_url_secrets_are_not_stored_in_plain(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gh": {
                        "command": "npx",
                        "args": ["srv", "--token", "ghp_PLAINSECRET123456"],
                        "url": "https://x.invalid/?api_key=PLAINURLKEY987654",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    settings = make_settings(tmp_path, options={"mod-imports": {"project_dir": str(project)}})
    with server(settings, environ={"HOME": str(tmp_path / "nohome")}) as client:
        preview = client.post(f"{API}/resources/import/preview", json={"source": "project-claude"})
        [cand] = [c for c in preview.json()["candidates"] if c["resource_type"] == "mcp-server"]
        client.post(
            f"{API}/resources/import",
            json={"source": "project-claude", "items": [{"candidate_id": cand["id"]}]},
        )
        stored = json.dumps(client.get(f"{API}/resources/{cand['suggested_id']}").json())
        assert "PLAINSECRET" not in stored
        assert "PLAINURLKEY" not in stored


def test_import_blocks_linked_dirs_project_file_and_nested_escape(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "a.md").write_text(OUTSIDE_MARK, encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude" / "rules").mkdir(parents=True)
    (home / ".claude" / "rules" / "sub").symlink_to(outside_dir)
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "agents").symlink_to(outside_dir)
    (project / "CLAUDE.md").symlink_to(outside_dir / "a.md")
    settings = make_settings(tmp_path, options={"mod-imports": {"project_dir": str(project)}})
    with server(settings, environ={"HOME": str(home)}) as client:
        for source in ("user-claude", "project-claude"):
            preview = client.post(f"{API}/resources/import/preview", json={"source": source})
            assert preview.json()["candidates"] == []
            assert OUTSIDE_MARK not in preview.text


def test_import_allows_linked_root_but_not_escape_below_it(tmp_path: Path) -> None:
    real = tmp_path / "dotfiles"
    (real / "agents").mkdir(parents=True)
    (real / "agents" / "ok.md").write_text("---\nname: ok\n---\n본문", encoding="utf-8")
    outside = tmp_path / "o.md"
    outside.write_text(OUTSIDE_MARK, encoding="utf-8")
    (real / "agents" / "bad.md").symlink_to(outside)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").symlink_to(real)
    with server(make_settings(tmp_path), environ={"HOME": str(home)}) as client:
        preview = client.post(f"{API}/resources/import/preview", json={"source": "user-claude"})
        names = [c["name"] for c in preview.json()["candidates"]]
        assert names == ["ok"]


def test_mcp_benign_args_are_untouched(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    args = ["-y", "@scope/server-fs", "--root", "/work/dir", "--port", "3000", "--verbose"]
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fs": {"command": "npx", "args": args, "url": "https://h.invalid/p?a=1"}
                }
            }
        ),
        encoding="utf-8",
    )
    settings = make_settings(tmp_path, options={"mod-imports": {"project_dir": str(project)}})
    with server(settings, environ={"HOME": str(tmp_path / "nohome")}) as client:
        preview = client.post(f"{API}/resources/import/preview", json={"source": "project-claude"})
        [cand] = [c for c in preview.json()["candidates"] if c["resource_type"] == "mcp-server"]
        client.post(
            f"{API}/resources/import",
            json={"source": "project-claude", "items": [{"candidate_id": cand["id"]}]},
        )
        cfg = client.get(f"{API}/resources/{cand['suggested_id']}").json()["config"]
        assert cfg["args"] == args
        assert cfg["url"] == "https://h.invalid/p?a=1"
