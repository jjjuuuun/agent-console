"""1R.37: 정의 GET = 저장 원문("생략 = 상속"), 리소스 평문 비밀 저장 거부(R12.2·R12.3·R13.6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server, team_graph

PLAIN = "sk-live-123456"


def _etag(response: Any) -> str:
    value: str = response.headers["etag"]
    return value.strip('"')


def test_agent_round_trip_keeps_explicit_defaults_and_omits_unset(tmp_path: Path) -> None:
    doc: dict[str, Any] = {
        "id": "a1",
        "name": "에이전트",
        "backend": "fake",
        "description": "",  # 기본값과 같은 값을 일부러 지정
        "model": None,  # 명시 null
        "tools": [],  # 명시 빈 목록
    }
    with server(make_settings(tmp_path)) as client:
        created = client.post(f"{API}/agents", json=doc)
        assert created.status_code == 201
        assert created.json() == doc
        got = client.get(f"{API}/agents/a1")
        assert got.json() == doc
        assert "role" not in got.json()  # 생략한 키는 응답에도 없다
        assert "limits" not in got.json()
        assert _etag(got) == _etag(created)
        assert client.get(f"{API}/agents").json() == [doc]
        changed = {**doc, "role": "검토"}
        put = client.put(f"{API}/agents/a1", json=changed, headers={"If-Match": _etag(got)})
        assert put.status_code == 200
        assert put.json() == changed
        assert _etag(put) != _etag(got)


def test_graph_round_trip_and_duplicate_are_stored_documents(tmp_path: Path) -> None:
    doc = {**team_graph(), "description": ""}
    with server(make_settings(tmp_path)) as client:
        created = client.post(f"{API}/graphs", json=doc)
        assert created.status_code == 201
        body = created.json()
        assert body["graph"] == doc
        assert body["version_hash"] == _etag(created)
        got = client.get(f"{API}/graphs/flow")
        assert got.json()["graph"] == doc
        assert "settings" not in got.json()["graph"]
        assert "config" not in got.json()["graph"]["nodes"][0]
        assert _etag(got) == got.json()["version_hash"]
        put = client.put(f"{API}/graphs/flow", json=doc, headers={"If-Match": _etag(got)})
        assert put.json()["graph"] == doc
        dup = client.post(f"{API}/graphs/flow/duplicate", json={"id": "flow2", "name": "복제"})
        assert dup.status_code == 201
        assert dup.json()["graph"] == {**doc, "id": "flow2", "name": "복제"}
        assert dup.headers["etag"]


def test_resource_round_trip_is_stored_document(tmp_path: Path) -> None:
    doc = {"id": "tip", "type": "instruction", "name": "팁", "labels": []}
    with server(make_settings(tmp_path)) as client:
        created = client.post(f"{API}/resources", json=doc)
        assert created.status_code == 201, created.text
        assert created.json() == doc
        got = client.get(f"{API}/resources/tip")
        assert got.json() == doc
        assert "config" not in got.json()
        assert _etag(got) == _etag(created)


def test_settings_get_put_does_not_grow_file(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        assert client.get(f"{API}/settings").json() == {}
        first = {"default_backend": "fake", "chat": {"busy_policy": "queue"}}
        assert client.put(f"{API}/settings", json=first).status_code == 200
        [path] = list(settings.workspace_path.rglob("settings*.yaml"))
        before = path.read_text(encoding="utf-8")
        got = client.get(f"{API}/settings")
        assert got.json() == first  # 기본값과 같은 명시값(queue)도 그대로, 나머지 키는 없다
        again = client.put(f"{API}/settings", json=got.json(), headers={"If-Match": _etag(got)})
        assert again.status_code == 200
        assert again.json() == first
        assert _etag(again) == _etag(got)  # 같은 원문 → 같은 버전
        assert path.read_text(encoding="utf-8") == before
        assert len(before.splitlines()) <= 3


def _mcp(env_value: str) -> dict[str, Any]:
    return {
        "id": "gh",
        "type": "mcp-server",
        "name": "gh",
        "config": {"name": "gh", "command": "npx", "env": {"API_KEY": env_value}},
    }


def test_resource_plain_secret_is_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        rejected = client.post(f"{API}/resources", json=_mcp(PLAIN))
        assert rejected.status_code == 422
        error = rejected.json()["error"]
        assert error["code"] == "validation_failed"
        plain = [i for i in error["details"]["issues"] if i["code"] == "resource.plain_secret"]
        assert [(i["severity"], i["path"]) for i in plain] == [("error", "/config/env/API_KEY")]
        assert all(i["path"].startswith("/config/") for i in error["details"]["issues"])
        assert all(PLAIN not in i["message"] for i in error["details"]["issues"])
        assert PLAIN not in rejected.text
        assert client.get(f"{API}/resources/gh").status_code == 404

        ok = client.post(f"{API}/resources", json=_mcp("secret://GH_TOKEN"))
        assert ok.status_code == 201, ok.text
        put = client.put(f"{API}/resources/gh", json=_mcp(PLAIN), headers={"If-Match": _etag(ok)})
        assert put.status_code == 422
        assert put.json()["error"]["code"] == "validation_failed"
        assert PLAIN not in put.text
        assert client.get(f"{API}/resources/gh").json() == _mcp("secret://GH_TOKEN")


def test_resource_of_unknown_type_is_still_saved(tmp_path: Path) -> None:
    """등록되지 않은 종류는 warning뿐이므로 저장한다(플러그인을 나중에 설치할 수 있다)."""
    doc = {"id": "later", "type": "not-installed-yet", "name": "나중", "config": {"k": PLAIN}}
    with server(make_settings(tmp_path)) as client:
        assert client.post(f"{API}/resources", json=doc).status_code == 201
