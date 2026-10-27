"""2R.12: 여러 파일 리소스 REST(`/resources/{id}/files[/{path}]`), skill·rule·hook 실행 전달,
받지 않는 칸 검증 경고, fake `echo_hooks`, 사용자 프로젝트·HOME 무변경."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server, wait_run

SKILL = {"id": "review", "type": "skill", "name": "리뷰", "config": {"name": "review"}}
RULE = {
    "id": "api",
    "type": "rule",
    "name": "API 규칙",
    "config": {"paths": ["src/**"], "text": "검증 먼저"},
}
HOOK = {
    "id": "fmt",
    "type": "hook",
    "name": "포맷",
    "config": {"event": "PostToolUse", "command": "fmt --check"},
}


def _etag(response: Any) -> str:
    value: str = response.headers["ETag"]
    return value


def _graph(agent_id: str) -> dict[str, Any]:
    return {
        "id": f"g-{agent_id}",
        "name": "g",
        "inputs": [{"name": "request"}],
        "nodes": [
            {"id": "you", "type": "user"},
            {"id": "a", "type": "agent", "config": {"agent_ref": agent_id}},
        ],
        "edges": [
            {
                "id": "m",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {"input_key": "request"},
            },
            {
                "id": "r",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _agent(agent_id: str, refs: list[str]) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {"default": {"response": "ok"}, "echo_bundle": True},
        "resources": [{"ref": r} for r in refs],
    }


# ---------------------------------------------------------------- 파일 REST


def test_files_crud_with_if_match(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        created = client.post(f"{API}/resources", json=SKILL)
        assert created.status_code == 201, created.text
        etag = _etag(created)
        assert client.get(f"{API}/resources/review/files").json() == []

        url = f"{API}/resources/review/files/SKILL.md"
        assert client.put(url, content=b"# review").status_code == 428
        put = client.put(url, content=b"# review", headers={"If-Match": etag})
        assert put.status_code == 200, put.text
        assert put.json()["id"] == "review"
        assert _etag(put) != etag
        stale = client.put(
            f"{API}/resources/review/files/scripts/run.sh",
            content=b"echo hi",
            headers={"If-Match": etag},
        )
        assert stale.status_code == 412
        second = client.put(
            f"{API}/resources/review/files/scripts/run.sh",
            content=b"echo hi",
            headers={"If-Match": _etag(put)},
        )
        assert second.status_code == 200

        files = client.get(f"{API}/resources/review/files").json()
        assert [f["path"] for f in files] == ["SKILL.md", "scripts/run.sh"]
        assert files[0]["size"] == len(b"# review")
        assert len(files[0]["sha256"]) == 64
        got = client.get(url)
        assert got.status_code == 200
        assert got.content == b"# review"
        assert got.headers["content-type"].startswith("text/plain")
        assert _etag(got) == _etag(second)

        deleted = client.delete(
            f"{API}/resources/review/files/scripts/run.sh", headers={"If-Match": _etag(second)}
        )
        assert deleted.status_code == 200
        assert [f["path"] for f in client.get(f"{API}/resources/review/files").json()] == [
            "SKILL.md"
        ]
        missing = client.delete(
            f"{API}/resources/review/files/nope.md", headers={"If-Match": _etag(deleted)}
        )
        assert missing.status_code == 404
        # 되돌리기와 같은 규칙: 같은 파일 집합이면 같은 해시
        assert _etag(deleted) == _etag(put)


def test_files_rejects_single_body_types_bad_paths_and_size(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, options={"mod-definitions": {"max_content_bytes": 16}})
    with server(settings) as client:
        instr = {"id": "guide", "type": "instruction", "name": "g", "config": {"text": "x"}}
        etag = _etag(client.post(f"{API}/resources", json=instr))
        refused = client.put(
            f"{API}/resources/guide/files/extra.md", content=b"x", headers={"If-Match": etag}
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["details"]["issues"][0]["code"] == "resource.not_multi_file"

        etag = _etag(client.post(f"{API}/resources", json=SKILL))
        bad = client.put(
            f"{API}/resources/review/files/a:b.md", content=b"x", headers={"If-Match": etag}
        )
        assert bad.status_code == 400
        big = client.put(
            f"{API}/resources/review/files/SKILL.md", content=b"x" * 32, headers={"If-Match": etag}
        )
        assert big.status_code == 413
        assert client.get(f"{API}/resources/none/files").status_code == 404


# ---------------------------------------------------------------- 실행 전달


def test_run_writes_skill_and_rule_trees_only_under_run_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("mine", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("p", encoding="utf-8")
    settings = make_settings(tmp_path, options={"mod-runs": {"working_directory": "project"}})
    watched = [home, project]
    before = {p: sorted(x.relative_to(p) for x in p.rglob("*")) for p in watched}
    with server(settings, environ={"HOME": str(home)}) as client:
        etag = _etag(client.post(f"{API}/resources", json=SKILL))
        client.put(
            f"{API}/resources/review/files/SKILL.md",
            content=b"# review",
            headers={"If-Match": etag},
        )
        assert client.post(f"{API}/resources", json=RULE).status_code == 201
        assert client.post(f"{API}/agents", json=_agent("w", ["review", "api"])).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("w")).status_code == 201
        run = client.post(
            f"{API}/runs", json={"graph_id": "g-w", "input": {"request": "go"}}
        ).json()
        snap = wait_run(client, run["id"])
        assert snap["run"]["status"] == "completed"
        tree = tmp_path / "ws" / ".state" / "runs" / run["id"] / "a" / "_bundle" / "a"
        assert (tree / "skills" / "review" / "SKILL.md").read_bytes() == b"# review"
        assert (tree / "rules" / "api" / ".claude" / "rules" / "api.md").is_file()
        preview = client.get(f"{API}/graphs/g-w/nodes/a/bundle-preview").json()
        assert preview["bundle"]["slots"]["skills"][0]["name"] == "review"
    after = {p: sorted(x.relative_to(p) for x in p.rglob("*")) for p in watched}
    assert after == before
    assert (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == "mine"


def test_unsupported_hooks_slot_is_a_validation_warning(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        options={"mod-runs": {"backends": {"fake-agent": {"resource_slots": ["instructions"]}}}},
    )
    with server(settings) as client:
        assert client.post(f"{API}/resources", json=HOOK).status_code == 201
        assert client.post(f"{API}/agents", json=_agent("h", ["fmt"])).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("h")).status_code == 201
        issues = client.post(f"{API}/graphs/g-h/validate").json()
        found = [i for i in issues if i["code"] == "resource.slot_unsupported"]
        assert found
        assert found[0]["node_id"] == "a"
        assert found[0]["details"]["slot"] == "hooks"
        assert found[0]["severity"] == "warning"
        preview = client.get(f"{API}/graphs/g-h/nodes/a/bundle-preview").json()
        assert any(w["code"] == "resource.slot_unsupported" for w in preview["warnings"])


def test_fake_echo_hooks_events_are_queryable(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, options={"mod-runs": {"backends": {"fake-agent": {"echo_hooks": True}}}}
    )
    with server(settings) as client:
        assert client.post(f"{API}/resources", json=HOOK).status_code == 201
        assert client.post(f"{API}/agents", json=_agent("e", ["fmt"])).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("e")).status_code == 201
        run = client.post(
            f"{API}/runs", json={"graph_id": "g-e", "input": {"request": "go"}}
        ).json()
        assert wait_run(client, run["id"])["run"]["status"] == "completed"
        events = client.get(
            f"{API}/runs/{run['id']}/events", params={"type_prefix": "hook."}
        ).json()
        assert [e["type"] for e in events] == ["hook.started", "hook.finished"]
        assert events[1]["payload"]["event"] == "PostToolUse"
