"""2R.7 서버 API v3(design §2R.6): 검증 요약·묶음 경고·답변 계획·초안 미리보기·강제되지 않는 범위·
플러그인 상태.

테스트 전용 확장은 `plugins.modules`로 넣는다: 다른 config 키를 `reply_fields`로 선언한 답변 연결
`t-say`, `enforce`·`subagent_slots` 조합이 다른 백엔드(fake를 다른 id로).
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_modkit import PortKey
from agent_console_server.testing import API, SECRET_VALUE, make_settings, seed, server, team_graph

GRAPH_VALIDATION: PortKey[Any] = PortKey("graphs.validation")

_PLUGIN = """
from agent_console_backend_fake import FakeBackend
from agent_console_contracts import EnforceCapabilities, ReplyFields
from agent_console_nodes_core import ReplyEdge


class SayEdge(ReplyEdge):
    descriptor = ReplyEdge.descriptor.model_copy(
        update={
            "id": "t-say",
            "title": "말하기",
            "reply_fields": ReplyFields(
                label="/caption/text", order="/rank", final="/done", stream="/live"
            ),
            "config_schema": {
                "type": "object",
                "properties": {
                    "caption": {"type": "object", "properties": {"text": {"type": "string"}}},
                    "rank": {"type": "integer"},
                    "done": {"type": "boolean"},
                    "live": {"type": "boolean", "default": True},
                },
            },
        }
    )


class _Backend:
    # fake를 다른 id·능력으로 감싼다. 설정 훅(from_options)은 숨긴다: 서버가 설정 훅으로
    # 백엔드를 다시 만들면 바꾼 능력이 사라지기 때문이다.

    def __init__(self, backend_id, enforce, slots=None, subagent_slots=None):
        self._inner = FakeBackend(backend_id=backend_id, resource_slots=slots)
        caps = self._inner.descriptor.capabilities.model_copy(
            update={"enforce": enforce, "subagent_slots": subagent_slots}
        )
        self.descriptor = self._inner.descriptor.model_copy(update={"capabilities": caps})

    async def list_models(self):
        return await self._inner.list_models()

    async def run(self, *args, **kwargs):
        return await self._inner.run(*args, **kwargs)


def _backend(backend_id, enforce, slots=None, subagent_slots=None):
    return _Backend(backend_id, enforce, slots, subagent_slots)


def register(registries):
    registries.edge_types.register("t-say", SayEdge(), source="module")
    registries.backends.register(
        "t-cmd", _backend("t-cmd", EnforceCapabilities(commands=True)), source="module"
    )
    registries.backends.register(
        "t-all",
        _backend("t-all", EnforceCapabilities(directories=True, commands=True, network=True)),
        source="module",
    )
    registries.backends.register(
        "t-narrow", _backend("t-narrow", EnforceCapabilities(), slots=["files"]), source="module"
    )
    registries.backends.register(
        "t-sess",
        _backend(
            "t-sess", EnforceCapabilities(), slots=["instructions", "files"],
            subagent_slots=["files"],
        ),
        source="module",
    )
