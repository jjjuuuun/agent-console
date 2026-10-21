"""4R.9: hook probe 전달 연결(서버 조립 수준, 실 SDK 호출 없음).

- 설치자 옵션 `modules.options.mod-runs.backends.claude-agent-sdk.hook_probe_command`가
  백엔드에 닿는다.
- 노드 실행 폴더(`<Run 파일 폴더>/<run>/<노드>`)가 요청으로 넘어가 fake 흉내 기록이
  `hook-probe/`에 남는다.
- 묶음 미리보기에 "hook 감싸기 켜짐" 안내(info)가 붙는다(꺼짐이면 없음).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, agent_doc, make_settings, server, team_graph, wait_run

PROBE_RULE: dict[str, Any] = {"hook_probe": [{"event": "Stop", "after": "end"}]}
NOTE = "observe.hook_probe_wrapped"


def test_hook_probe_command_install_option_reaches_backend(tmp_path: Path) -> None:
    from agent_console_mod_runs import RUNS_STARTER

    probe = ["/opt/probe", "--x"]
    settings = make_settings(
        tmp_path,
        options={"mod-runs": {"backends": {"claude-agent-sdk": {"hook_probe_command": probe}}}},
    )
    with server(settings) as client:
        starter = client.app.state.assembly.port(RUNS_STARTER)  # type: ignore[attr-defined]
        backend = starter.registries.backends.get("claude-agent-sdk")
        assert backend._probe_command == probe


def _seed(client: Any, *, hook_probe: bool) -> None:
    fast = agent_doc("fast", "빠른 답")
    fast["backend_options"]["default"].update(PROBE_RULE)
    if hook_probe:
        fast["observe"] = {"hook_probe": True}
    assert client.post(f"{API}/agents", json=fast).status_code == 201
    assert client.post(f"{API}/agents", json=agent_doc("slow", "깊은 답")).status_code == 201
    assert client.post(f"{API}/graphs", json=team_graph()).status_code == 201


def test_fake_probe_records_land_in_node_run_folder(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client, hook_probe=True)
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "q"}})
        snap = wait_run(client, run.json()["id"])
        assert snap["run"]["status"] == "completed", snap["run"]
        run_id = snap["run"]["id"]
    (folder,) = [p for p in tmp_path.rglob("hook-probe") if p.is_dir()]
    assert folder.parent.name == "a"
    assert folder.parent.parent.name == run_id
    (record_file,) = folder.iterdir()
    record = json.loads(record_file.read_text(encoding="utf-8").splitlines()[0])
    assert record["format"] == "hook-probe/1"
    assert record["context"] == {"run_id": run_id, "node_path": "a"}


def test_fake_probe_off_by_default_writes_nothing(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client, hook_probe=False)
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "q"}})
        wait_run(client, run.json()["id"])
    assert not [p for p in tmp_path.rglob("hook-probe")]


def test_bundle_preview_announces_hook_probe(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client, hook_probe=False)
        off = client.get(f"{API}/graphs/flow/nodes/a/bundle-preview").json()
        assert all(w["code"] != NOTE for w in off["warnings"])
        fast = client.get(f"{API}/agents/fast").json()
        fast["observe"] = {"hook_probe": True}
        assert client.put(f"{API}/agents/fast", json=fast).status_code == 200
        on = client.get(f"{API}/graphs/flow/nodes/a/bundle-preview").json()
        (note,) = [w for w in on["warnings"] if w["code"] == NOTE]
        assert note["severity"] == "info"
        assert "hook 감싸기 켜짐" in note["message"]
