"""1R.14 REST 통합(fake): §R9.5 경로와 1R.17 api-client 가정(라우트 순서, ETag, 필터, 응답 형식).

리소스·본문 ETag, `.claude` 가져오기(원본 무변경), 사용량, 디스크립터,
유효 설정·묶음 미리보기, 복제,
실행 필터·이벤트·위임 흐름·집계, 에이전트 사용처·활동, 서버 정보, auth_missing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    seed,
    seed_chat,
    server,
    wait_run,
)


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    out: dict[str, tuple[bytes, int]] = {}
    for current, _, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            out[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
    return out


def _resource(resource_id: str = "guide", **extra: Any) -> dict[str, Any]:
    return {
        "id": resource_id,
        "type": "instruction",
        "name": "팀 지침",
        "config": {"title": "지침"},
        "content": {"file": "content.md", "media_type": "text/markdown"},
        **extra,
    }


# ---------------------------------------------------------------- 디스크립터·서버 정보


def test_descriptors_and_server_info(tmp_path: Path) -> None:
    (tmp_path / "ws" / "resource-types").mkdir(parents=True)
    (tmp_path / "ws" / "resource-types" / "tip.yaml").write_text(
        "id: tip\ntitle: 팁\nconfig_schema: {type: object}\n"
        "contributes: [{slot: instructions, template: '{name}'}]\n",
        encoding="utf-8",
    )
    with server(make_settings(tmp_path)) as client:
        types = {t["id"] for t in client.get(f"{API}/resource-types").json()}
        assert {"instruction", "file", "mcp-server", "tool-permission", "tip"} <= types
        strategies = {s["id"] for s in client.get(f"{API}/delegation-strategies").json()}
        assert "sdk-subagents" in strategies
        merge = {m["id"] for m in client.get(f"{API}/merge-strategies").json()}
        assert {"replace", "merge", "append", "union", "intersect", "keyed_attachments"} <= merge
        edge_ids = {e["id"] for e in client.get(f"{API}/edge-types").json()}
        assert "router" not in {n["id"] for n in client.get(f"{API}/node-types").json()}
        assert {"message", "reply", "ask_user"} <= edge_ids
        info = client.get(f"{API}/server-info").json()
        assert info["contracts_version"]
        groups = {p["group"] for p in info["plugins"]}
        assert {"runtime", "resource_types", "usage_sources", "import_sources"} <= groups
        assert "token" not in json.dumps(info).lower()


# ---------------------------------------------------------------- 리소스


def test_resource_crud_content_etag_and_usages(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        created = client.post(f"{API}/resources", json=_resource())
        assert created.status_code == 201
        etag = created.headers["ETag"]
        assert client.post(f"{API}/resources", json=_resource()).status_code == 409

        put = client.put(
            f"{API}/resources/guide/content",
            content="# 규칙\n짧게.".encode(),
            headers={"If-Match": etag, "Content-Type": "text/plain; charset=utf-8"},
        )
        assert put.status_code == 200, put.text
        new_etag = put.headers["ETag"]
        assert new_etag != etag
        got = client.get(f"{API}/resources/guide/content")
        assert got.text == "# 규칙\n짧게."
        assert got.headers["content-type"].startswith("text/markdown")  # 기존 형식 유지
        assert got.headers["ETag"] == new_etag
        stale = client.put(
            f"{API}/resources/guide/content", content=b"x", headers={"If-Match": etag}
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "version_conflict"
        assert stale.headers["ETag"] == new_etag

        no_match = client.put(f"{API}/resources/guide", json=_resource(name="바꿈"))
        assert no_match.status_code == 428
        renamed = client.put(
            f"{API}/resources/guide", json=_resource(name="바꿈"), headers={"If-Match": new_etag}
        )
        assert renamed.status_code == 200

        client.post(f"{API}/resources", json=_resource("other", type="tool-permission"))
        typed = client.get(f"{API}/resources", params={"type": "instruction"}).json()
        assert [r["id"] for r in typed] == ["guide"]

        agent = agent_doc("a1", "x", resources=[{"ref": "guide"}])
        client.post(f"{API}/agents", json=agent)
        usages = client.get(f"{API}/resources/guide/usages").json()
        assert [(u["kind"], u["id"], u["layer"]) for u in usages] == [("agent", "a1", "agent")]
        eff = client.get(f"{API}/agents/a1/effective-settings").json()
        assert eff["value"]["resources"][0]["ref"] == "guide"
        assert eff["provenance"]["/backend"] == "agent"

        assert client.get(f"{API}/resources/other/content").status_code == 404
        current = client.get(f"{API}/resources/guide").headers["ETag"]
        assert (
            client.delete(f"{API}/resources/guide", headers={"If-Match": '"old"'}).status_code
            == 412
        )
        assert (
            client.delete(f"{API}/resources/guide", headers={"If-Match": current}).status_code
            == 204
        )
        assert client.get(f"{API}/resources/guide").status_code == 404


# ---------------------------------------------------------------- 가져오기


def test_claude_import_reads_only(tmp_path: Path) -> None:
    home = tmp_path / "fakehome"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("전역 지침", encoding="utf-8")
    (home / ".claude" / "agents" / "helper.md").write_text(
        "---\nname: helper\ndescription: 돕는다\n---\n도와준다.", encoding="utf-8"
    )
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"gh": {"url": "https://x.invalid", "headers": {"A": "plain"}}}}),
        encoding="utf-8",
    )
    before = _snapshot(home) | _snapshot(project)
    settings = make_settings(tmp_path, options={"mod-imports": {"project_dir": str(project)}})
    with server(settings, environ={"HOME": str(home)}) as client:
        sources = {s["id"]: s for s in client.get(f"{API}/resources/import/sources").json()}
        assert sources["user-claude"]["available"] is True
        preview = client.post(f"{API}/resources/import/preview", json={"source": "user-claude"})
        assert preview.status_code == 200
        candidates = preview.json()["candidates"]
        assert {c["kind"] for c in candidates} == {"agent", "resource"}
        result = client.post(
            f"{API}/resources/import",
            json={
                "source": "user-claude",
                "items": [{"candidate_id": c["id"]} for c in candidates],
            },
        ).json()
        assert {i["action"] for i in result["items"]} == {"created"}
        assert client.get(f"{API}/agents/helper").json()["system_prompt"] == "도와준다."

        mcp = client.post(f"{API}/resources/import/preview", json={"source": "project-claude"})
        [server_item] = [c for c in mcp.json()["candidates"] if c["resource_type"] == "mcp-server"]
        client.post(
            f"{API}/resources/import",
            json={"source": "project-claude", "items": [{"candidate_id": server_item["id"]}]},
        )
        stored = client.get(f"{API}/resources/{server_item['suggested_id']}").json()
        assert "plain" not in json.dumps(stored)
        missing = client.post(f"{API}/resources/import/preview", json={"source": "nope"})
        assert missing.status_code == 404
    assert _snapshot(home) | _snapshot(project) == before  # 원본(가짜 ~/.claude) 무변경


# ---------------------------------------------------------------- 사용량


def test_usage_report_and_sources(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        settings = client.get(f"{API}/settings").json()
        settings.setdefault("usage", {})["sources"] = [
            {"id": "fake", "config": {"windows": [{"window": "five_hour", "used_ratio": 0.25}]}}
        ]
        assert client.put(f"{API}/settings", json=settings).status_code == 200
        seed_chat(client)
        run = client.post(f"{API}/runs", json={"graph_id": "chat", "input": {"text": "hi"}}).json()
        wait_run(client, run["id"])
        report = client.get(f"{API}/usage").json()
        windows = {(w["source"], w["window"]): w for w in report["windows"]}
        assert windows[("fake", "five_hour")]["used_ratio"] == 0.25
        assert report["rollups"]
        sources = {s["descriptor"]["id"]: s for s in client.get(f"{API}/usage/sources").json()}
        assert {"fake", "run-events", "statusline-file"} <= set(sources)
        assert sources["fake"]["last_observed_at"] is not None


# ---------------------------------------------------------------- 팀 구성·실행


def test_graph_duplicate_effective_bundle_and_summaries(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        short = _resource(content=None, config={"title": "지침", "text": "짧게 답한다."})
        assert client.post(f"{API}/resources", json=short).status_code == 201
        seed(client)
        dup = client.post(f"{API}/graphs/flow/duplicate", json={"id": "flow2", "name": "복제본"})
        assert dup.status_code == 201
        assert dup.json()["graph"]["name"] == "복제본"
        assert dup.json()["version_hash"] == dup.headers["ETag"].strip('"')
        conflict = client.post(f"{API}/graphs/flow/duplicate", json={"id": "flow2", "name": "x"})
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "already_exists"
        assert (
            client.post(f"{API}/graphs/ghost/duplicate", json={"id": "g3", "name": "x"}).status_code
            == 404
        )

        summaries = {g["id"]: g for g in client.get(f"{API}/graphs").json()}
        assert summaries["flow"]["entry_labels"] == ["빠른"]

        eff = client.get(f"{API}/graphs/flow/nodes/a/effective-settings").json()
        assert eff["value"]["backend"] == "fake-agent"
        assert [layer["id"] for layer in eff["layers"]] == ["common", "team", "agent", "node"]
        assert client.get(f"{API}/graphs/flow/nodes/nope/effective-settings").status_code == 404

        graph = client.get(f"{API}/graphs/flow").json()
        doc = graph["graph"]
        doc["nodes"][1]["config"]["settings"] = {"resources": [{"ref": "guide"}]}
        saved = client.put(
            f"{API}/graphs/flow", json=doc, headers={"If-Match": graph["version_hash"]}
        )
        assert saved.status_code == 200
        bundle = client.get(f"{API}/graphs/flow/nodes/a/bundle-preview").json()
        assert bundle["bundle"]["sources"]["instructions"][0]["ref"] == "guide"
        usages = client.get(f"{API}/resources/guide/usages").json()
        assert [(u["id"], u["node_ids"], u["layer"]) for u in usages] == [("flow", ["a"], "node")]

        agent_usages = client.get(f"{API}/agents/fast/usages").json()
        assert sorted((u["id"], tuple(u["node_ids"])) for u in agent_usages) == [
            ("flow", ("a",)),
            ("flow2", ("a",)),
        ]


def test_runs_filters_events_trace_handoffs_activity(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed(client)
        run = client.post(
            f"{API}/runs", json={"graph_id": "flow", "input": {"request": "go"}}
        ).json()
        assert wait_run(client, run["id"])["run"]["status"] == "completed"

        assert [r["id"] for r in client.get(f"{API}/runs", params={"agent_id": "slow"}).json()] == [
            run["id"]
        ]
        assert client.get(f"{API}/runs", params={"agent_id": "nobody"}).json() == []
        assert (
            client.get(f"{API}/runs", params={"status": "completed"}).json()[0]["id"] == run["id"]
        )
        assert client.get(f"{API}/runs", params={"status": "bogus"}).status_code == 400
        assert client.get(f"{API}/runs", params={"limit": 0}).status_code == 400

        by_actor = client.get(f"{API}/runs/{run['id']}/events", params={"actor": "slow"}).json()
        assert by_actor
        assert {e["actor"] for e in by_actor} == {"slow"}
        agents_only = client.get(
            f"{API}/runs/{run['id']}/events", params={"type_prefix": "agent."}
        ).json()
        assert all(e["type"].startswith("agent.") for e in agents_only)

        trace = client.get(f"{API}/runs/{run['id']}/trace").json()
        assert trace["run_id"] == run["id"]
        assert {s["node_id"] for s in trace["spans"]} >= {"a", "b"}
        assert trace["links"][0]["kind"] == "handoff"

        matrix = client.get(
            f"{API}/runs/handoffs", params={"graph_id": "flow"}
        ).json()  # 순서: /runs/{id}보다 먼저
        assert matrix["runs"] == 1
        assert [(c["source"], c["target"], c["count"]) for c in matrix["cells"]] == [
            ("fast", "slow", 1)
        ]
        assert client.get(f"{API}/runs/missing/trace").status_code == 404

        activity = client.get(f"{API}/agents/fast/activity", params={"limit": 3}).json()
        assert 0 < len(activity) <= 3
        assert all(e["actor"] == "fast" for e in activity)


def test_validate_reports_team_rules_once(tmp_path: Path) -> None:
    """검증 = 엔진 검증 + 팀 규칙(`validate_team(graph_checks=False)`).

    구조 이슈는 한 번만 나온다.
    """
    with server(make_settings(tmp_path)) as client:
        seed(client)
        doc = client.get(f"{API}/graphs/flow").json()["graph"]
        doc["edges"] = [e for e in doc["edges"] if e["kind"] != "message"]
        issues = client.post(f"{API}/graphs/flow/validate", json=doc).json()
        codes = [i["code"] for i in issues]
        assert codes.count("team.no_entry") == 1
        blocked = client.put(
            f"{API}/graphs/flow",
            json=doc,
            headers={"If-Match": client.get(f"{API}/graphs/flow").json()["version_hash"]},
        )
        assert blocked.status_code == 200  # 초안 저장은 허용
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {}})
        assert run.status_code == 422
        assert run.json()["error"]["code"] == "validation_failed"


def test_claude_sdk_without_key_fails_with_auth_missing(tmp_path: Path) -> None:
    """실제 백엔드(claude-sdk)도 조립된다.

    API 키 방식인데 키가 없으면 노드가 auth_missing으로 실패한다.
    """
    with server(make_settings(tmp_path), environ={}) as client:
        assert "claude-agent-sdk" in {b["id"] for b in client.get(f"{API}/backends").json()}
        agent = {
            "id": "real",
            "name": "실제",
            "backend": "claude-agent-sdk",
            "backend_options": {"auth": {"mode": "api_key"}},
        }
        assert client.post(f"{API}/agents", json=agent).status_code == 201
        graph: dict[str, Any] = {
            "id": "g",
            "name": "g",
            "nodes": [
                {"id": "you", "type": "user"},
                {"id": "a", "type": "agent", "config": {"agent_ref": "real"}},
            ],
            "edges": [
                {
                    "id": "m",
                    "source": {"node": "you", "port": "says"},
                    "target": {"node": "a", "port": "in"},
                    "kind": "message",
                }
            ],
        }
        client.post(f"{API}/graphs", json=graph)
        run = client.post(f"{API}/runs", json={"graph_id": "g", "input": {"text": "hi"}}).json()
        snap = wait_run(client, run["id"])
        [node] = snap["node_runs"]
        assert node["status"] == "failed"
        assert node["error"]["code"] == "auth_missing"


def _cors_client(tmp_path: Path, origin: str) -> Any:
    return server(make_settings(tmp_path, security={"allowed_origins": [origin]}), with_token=False)


def test_cors_allowed_origin_preflight_and_expose_etag(tmp_path: Path) -> None:
    origin = "http://localhost:5173"
    with _cors_client(tmp_path, origin) as client:
        pre = client.options(
            f"{API}/graphs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "X-Console-Token, If-Match",
            },
        )
        assert pre.status_code == 204
        assert pre.headers["access-control-allow-origin"] == origin
        assert "If-Match" in pre.headers["access-control-allow-headers"]
        assert "PUT" in pre.headers["access-control-allow-methods"]

        denied = client.options(
            f"{API}/graphs",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers
        bad_host = client.options(
            f"{API}/graphs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Host": "evil.example",
            },
        )
        assert bad_host.status_code == 403

        boot = client.get(
            f"{API}/bootstrap", headers={"Origin": origin, "Sec-Fetch-Site": "cross-site"}
        )
        assert boot.status_code == 200
        assert boot.headers["access-control-allow-origin"] == origin
        assert boot.headers["access-control-expose-headers"] == "ETag, X-Console-Issues"
        other = client.get(
            f"{API}/bootstrap",
            headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"},
        )
        assert other.status_code == 403

        token = boot.json()["token"]
        created = client.post(
            f"{API}/agents",
            json=agent_doc("x", "y"),
            headers={"Origin": origin, "X-Console-Token": token},
        )
        assert created.status_code == 201
        assert created.headers["access-control-expose-headers"] == "ETag, X-Console-Issues"
        unauth = client.post(f"{API}/agents", json=agent_doc("z", "y"), headers={"Origin": origin})
        assert unauth.status_code == 401
        assert unauth.headers["access-control-allow-origin"] == origin  # 오류도 읽을 수 있게


def test_unknown_api_path_is_json_404(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        response = client.get(f"{API}/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        bad_json = client.post(
            f"{API}/agents", content=b"{bad", headers={"Content-Type": "application/json"}
        )
        assert bad_json.status_code == 400
        invalid = client.post(f"{API}/agents", json={"id": "!"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["details"]["issues"]
