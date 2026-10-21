"""2R.21 확장성: `rerunnable` 노드 타입을 플러그인 모듈 하나로 추가한다(서버 코드 수정 없음).

디스크립터의 `rerunnable`만이 "이 지점부터 다시 실행"의 가능 여부를 정한다.
플러그인 타입 `t-redo`(rerunnable = true)는 이어 가면 다시 열린다.
`t-once`(rerunnable = false)는 선택지에 나오지만 이어 갈 수 없다(422 `resume.not_rerunnable`).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_server import ServerSettings
from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    pending_of,
    server,
    wait_run,
)

_PLUGIN = """
from agent_console_nodes_core import UserNode


class Redo(UserNode):
    descriptor = UserNode.descriptor.model_copy(
        update={"id": "t-redo", "title": "다시 열리는 검토", "rerunnable": True}
    )


class Once(UserNode):
    descriptor = UserNode.descriptor.model_copy(
        update={"id": "t-once", "title": "한 번만 검토", "rerunnable": False}
    )


def register(registries):
    registries.node_types.register("t-redo", Redo(), source="module")
    registries.node_types.register("t-once", Once(), source="module")
"""

REVIEW = {
    "title": "설계안 검토",
    "decisions": [{"id": "approved", "label": "승인"}, {"id": "rejected", "label": "반려"}],
}


def _edge(edge_id: str, src: tuple[str, str], dst: tuple[str, str], kind: str) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
        "kind": kind,
    }


def _team(client: TestClient, review_type: str) -> None:
    assert client.post(f"{API}/agents", json=agent_doc("pl", "설계: $prompt")).status_code == 201
    assert client.post(f"{API}/agents", json=agent_doc("be", "구현: $prompt")).status_code == 201
    graph = {
        "id": "review",
        "name": "검토 팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "pl", "type": "agent", "label": "PL", "config": {"agent_ref": "pl"}},
            {"id": "rv", "type": review_type, "label": "문서 검토", "config": {"review": REVIEW}},
            {"id": "be", "type": "agent", "label": "BE", "config": {"agent_ref": "be"}},
        ],
        "edges": [
            _edge("m", ("you", "says"), ("pl", "in"), "message"),
            _edge("h1", ("pl", "out"), ("rv", "review"), "handoff"),
            _edge("h2", ("rv", "approved"), ("be", "in"), "handoff"),
            _edge("r", ("be", "out"), ("you", "hears"), "reply"),
        ],
    }
    response = client.post(f"{API}/graphs", json=graph)
    assert response.status_code == 201, response.text


@pytest.fixture
def plugin_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ServerSettings:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "ac_server_test_2r21_nodes.py").write_text(
        textwrap.dedent(_PLUGIN), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(plugin_dir))
    return make_settings(tmp_path, plugins={"modules": ["ac_server_test_2r21_nodes:register"]})


def _interrupted_run(settings: ServerSettings, review_type: str) -> str:
    with server(settings) as client:
        types = {t["id"]: t for t in client.get(f"{API}/node-types").json()}
        assert types["t-redo"]["rerunnable"] is True
        assert types["t-once"]["rerunnable"] is False
        _team(client, review_type)
        conv = client.post(f"{API}/conversations", json={"graph_id": "review"}).json()
        run = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "x"}).json()
        assert len(pending_of(client)) == 1
        return str(run["id"])


def test_plugin_node_type_rerunnable_flag_drives_resume(plugin_settings: ServerSettings) -> None:
    first = _interrupted_run(plugin_settings, "t-redo")
    with server(plugin_settings) as client:  # 재시작: 끊긴 실행
        options = client.get(f"{API}/runs/{first}/resume-options").json()
        assert [(n["node_id"], n["rerunnable"], n["status"]) for n in options["nodes"]] == [
            ("rv", True, "waiting")
        ]
        response = client.post(f"{API}/runs/{first}/resume", json={"node_ids": ["rv"]})
        assert response.status_code == 202, response.text
        new = response.json()
        [reopened] = pending_of(client)
        answered = client.post(
            f"{API}/runs/{new['id']}/interactions/{reopened['id']}/respond",
            json={"response": {"decision": "approved"}},
        )
        assert answered.status_code == 200, answered.text
        assert wait_run(client, new["id"])["run"]["status"] == "completed"


def test_plugin_node_type_not_rerunnable_is_refused(plugin_settings: ServerSettings) -> None:
    first = _interrupted_run(plugin_settings, "t-once")
    with server(plugin_settings) as client:
        options = client.get(f"{API}/runs/{first}/resume-options").json()
        assert [(n["node_id"], n["rerunnable"]) for n in options["nodes"]] == [("rv", False)]
        response = client.post(f"{API}/runs/{first}/resume", json={"node_ids": ["rv"]})
        assert response.status_code == 422
        issue = response.json()["error"]["details"]["issues"][0]
        assert (issue["node_id"], issue["code"]) == ("rv", "resume.not_rerunnable")
