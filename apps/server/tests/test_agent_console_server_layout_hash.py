"""화면 배치(layout)만 바꾼 저장(3R.7, E-3, graph-edges §5.3 S2).

layout은 position처럼 버전 해시에서 빠진다. layout만 바꾼 저장은 해시·ETag가 그대로이고 버전 행이
늘지 않으며, 같은 버전 행의 내용(최신 배치)만 갱신된다.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, seed, server


def _versions(client: TestClient) -> list[dict[str, Any]]:
    response = client.get(f"{API}/graphs/flow/versions")
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()
    return body


def _put(client: TestClient, graph: dict[str, Any], version: str) -> Any:
    response = client.put(f"{API}/graphs/flow", json=graph, headers={"If-Match": version})
    assert response.status_code == 200, response.text
    return response


def test_layout_only_save_keeps_hash_etag_and_version_rows(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        created = seed(client)
        old_hash = created["version_hash"]
        before = _versions(client)

        graph = copy.deepcopy(created["graph"])
        graph["nodes"][0]["layout"] = {"direction": "tb", "ports": {"out:out": "bottom"}}
        graph["edges"][0]["layout"] = {
            "shape": "smoothstep",
            "waypoints": [{"x": 560, "y": 280}, {"x": 560, "y": 72}],
            "label_t": 0.3,
        }
        graph["ui"] = {"layout": {"direction": "tb", "edge_shape": "auto"}}
        put = _put(client, graph, old_hash)
        assert put.json()["version_hash"] == old_hash
        assert put.headers["etag"].strip('"') == old_hash
        assert [v["version_hash"] for v in _versions(client)] == [v["version_hash"] for v in before]

        # 저장된 문서와 그 버전 행은 최신 배치를 담는다
        # (실행 상세가 같은 의미 버전의 최신 배치를 그림)
        current = client.get(f"{API}/graphs/flow")
        assert current.headers["etag"].strip('"') == old_hash
        assert current.json()["graph"]["edges"][0]["layout"]["waypoints"][1] == {"x": 560, "y": 72}
        row = client.get(f"{API}/graphs/flow/versions/{old_hash}").json()
        assert row["content"]["nodes"][0]["layout"] == {
            "direction": "tb",
            "ports": {"out:out": "bottom"},
        }

        # position과 layout을 같이 바꿔도 같다
        graph["nodes"][1]["position"] = {"x": -40, "y": 900}
        graph["nodes"][1]["layout"] = {"direction": "bt"}
        assert _put(client, graph, old_hash).json()["version_hash"] == old_hash
        assert len(_versions(client)) == len(before)

        # 의미 있는 변경은 새 버전을 만든다
        graph["nodes"][0]["label"] = "바뀐 이름"
        assert _put(client, graph, old_hash).json()["version_hash"] != old_hash
        assert len(_versions(client)) == len(before) + 1
