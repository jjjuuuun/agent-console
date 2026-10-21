"""5R.23 통합 검증: 하드코딩(이름 바꾼 플러그인·제거)·안전(비밀 가림·넓힘 경고)·연동 끄기.

- 이름 바꾼 연결 종류(`zz.*`)만 등록한 레지스트리로 독립 위임·반복·조건·실패 처리를 끝까지 돌린다.
  엔진·`ac-teams`·`ac-trace`가 `delegate`·`loop`·`when`·`on_error`라는 이름을 몰라야 통과한다.
- 그 종류를 레지스트리에서 지우면 남은 데이터는 `unknown_edge_type` 검증 이슈다.
- 위임 과제·결과에 섞인 비밀 값이 Run 스냅샷·trace·목록·로그에 원문으로 나오지 않는다.
- 아래 층이 `limits`를 넓히면 유효 설정 경고 `settings.widened`.
- 연동 모듈(link-*)을 하나씩 끄거나 연동만 남겨도 서버가 뜨고 나머지가 돈다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_link_runs_teams import module as runs_teams
from agent_console_link_runs_trace import module as runs_trace
from agent_console_mod_definitions import module as definitions
from agent_console_mod_runs import module as runs
from agent_console_modkit import Assembly, BaseServices, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core.conditional import OnErrorEdge, WhenEdge
from agent_console_nodes_core.edges import DelegateEdge
from agent_console_nodes_core.loops import LoopEdge
from agent_console_runtime import Registries, load_registries
from agent_console_server import installed_modules
from agent_console_server.testing import (
    API,
    SECRET_NAME,
    SECRET_VALUE,
    TEST_TOKEN,
    agent_doc,
    make_settings,
    seed,
    server,
    team_graph,
    wait_run,
)

TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})

# 원래 이름 -> 바꾼 이름. 코드 어디에도 오른쪽 이름이 없다.
RENAMED = {
    "delegate": "zz.handover",
    "loop": "zz.again",
    "when": "zz.if",
    "on_error": "zz.rescue",
}
ORIGINAL_CLASSES: dict[str, Any] = {
    "delegate": DelegateEdge,
    "loop": LoopEdge,
    "when": WhenEdge,
    "on_error": OnErrorEdge,
}


def _renamed_class(original: str) -> Any:
    base = ORIGINAL_CLASSES[original]
    descriptor = base.descriptor.model_copy(update={"id": RENAMED[original]})
    return type(f"Renamed_{original}", (base,), {"descriptor": descriptor})


def _registries(*, renamed: bool) -> Registries:
    """기본 플러그인을 읽되 `renamed`면 네 연결 종류를 지우고 이름 바꾼 것만 등록한다."""
    registries = Registries()
    load_registries(registries)
    if renamed:
        for original in RENAMED:
            registries.edge_types.unregister(original)
            cls = _renamed_class(original)
            registries.edge_types.register(RENAMED[original], cls(), source="qa-5r23")
    return registries


@contextmanager
def _client(tmp_path: Path, registries: Registries) -> Iterator[TestClient]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    assembly: Assembly = assemble([definitions, runs, runs_teams, runs_trace], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str, **cfg: Any) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": cfg,
    }


def _node(node_id: str, type: str = "agent", **config: Any) -> dict[str, Any]:
    return {"id": node_id, "type": type, "label": node_id, "config": config}


def _agent(agent_id: str, response: str, **rule: Any) -> dict[str, Any]:
    return agent_doc(
        agent_id, response, backend_options={"default": {"response": response, **rule}}
    )


def _call(target: str, task: str) -> dict[str, Any]:
    return {"tool": "delegate", "input": {"target": target, "task": task}, "append": False}


def _delegation_graph(kinds: dict[str, str], gid: str = "flow-qa") -> dict[str, Any]:
    d, lp = kinds["delegate"], kinds["loop"]
    return {
        "id": gid,
        "name": "위임",
        "nodes": [
            _node("you", "user"),
            _node("lead", agent_ref="lead"),
            _node("m1", agent_ref="member"),
            _node("m2", agent_ref="member2"),
            _node("sub", agent_ref="subx"),
            _node("rev", agent_ref="rev"),
        ],
        "edges": [
            _edge("m-lead", "you", "says", "lead", "in", "message"),
            _edge("l-m1", "lead", "delegates", "m1", "delegated", d),
            _edge("l-m2", "lead", "delegates", "m2", "delegated", d),
            _edge("m1-sub", "m1", "delegates", "sub", "delegated", d),
            _edge("h", "lead", "out", "rev", "in", "handoff"),
            _edge("back", "rev", "out", "lead", "in", lp, max_iterations=1),
            _edge("a-rev", "rev", "out", "you", "hears", "reply"),
        ],
    }


def _condition_graph(kinds: dict[str, str]) -> dict[str, Any]:
    w, oe = kinds["when"], kinds["on_error"]

    def cond(value: str) -> dict[str, Any]:
        return {"conditions": {"all": [{"path": "/output", "op": "contains", "value": value}]}}

    return {
        "id": "cond-qa",
        "name": "조건",
        "nodes": [
            _node("you", "user"),
            _node("checker", agent_ref="checker"),
            _node("okn", agent_ref="okn"),
            _node("badn", agent_ref="badn"),
            _node("flaky", agent_ref="flaky"),
            _node("recover", agent_ref="okn"),
        ],
        "edges": [
            _edge("m-c", "you", "says", "checker", "in", "message"),
            _edge("m-f", "you", "says", "flaky", "in", "message"),
            _edge("c-ok", "checker", "out", "okn", "in", w, **cond("PASS")),
            _edge("c-bad", "checker", "out", "badn", "in", w, **cond("FAIL")),
            _edge("f-r", "flaky", "out", "recover", "in", oe),
            _edge("r-you", "recover", "out", "you", "hears", "reply"),
        ],
    }


def _post_agents(client: TestClient) -> None:
    for body in (
        _agent("lead", "리더<$host_1>", host_tool_calls=[_call("m1", "일1"), _call("m2", "일2")]),
        _agent("member", "팀원<$host_1>", host_tool_calls=[_call("sub", "세부: $prompt")]),
        _agent("member2", "팀원2($prompt)"),
        _agent("subx", "하위($prompt)"),
        _agent("rev", "검토 끝"),
        _agent("checker", "$prompt"),
        _agent("okn", "ok"),
        _agent("badn", "bad"),
        _agent("flaky", "x", fail={"code": "qa.flaky", "message": "일부러 실패"}),
    ):
        assert client.post(f"{API}/agents", json=body).status_code == 201, body["id"]


def test_renamed_edge_kinds_run_delegation_and_loop(tmp_path: Path) -> None:
    """엔진·팀 의미·추적이 연결 종류 이름을 모른다 — 이름만 바꾼 플러그인으로 위임·반복이 돈다."""
    with _client(tmp_path, _registries(renamed=True)) as client:
        kinds = RENAMED
        _post_agents(client)
        graph = _delegation_graph(kinds)
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        assert client.post(f"{API}/graphs/{graph['id']}/validate").json() == []
        started = client.post(
            f"{API}/runs", json={"graph_id": graph["id"], "input": {"text": "hi"}}
        )
        assert started.status_code == 202, started.text
        snap = _wait(client, started.json()["id"])
        assert snap["run"]["status"] == "completed", snap["run"]
        trace = client.get(f"{API}/runs/{started.json()['id']}/trace").json()
        span_ids = {s["id"] for s in trace["spans"]}
        assert {"call:lead/m1#0", "call:lead/m2#0", "call:lead/m1/sub#0"} <= span_ids
        link_kinds = {link["kind"] for link in trace["links"]}
        assert kinds["loop"] in link_kinds
        assert kinds["delegate"] in link_kinds
        # 옛 이름은 어디에도 나오지 않는다
        assert "delegate" not in link_kinds
        assert "loop" not in link_kinds


def test_renamed_when_and_on_error(tmp_path: Path) -> None:
    """조건 연결은 한쪽만, 실패 처리 연결이 지나가면 Run은 completed."""
    with _client(tmp_path, _registries(renamed=True)) as client:
        _post_agents(client)
        graph = _condition_graph(RENAMED)
        saved = client.post(f"{API}/graphs", json=graph)
        assert saved.status_code == 201, saved.text
        started = client.post(
            f"{API}/runs", json={"graph_id": "cond-qa", "input": {"text": "PASS go"}}
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        snap = _wait(client, run_id)
        status = {n["node_id"]: n["status"] for n in snap["node_runs"]}
        assert status.get("okn") == "succeeded", status
        assert status.get("badn") == "skipped", status
        assert status.get("flaky") == "failed", status
        assert status.get("recover") == "succeeded", status
        assert snap["run"]["status"] == "completed", snap["run"]


def test_removed_plugin_leaves_data_as_validation_issue(tmp_path: Path) -> None:
    """플러그인을 지운 뒤 남은 데이터는 `unknown_edge_type` 이슈이고 서버는 계속 돈다."""
    registries = _registries(renamed=True)
    with _client(tmp_path, registries) as client:
        _post_agents(client)
        graph = _delegation_graph(RENAMED)
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        assert client.post(f"{API}/graphs/{graph['id']}/validate").json() == []
        for kind in RENAMED.values():
            registries.edge_types.unregister(kind)
        issues = client.post(f"{API}/graphs/{graph['id']}/validate").json()
        codes = {i["code"] for i in issues}
        assert "unknown_edge_type" in codes, issues
        assert {i["path"] for i in issues if i["code"] == "unknown_edge_type"} >= {
            "/edges/1",
            "/edges/5",
        } or len([i for i in issues if i["code"] == "unknown_edge_type"]) >= 4
        # 저장된 정의 열람·다른 API는 그대로 돈다
        assert client.get(f"{API}/graphs/{graph['id']}").status_code == 200
        assert client.get(f"{API}/agents").status_code == 200
        # 플러그인을 다시 설치하면 이슈가 사라진다
        for original, kind in RENAMED.items():
            registries.edge_types.register(kind, _renamed_class(original)(), source="qa-5r23")
        assert client.post(f"{API}/graphs/{graph['id']}/validate").json() == []


def test_delegation_secrets_not_exposed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """위임 과제·결과에 비밀 값이 섞여도 스냅샷·trace·목록·로그에 원문이 없다."""
    caplog.set_level(logging.DEBUG)
    with server(make_settings(tmp_path)) as client:
        # 비밀은 해석된 뒤부터 가려진다 — 먼저 한 번 해석시킨다
        warm = client.post(f"{API}/agents", json=_agent("warm", f"secret://{SECRET_NAME}"))
        assert warm.status_code == 201
        warm_graph = {
            "id": "warm-flow",
            "name": "w",
            "nodes": [_node("you", "user"), _node("w", agent_ref="warm")],
            "edges": [
                _edge("m", "you", "says", "w", "in", "message"),
                _edge("r", "w", "out", "you", "hears", "reply"),
            ],
        }
        assert client.post(f"{API}/graphs", json=warm_graph).status_code == 201
        warm_run = client.post(
            f"{API}/runs", json={"graph_id": "warm-flow", "input": {"text": "x"}}
        )
        assert wait_run(client, warm_run.json()["id"])["run"]["status"] == "completed"
        assert (
            client.post(
                f"{API}/agents",
                json=_agent(
                    "lead",
                    "리더<$host_1>",
                    host_tool_calls=[_call("m1", f"열쇠 secret://{SECRET_NAME} / {SECRET_VALUE}")],
                ),
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"{API}/agents", json=_agent("member", f"받음($prompt) secret://{SECRET_NAME}")
            ).status_code
            == 201
        )
        graph = {
            "id": "sec-flow",
            "name": "비밀",
            "nodes": [
                _node("you", "user"),
                _node("lead", agent_ref="lead"),
                _node("m1", agent_ref="member"),
            ],
            "edges": [
                _edge("m", "you", "says", "lead", "in", "message"),
                _edge("d", "lead", "delegates", "m1", "delegated", "delegate"),
                _edge("r", "lead", "out", "you", "hears", "reply"),
            ],
        }
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        started = client.post(
            f"{API}/runs", json={"graph_id": "sec-flow", "input": {"text": "? 열쇠"}}
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["id"]
        snap = wait_run(client, run_id)
        assert snap["run"]["status"] == "completed", snap["run"]
        trace = client.get(f"{API}/runs/{run_id}/trace")
        assert trace.status_code == 200
        text = json.dumps(snap, ensure_ascii=False) + trace.text
        for path in ("/runs", "/runs/handoffs", f"/runs/{run_id}/events?limit=1000"):
            text += client.get(f"{API}{path}").text
        assert SECRET_VALUE not in text
        assert "[REDACTED]" in text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET_VALUE not in logged
    assert TEST_TOKEN not in logged


def test_widened_limits_warn_on_effective_settings(tmp_path: Path) -> None:
    """공통 설정의 `limits.directories`보다 팀 구성이 넓히면 `settings.widened` 경고."""
    with server(make_settings(tmp_path)) as client:
        put = client.put(
            f"{API}/settings",
            json={"agent_defaults": {"backend": "fake", "limits": {"directories": ["/w"]}}},
        )
        assert put.status_code == 200, put.text
        seed(client, "wide0")
        for gid, dirs in (("wide", ["/w", "/x"]), ("same", ["/w"])):
            graph = team_graph(gid)
            graph["settings"] = {"limits": {"directories": dirs}}
            assert client.post(f"{API}/graphs", json=graph).status_code == 201
        wide = client.get(f"{API}/graphs/wide/nodes/a/effective-settings")
        assert wide.status_code == 200, wide.text
        assert any(w["code"] == "settings.widened" for w in wide.json()["warnings"]), wide.text
        same = client.get(f"{API}/graphs/same/nodes/a/effective-settings").json()["warnings"]
        assert not any(w["code"] == "settings.widened" for w in same), same


LINKS = sorted(m.descriptor.id for m in installed_modules() if m.descriptor.id.startswith("link-"))


def test_link_modules_exist_for_every_pair() -> None:
    assert {
        "link-runs-teams",
        "link-runs-trace",
        "link-chat-runs",
        "link-runs-usage",
    } <= set(LINKS)


@pytest.mark.parametrize(
    "link_id", ["link-runs-teams", "link-runs-trace", "link-chat-runs", "link-runs-usage"]
)
def test_each_link_off_server_runs_a_flow(tmp_path: Path, link_id: str) -> None:
    """연동 하나를 꺼도 실행·조회가 돈다. 그 연동의 경로만 사라지거나 feature_unavailable."""
    settings = make_settings(tmp_path, modules={"disabled": [link_id]})
    with server(settings) as client:
        mods = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert mods[link_id]["status"] == "disabled"
        seed(client, "f1")
        started = client.post(f"{API}/runs", json={"graph_id": "f1", "input": {"request": "? x"}})
        assert started.status_code == 202, started.text
        snap = wait_run(client, started.json()["id"])
        if link_id == "link-runs-teams":
            # 에이전트 정의 조회 연동이 없으면 에이전트 노드는 안내와 함께 실패(서버는 계속)
            assert snap["run"]["status"] == "failed", snap["run"]
            assert "link-runs-teams" in snap["run"]["error"]["message"]
        else:
            assert snap["run"]["status"] == "completed", snap["run"]
        assert client.get(f"{API}/health").status_code == 200
        trace = client.get(f"{API}/runs/{started.json()['id']}/trace")
        assert trace.status_code in (200, 404, 409), trace.text  # 5xx가 아니다


def test_only_links_with_everything_else_off(tmp_path: Path) -> None:
    """연동 4개를 모두 끄고 켜도, 기능 모듈 없이 연동만 켜면 unsatisfied로 보이고 서버는 뜬다."""
    features = [
        m.descriptor.id for m in installed_modules() if not m.descriptor.id.startswith("link-")
    ]
    settings = make_settings(tmp_path, modules={"disabled": features})
    with server(settings) as client:
        assert client.get(f"{API}/health").status_code == 200
        mods = client.get(f"{API}/modules").json()
        statuses = {m["id"]: m["status"] for m in mods}
        assert all(statuses[f] == "disabled" for f in features)
        assert all(s in {"unsatisfied", "disabled"} for i, s in statuses.items() if i in LINKS)
