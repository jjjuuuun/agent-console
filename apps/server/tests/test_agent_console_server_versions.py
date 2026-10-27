"""버전 비교·되돌리기 API(2R.13, design §2R.9, R2.5·R10.2)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server import create_app
from agent_console_server.testing import API, make_settings, seed, server

PLAIN = "plain-legacy-zz77"


def _etag(response: Any) -> str:
    return str(response.headers["etag"])


def _versions(client: TestClient, base: str) -> list[dict[str, Any]]:
    response = client.get(f"{base}/versions")
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()
    return body


def test_graph_diff_and_restore(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        created = seed(client)
        old_hash = created["version_hash"]
        graph = copy.deepcopy(created["graph"])
        graph["nodes"][1]["label"] = "아주 빠른"
        graph["nodes"].pop(2)
        graph["edges"] = [e for e in graph["edges"] if e["id"] not in ("h1", "r2")]
        put = client.put(f"{API}/graphs/flow", json=graph, headers={"If-Match": old_hash})
        assert put.status_code == 200, put.text
        new_hash = put.json()["version_hash"]

        diff = client.get(f"{API}/graphs/flow/versions/{old_hash}/diff")
        assert diff.status_code == 200, diff.text
        body = diff.json()
        assert (body["kind"], body["id"]) == ("graph", "flow")
        assert (body["from_hash"], body["to_hash"]) == (old_hash, new_hash)
        changes = {(c["op"], c["path"]): c for c in body["changes"]}
        label = changes[("replace", "/nodes/1/label")]
        assert (label["before"], label["after"], label["secret"]) == ("빠른", "아주 빠른", False)
        assert ("remove", "/nodes/2") in changes
        assert changes[("remove", "/nodes/2")]["before"]["id"] == "b"
        assert body["content_changes"] == []
        # 두 버전을 명시해도 같다, 반대 방향은 add
        explicit = client.get(f"{API}/graphs/flow/versions/{old_hash}/diff/{new_hash}").json()
        assert explicit == body
        back = client.get(f"{API}/graphs/flow/versions/{new_hash}/diff/{old_hash}").json()
        assert ("add", "/nodes/2") in {(c["op"], c["path"]) for c in back["changes"]}
        same = client.get(f"{API}/graphs/flow/versions/{new_hash}/diff").json()
        assert same["changes"] == []
        assert same["content_changes"] == []

        # 되돌리기: If-Match 필수(428), 다르면 412
        url = f"{API}/graphs/flow/versions/{old_hash}/restore"
        assert client.post(url).status_code == 428
        stale = client.post(url, headers={"If-Match": old_hash})
        assert stale.status_code == 412
        restored = client.post(url, headers={"If-Match": new_hash}, json={})
        assert restored.status_code == 200, restored.text
        version = restored.json()
        assert version["message"] == f"restored from {old_hash}"
        assert _etag(restored).strip('"') == version["version_hash"]
        current = client.get(f"{API}/graphs/flow").json()
        assert current["graph"] == created["graph"]
        assert current["version_hash"] == version["version_hash"]
        # 이력은 지우지 않는다
        hashes = [v["version_hash"] for v in _versions(client, f"{API}/graphs/flow")]
        assert new_hash in hashes
        assert old_hash in hashes
        assert client.get(f"{API}/graphs/flow/versions/{'f' * 64}/diff").status_code == 404


def test_resource_body_changes_and_restore(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        made = client.post(
            f"{API}/resources", json={"id": "guide", "type": "instruction", "name": "가이드"}
        )
        assert made.status_code == 201, made.text
        first = client.put(
            f"{API}/resources/guide/content",
            content="첫 번째 본문".encode(),
            headers={"If-Match": _etag(made), "Content-Type": "text/markdown"},
        )
        assert first.status_code == 200, first.text
        v1 = _etag(first).strip('"')
        second = client.put(
            f"{API}/resources/guide/content",
            content="두 번째 본문".encode(),
            headers={"If-Match": _etag(first), "Content-Type": "text/markdown"},
        )
        assert second.status_code == 200, second.text
        v2 = _etag(second).strip('"')

        diff = client.get(f"{API}/resources/guide/versions/{v1}/diff").json()
        assert diff["to_hash"] == v2
        assert diff["changes"] == []  # 문서는 같고 본문만 바뀌었다
        [content] = diff["content_changes"]
        assert content["path"] == "content.md"
        assert content["before_hash"]
        assert content["after_hash"]
        assert content["before_hash"] != content["after_hash"]

        files = client.get(f"{API}/resources/guide/versions/{v1}/files").json()
        assert [(f["path"], f["sha256"]) for f in files] == [("content.md", content["before_hash"])]
        old_text = client.get(f"{API}/resources/guide/versions/{v1}/files/content.md")
        assert old_text.status_code == 200
        assert old_text.content.decode() == "첫 번째 본문"
        assert old_text.headers["content-type"].startswith("text/plain")
        missing = client.get(f"{API}/resources/guide/versions/{v1}/files/nope.md")
        assert missing.status_code == 404

        restored = client.post(
            f"{API}/resources/guide/versions/{v1}/restore",
            headers={"If-Match": v2},
            json={"message": "되돌림"},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["message"] == "되돌림"
        assert client.get(f"{API}/resources/guide/content").content.decode() == "첫 번째 본문"
        # 같은 파일 집합이면 원래 해시로 돌아온다(design §2R.3)
        assert restored.json()["version_hash"] == v1


def test_plain_secret_masked_in_diff_and_restore_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resources = settings.workspace_path / "resources"
    resources.mkdir(parents=True)
    legacy: dict[str, Any] = {
        "id": "gh",
        "type": "mcp-server",
        "name": "gh",
        "config": {"name": "gh", "command": "npx", "env": {"API_KEY": PLAIN}},
    }
    (resources / "gh.yaml").write_text(json.dumps(legacy), encoding="utf-8")
    with server(settings) as client:
        current = client.get(f"{API}/resources/gh")
        assert current.status_code == 200
        legacy_hash = _etag(current).strip('"')
        fixed = {**legacy, "config": {**legacy["config"], "env": {"API_KEY": "secret://GH"}}}
        put = client.put(f"{API}/resources/gh", json=fixed, headers={"If-Match": _etag(current)})
        assert put.status_code == 200, put.text
        fixed_hash = _etag(put).strip('"')

        diff = client.get(f"{API}/resources/gh/versions/{legacy_hash}/diff")
        assert diff.status_code == 200, diff.text
        assert PLAIN not in diff.text
        [change] = diff.json()["changes"]
        assert change == {
            "op": "replace",
            "path": "/config/env/API_KEY",
            "before": "***",
            "after": "***",
            "secret": True,
        }

        rejected = client.post(
            f"{API}/resources/gh/versions/{legacy_hash}/restore",
            headers={"If-Match": fixed_hash},
        )
        assert rejected.status_code == 422, rejected.text
        assert PLAIN not in rejected.text
        error = rejected.json()["error"]
        assert error["code"] == "validation_failed"
        assert "/config/env/API_KEY" in [i["path"] for i in error["details"]["issues"]]
        # 아무것도 저장되지 않았다
        assert _etag(client.get(f"{API}/resources/gh")).strip('"') == fixed_hash


def test_deleted_agent_is_restored_without_if_match(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        made = client.post(
            f"{API}/agents", json={"id": "a1", "name": "에이", "backend": "fake-agent"}
        )
        assert made.status_code == 201
        first = _etag(made).strip('"')
        assert client.delete(f"{API}/agents/a1").status_code == 204
        assert client.get(f"{API}/agents/a1").status_code == 404
        assert client.get(f"{API}/agents/a1/versions/{first}/diff").status_code == 404
        listed = _versions(client, f"{API}/agents/a1")
        assert [v["version_hash"] for v in listed] == [first]

        restored = client.post(f"{API}/agents/a1/versions/{first}/restore")
        assert restored.status_code == 200, restored.text
        assert client.get(f"{API}/agents/a1").json()["name"] == "에이"
        # 되살린 뒤에는 If-Match가 필요하다
        again = client.post(f"{API}/agents/a1/versions/{first}/restore")
        assert again.status_code == 428
        # 본문이 없는 종류는 본문 스냅샷이 없다(404) -- 비교의 content_changes는 비어 있다
        assert client.get(f"{API}/agents/a1/versions/{first}/files").status_code == 404
        diff = client.get(f"{API}/agents/a1/versions/{first}/diff").json()
        assert diff["changes"] == []
        assert diff["content_changes"] == []


def test_settings_versions_diff_and_restore(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        one = client.put(f"{API}/settings", json={"default_model": "m1"})
        assert one.status_code == 200, one.text
        two = client.put(f"{API}/settings", json={"default_model": "m2"})
        assert two.status_code == 200, two.text
        h1, h2 = _etag(one).strip('"'), _etag(two).strip('"')
        assert {v["version_hash"] for v in _versions(client, f"{API}/settings")} >= {h1, h2}
        [change] = client.get(f"{API}/settings/versions/{h1}/diff").json()["changes"]
        assert (change["op"], change["path"], change["before"], change["after"]) == (
            "replace",
            "/default_model",
            "m1",
            "m2",
        )
        restored = client.post(f"{API}/settings/versions/{h1}/restore", headers={"If-Match": h2})
        assert restored.status_code == 200, restored.text
        assert client.get(f"{API}/settings").json() == {"default_model": "m1"}


def test_openapi_lists_version_routes(tmp_path: Path) -> None:
    paths = create_app(make_settings(tmp_path), environ={}).openapi()["paths"]
    for base in (
        "/api/v1/agents/{agent_id}",
        "/api/v1/graphs/{graph_id}",
        "/api/v1/resources/{resource_id}",
        "/api/v1/settings",
    ):
        assert f"{base}/versions" in paths
        diff = paths[f"{base}/versions/{{version_hash}}/diff/{{to_hash}}"]["get"]
        schema = diff["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/DefinitionDiff"}
        restore = paths[f"{base}/versions/{{version_hash}}/restore"]["post"]
        assert {"412", "422", "428"} <= set(restore["responses"])
        assert restore["security"] == [{"ConsoleToken": []}]


def test_version_file_path_escape_rejected_and_attachment(tmp_path: Path) -> None:
    """QA 2R.13: files/{path}는 스냅샷 목록의 키만 읽는다(../·절대경로·인코딩 우회 = 404)."""
    outside = tmp_path / "outside.txt"
    outside.write_text("TOPSECRET", encoding="utf-8")
    with server(make_settings(tmp_path)) as client:
        made = client.post(
            f"{API}/resources", json={"id": "guide", "type": "instruction", "name": "g"}
        )
        put = client.put(
            f"{API}/resources/guide/content",
            content=b"hello",
            headers={"If-Match": _etag(made), "Content-Type": "text/markdown"},
        )
        v1 = _etag(put).strip('"')
        base = f"{API}/resources/guide/versions/{v1}/files"
        ok = client.get(f"{base}/content.md")
        assert ok.status_code == 200
        assert ok.headers["content-disposition"].startswith("attachment")
        assert ok.headers["content-type"].startswith("text/plain")
        for bad in (
            "../../../outside.txt",
            "..%2F..%2F..%2Foutside.txt",
            "%2e%2e/%2e%2e/outside.txt",
            "/etc/passwd",
            "%2Fetc%2Fpasswd",
            "..\\..\\outside.txt",
            "content.md/../../guide.yaml",
        ):
            r = client.get(f"{base}/{bad}")
            assert r.status_code in (400, 404, 422), (bad, r.status_code)
            assert "TOPSECRET" not in r.text
            assert "root:" not in r.text