"""

MODULE = "ac_server_test_v3_views:register"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "ac_server_test_v3_views.py").write_text(
        textwrap.dedent(_PLUGIN), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(plugin_dir))
    with server(make_settings(tmp_path, plugins={"modules": [MODULE]})) as c:
        yield c


def _guide(client: TestClient, resource_id: str = "guide") -> None:
    body = {
        "id": resource_id,
        "type": "instruction",
        "name": "지침",
        "config": {"title": resource_id, "text": "짧게 답한다."},
    }
    assert client.post(f"{API}/resources", json=body).status_code == 201


def _graphs(client: TestClient, **params: Any) -> dict[str, dict[str, Any]]:
    response = client.get(f"{API}/graphs", params=params)
    assert response.status_code == 200, response.text
    return {g["id"]: g for g in response.json()}


# ---------------------------------------------------------------- GET /graphs 검증 요약


def test_graph_list_validation_summary_cache_and_opt_out(client: TestClient) -> None:
    seed(client)
    lonely = {
        "id": "lonely",
        "name": "입구 없음",
        "nodes": [{"id": "a", "type": "agent", "config": {"agent_ref": "fast"}}],
    }
    assert client.post(f"{API}/graphs", json=lonely).status_code == 201

    graphs = _graphs(client)
    ok, bad = graphs["flow"]["validation"], graphs["lonely"]["validation"]
    assert ok["blocks_run"] is False
    assert ok["error_count"] == 0
    assert bad["blocks_run"] is True
    assert bad["error_count"] >= 1
    assert "team.no_entry" in bad["codes"]
    assert all(g["validation"] is None for g in _graphs(client, validate="false").values())

    # 같은 개정이면 다시 계산하지 않는다
    source = client.app.state.assembly.port(GRAPH_VALIDATION)  # type: ignore[attr-defined]
    calls: list[str] = []
    original = source.compute

    def counting(graph_id: str) -> Any:
        calls.append(graph_id)
        return original(graph_id)

    source.compute = counting
    try:
        assert _graphs(client)["flow"]["validation"] == ok
        assert calls == []
        # 그래프가 아니라 에이전트가 바뀌어도 개정이 바뀌어 다시 계산한다(검증이 에이전트에 달림)
        etag = client.get(f"{API}/agents/fast").headers["ETag"]
        assert client.delete(f"{API}/agents/fast", headers={"If-Match": etag}).status_code == 204
        after = _graphs(client)["flow"]["validation"]
        assert sorted(calls) == ["flow", "lonely"]
        assert after["blocks_run"] is True
        assert any(code.endswith("not_found") for code in after["codes"])
    finally:
        source.compute = original


# ---------------------------------------------------------------- 답변 계획


def test_plan_reads_reply_fields_of_default_and_test_edge_types(client: TestClient) -> None:
    seed(client)
    plan = client.get(f"{API}/graphs/flow/plan")
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert [(e["edge_id"], e["node_id"], e["label"]) for e in body["entries"]] == [
        ("m1", "a", "빠른")
    ]
    answers = {a["edge_id"]: a for a in body["answers"]}
    # 기본 reply 플러그인: reply_fields{label:/label, ...}, stream은 스키마 기본값(true)
    assert answers["r1"] == {
        "edge_id": "r1",
        "node_id": "a",
        "agent_id": "fast",
        "label": "빠른",
        "order": None,
        "final": False,
        "stream": True,
    }
    assert (answers["r2"]["node_id"], answers["r2"]["final"]) == ("b", True)
    assert client.get(f"{API}/graphs/ghost/plan").status_code == 404

    # 테스트 전용 답변 연결: 다른 config 키를 reply_fields로 선언하면 그대로 읽힌다(초안)
    draft = team_graph("draft-say")
    draft["edges"] = [e for e in draft["edges"] if e["kind"] != "reply"] + [
        {
            "id": "s1",
            "source": {"node": "b", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "t-say",
            "label": "엣지 이름",
            "config": {"caption": {"text": "요약"}, "rank": 3, "done": False, "live": False},
        },
        {
            "id": "s2",
            "source": {"node": "a", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "t-say",
            "label": "엣지 이름",
            "config": {"label": "무시", "final": False},
        },
    ]
    response = client.post(f"{API}/graphs/plan", json={"graph": draft})
    assert response.status_code == 200, response.text
    said = {a["edge_id"]: a for a in response.json()["answers"]}
    assert (said["s1"]["label"], said["s1"]["order"], said["s1"]["final"]) == ("요약", 3, False)
    assert said["s1"]["stream"] is False
    # 선언하지 않은 키(label·final)는 읽지 않는다: label = 엣지 label, final = true
    assert (said["s2"]["label"], said["s2"]["final"], said["s2"]["stream"]) == (
        "엣지 이름",
        True,
        True,
    )
    assert client.get(f"{API}/graphs/draft-say").status_code == 404


def test_reply_edge_descriptor_declares_reply_fields(client: TestClient) -> None:
    edges = {e["id"]: e for e in client.get(f"{API}/edge-types").json()}
    assert edges["reply"]["reply_fields"] == {
        "label": "/label",
        "order": "/order",
        "final": "/final",
        "stream": "/stream",
    }
    assert edges["handoff"]["reply_fields"] is None


# ---------------------------------------------------------------- 묶음 미리보기·초안


def _delegation_draft(lead_backend: str, member_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "draft-team",
        "name": "초안",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {
                "id": "a",
                "type": "agent",
                "label": "리더",
                "config": {"agent_ref": "fast", "settings": {"backend": lead_backend}},
            },
            {
                "id": "b",
                "type": "agent",
                "label": "팀원",
                "config": {"agent_ref": "slow", "settings": member_settings},
            },
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
            },
            {
                "id": "d1",
                "source": {"node": "a", "port": "delegates"},
                "target": {"node": "b", "port": "delegated"},
                "kind": "subagent",
            },
            {
                "id": "r1",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
            },
        ],
    }


def test_bundle_preview_returns_bundle_and_slot_warnings(client: TestClient) -> None:
    seed(client)
    _guide(client)
    doc = client.get(f"{API}/graphs/flow").json()
    graph = doc["graph"]
    graph["nodes"][1]["config"]["settings"] = {
        "backend": "t-narrow",
        "resources": [{"ref": "guide"}],
    }
    saved = client.put(f"{API}/graphs/flow", json=graph, headers={"If-Match": doc["version_hash"]})
    assert saved.status_code == 200, saved.text
    preview = client.get(f"{API}/graphs/flow/nodes/a/bundle-preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["bundle"]["sources"]["instructions"][0]["ref"] == "guide"
    assert [(w["code"], w["severity"]) for w in body["warnings"]] == [
        ("resource.slot_unsupported", "warning")
    ]
    assert client.get(f"{API}/graphs/flow/nodes/nope/bundle-preview").status_code == 404


def test_draft_bundle_preview_warns_session_shared_slots(client: TestClient) -> None:
    seed(client)
    _guide(client)
    draft = _delegation_draft("t-sess", {"resources": [{"ref": "guide"}]})
    response = client.post(f"{API}/graphs/bundle-preview", json={"graph": draft, "node_id": "b"})
    assert response.status_code == 200, response.text
    codes = [(w["code"], w["details"].get("slot")) for w in response.json()["warnings"]]
    assert codes == [("resource.slot_session_shared", "instructions")]
    # 위임자 자신은 세션 공유 경고가 없다
    lead = client.post(f"{API}/graphs/bundle-preview", json={"graph": draft, "node_id": "a"})
    assert lead.json()["warnings"] == []
    missing = client.post(f"{API}/graphs/bundle-preview", json={"graph": draft, "node_id": "zz"})
    assert missing.status_code == 404
    assert client.get(f"{API}/graphs/draft-team").status_code == 404  # 저장하지 않음


def test_draft_effective_settings_and_preview_mask_secrets(client: TestClient) -> None:
    seed(client)
    body = {
        "id": "mcp1",
        "type": "mcp-server",
        "name": "MCP",
        "config": {"name": "srv", "command": "srv", "env": {"TOKEN": "secret://MY_API_KEY"}},
    }
    assert client.post(f"{API}/resources", json=body).status_code == 201, body
    draft = team_graph("draft-secret")
    draft["nodes"][1]["config"]["settings"] = {"resources": [{"ref": "mcp1"}]}
    eff = client.post(f"{API}/graphs/effective-settings", json={"graph": draft, "node_id": "a"})
    assert eff.status_code == 200, eff.text
    assert [r["ref"] for r in eff.json()["value"]["resources"]] == ["mcp1"]
    assert [layer["id"] for layer in eff.json()["layers"]] == ["common", "team", "agent", "node"]
    preview = client.post(f"{API}/graphs/bundle-preview", json={"graph": draft, "node_id": "a"})
    assert preview.status_code == 200, preview.text
    assert SECRET_VALUE not in preview.text
    assert "secret://MY_API_KEY" in preview.text  # 참조는 그대로
    assert client.get(f"{API}/graphs/draft-secret").status_code == 404


# ---------------------------------------------------------------- 강제되지 않는 범위


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        ("fake", ["/limits/commands", "/limits/network"]),
        ("t-cmd", ["/limits/network"]),
        ("t-all", []),
    ],
)
def test_limits_not_enforced_follow_backend_enforce(
    client: TestClient, backend: str, expected: list[str]
) -> None:
    seed(client)
    draft = team_graph("draft-limits")
    draft["settings"] = {"limits": {"commands": ["git"], "network": "deny"}}
    draft["nodes"][1]["config"]["settings"] = {"backend": backend}
    eff = client.post(f"{API}/graphs/effective-settings", json={"graph": draft, "node_id": "a"})
    assert eff.status_code == 200, eff.text
    found = sorted(w["path"] for w in eff.json()["warnings"] if w["code"] == "limits.not_enforced")
    assert found == expected


def test_saved_node_and_agent_effective_settings_warn_not_enforced(client: TestClient) -> None:
    seed(client)
    doc = client.get(f"{API}/agents/fast")
    agent = doc.json()
    agent["limits"] = {"directories": ["{workspace}"]}
    saved = client.put(f"{API}/agents/fast", json=agent, headers={"If-Match": doc.headers["ETag"]})
    assert saved.status_code == 200, saved.text
    for url in (
        f"{API}/agents/fast/effective-settings",
        f"{API}/graphs/flow/nodes/a/effective-settings",
    ):
        warnings = client.get(url).json()["warnings"]
        assert [(w["code"], w["path"]) for w in warnings] == [
            ("limits.not_enforced", "/limits/directories")
        ]


# ---------------------------------------------------------------- 플러그인 상태


def test_server_info_plugin_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "ac_server_test_v3_status.py").write_text(
        textwrap.dedent(_PLUGIN), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(plugin_dir))
    settings = make_settings(
        tmp_path,
        plugins={
            "modules": ["ac_server_test_v3_status:register", "ac_server_test_missing_zz:register"],
            "enabled": ["fake", "t-cmd", "agent", "user", "reply", "message"],
        },
    )
    with server(settings) as client:
        plugins = client.get(f"{API}/server-info").json()["plugins"]
    statuses = {p["status"] for p in plugins}
    assert {"loaded", "failed", "skipped", "disabled"} <= statuses
    for p in plugins:
        assert p["loaded"] is (p["status"] == "loaded")
        assert (p["error"] is not None) is (p["status"] == "failed")
    disabled = {p["name"] for p in plugins if p["status"] == "disabled"}
    assert {"t-say", "t-all"} <= disabled
