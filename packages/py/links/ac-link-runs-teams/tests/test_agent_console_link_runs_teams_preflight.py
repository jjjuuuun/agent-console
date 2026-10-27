"""사전 점검 ``backend.unresolved``(5.2R.4): 실행 백엔드가 빈 노드가 있으면 Run을 만들지 않고 422.

- HTTP(mod-definitions·mod-runs와 함께): 본문(노드 label·백엔드 디스크립터·해결 버튼 2개), Run 0건,
  기본값을 정하면 실행된다.
- ``TeamRules.preflight`` 단독: 이름을 바꾼 백엔드로도 같고(코드에 백엔드 이름 없음), 문구·역할은
  ``BackendFixTexts`` 데이터로 바뀐다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    BackendUnresolvedDetails,
    ErrorCodes,
    Graph,
    WorkspaceSettings,
)
from agent_console_link_runs_teams import BackendFixTexts, TeamRules, module
from agent_console_mod_definitions import module as definitions
from agent_console_mod_runs import module as runs
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import Registries, Services, load_registries
from agent_console_store import NotFound
from agent_console_teams import TeamCatalog, catalog_from_registries
from agent_console_teams.testing import KITS

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


def _agent(agent_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": "응답 담당",
        "backend_options": {"default": {"response": "답: $prompt"}},
        **extra,
    }


def _graph(graph_id: str, agent_ref: str, *, label: str | None = "응답자") -> dict[str, Any]:
    node: dict[str, Any] = {"id": "n1", "type": "agent", "config": {"agent_ref": agent_ref}}
    if label is not None:
        node["label"] = label
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [{"id": "you", "type": "user", "label": "나"}, node],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "n1", "port": "in"},
                "kind": "message",
            },
            {
                "id": "r1",
                "source": {"node": "n1", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
            },
        ],
    }


@contextmanager
def _client(tmp_path: Path, *, show_hidden: bool = True) -> Iterator[TestClient]:
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    config = ModulesConfig(options={"mod-runs": {"show_hidden_backends": show_hidden}})
    assembly = assemble([definitions, runs, module], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_post_runs_without_backend_is_422_and_records_nothing(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.post(f"{API}/agents", json=_agent("helper")).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("solo", "helper")).status_code == 201
        # 저장 검증은 막지 않는다(실행 때만 묻는다)
        assert client.post(f"{API}/graphs/solo/validate").json() == []

        res = client.post(f"{API}/runs", json={"graph_id": "solo", "input": {"text": "hi"}})
        assert res.status_code == 422, res.text
        error = res.json()["error"]
        assert error["code"] == ErrorCodes.BACKEND_UNRESOLVED
        # 문구는 노드 이름으로, id는 상세에만
        assert "응답자" in error["message"]
        assert "n1" not in error["message"]
        details = BackendUnresolvedDetails.model_validate(error["details"])
        assert [(n.id, n.label) for n in details.nodes] == [("n1", "응답자")]
        assert "fake-agent" in {o.id for o in details.options}
        fake = next(o for o in details.options if o.id == "fake-agent")
        assert fake.ui_hints is not None
        assert fake.ui_hints.badge  # 번들 데이터(테스트용 배지)
        assert fake.ui_hints.hidden is False  # show_hidden_backends로 숨김을 풀었다
        assert fake.cost_note
        actions = error["fix"]["actions"]
        assert [a["target"] for a in actions] == [
            {"role": "definition:graph", "id": "solo", "section": "n1"},
            {"role": "settings", "section": "common"},
        ]
        assert [a["focus"] for a in actions] == ["/backend", "/backend"]

        # 기록 0건: Run을 만들지 않았다
        assert client.get(f"{API}/runs").json() == []

        # 기본값(옛 default_backend도 공통 층으로 읽힌다)을 정하면 실행된다
        got = client.get(f"{API}/settings")
        body = {**got.json(), "default_backend": "fake-agent"}
        etag = got.headers.get("etag")  # 설정 파일이 아직 없으면 ETag 없음
        put = client.put(f"{API}/settings", json=body, headers={"If-Match": etag} if etag else {})
        assert put.status_code == 200, put.text
        run = client.post(f"{API}/runs", json={"graph_id": "solo", "input": {"text": "hi"}})
        assert run.status_code == 202, run.text
        assert _wait(client, run.json()["id"])["run"]["status"] == "completed"


def test_hidden_backend_is_not_offered_by_default(tmp_path: Path) -> None:
    """개발·테스트용 백엔드(``ui_hints.hidden``)는 설치자가 켜지 않으면 선택지에 없다(5.2R.105)."""
    with _client(tmp_path, show_hidden=False) as client:
        client.post(f"{API}/agents", json=_agent("helper"))
        client.post(f"{API}/graphs", json=_graph("solo", "helper"))
        error = client.post(f"{API}/runs", json={"graph_id": "solo"}).json()["error"]
        details = BackendUnresolvedDetails.model_validate(error["details"])
        assert "fake-agent" not in {o.id for o in details.options}


def test_label_falls_back_to_agent_name(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post(f"{API}/agents", json=_agent("helper"))
        client.post(f"{API}/graphs", json=_graph("bare", "helper", label=None))
        error = client.post(f"{API}/runs", json={"graph_id": "bare"}).json()["error"]
        assert error["details"]["nodes"] == [{"id": "n1", "label": "응답 담당"}]
        assert "응답 담당" in error["message"]


class _Lookup:
    """정의 읽기(에이전트 하나)."""

    def __init__(self, agents: Mapping[str, Mapping[str, Any]]) -> None:
        self._agents = agents

    def get(self, kind: str, id: str) -> Any:
        if id not in self._agents:
            raise NotFound(kind, id)
        return type("Stored", (), {"document": dict(self._agents[id])})()

    def get_version(self, kind: str, id: str, version_hash: str) -> Any:  # pragma: no cover
        raise NotImplementedError


def test_preflight_with_renamed_backend_and_custom_texts() -> None:
    registries = Registries()
    load_registries(registries)
    registries.backends.register("zz-engine", FakeBackend(backend_id="zz-engine"), replace=True)
    shown = FakeBackend(backend_id="zz-shown")
    assert shown.descriptor.ui_hints is not None
    shown.descriptor = shown.descriptor.model_copy(
        update={"ui_hints": shown.descriptor.ui_hints.model_copy(update={"hidden": False})}
    )
    registries.backends.register("zz-shown", shown, replace=True)
    workspace: dict[str, WorkspaceSettings | None] = {"value": None}
    texts = BackendFixTexts(message_one="[{label}] 백엔드 없음", default_role="prefs")
    rules = TeamRules(
        _Lookup({"helper": _agent("helper")}),
        catalog=lambda: catalog_from_registries(registries),
        registries=lambda: registries,
        workspace=lambda: workspace["value"],
        fix_texts=texts,
    )
    graph = Graph.model_validate(_graph("solo", "helper"))
    error = rules.preflight(graph, Services({}))
    assert error is not None
    assert error.message == "[응답자] 백엔드 없음"
    assert error.fix is not None
    assert error.fix.actions[1].target.role == "prefs"
    offered = {o["id"] for o in error.details["options"]}
    assert "zz-shown" in offered
    assert "zz-engine" not in offered  # 숨김 표시(개발·테스트용)는 선택지에서 뺀다

    workspace["value"] = WorkspaceSettings.model_validate(
        {"agent_defaults": {"backend": "zz-engine"}}
    )
    assert rules.preflight(graph, Services({})) is None


def test_child_run_keeps_node_failure_with_user_wording(tmp_path: Path) -> None:
    """사전 점검은 루트 실행만 막는다. 자식 Run(중첩 팀)은 노드 실패로 남고 문구는 이름으로
    부른다."""
    with _client(tmp_path) as client:
        client.post(f"{API}/agents", json=_agent("helper"))
        client.post(f"{API}/graphs", json=_graph("child", "helper"))
        parent = _graph("parent", "unused")
        parent["nodes"][1] = {
            "id": "T",
            "type": "team",
            "label": "중첩",
            "config": {"team_ref": "child"},
        }
        for edge in parent["edges"]:
            for side in ("source", "target"):
                if edge[side]["node"] == "n1":
                    edge[side]["node"] = "T"
        assert client.post(f"{API}/graphs", json=parent).status_code == 201

        run = client.post(f"{API}/runs", json={"graph_id": "parent", "input": {"text": "hi"}})
        assert run.status_code == 202, run.text
        root_id = run.json()["id"]
        assert _wait(client, root_id)["run"]["status"] == "failed"
        children = [r for r in client.get(f"{API}/runs", params={"root": root_id}).json()]
        child = next(r for r in children if r["id"] != root_id)
        snap = _wait(client, child["id"])
        [node] = [nr for nr in snap["node_runs"] if nr["node_id"] == "n1"]
        assert node["error"]["code"] == "agent.no_backend"
        assert "'응답자'" in node["error"]["message"]
        assert "n1" not in node["error"]["message"]
        assert node["error"]["details"]["node_id"] == "n1"
        # 3단 규칙의 둘째 단: 해결 버튼(노드 서비스 ERROR_FIXES, 5.2R.5)
        actions = node["error"]["fix"]["actions"]
        assert [_set(a["target"]) for a in actions] == [
            {"role": "definition:graph", "id": "child", "section": "n1"},
            {"role": "settings", "section": "common"},
        ]
        # 자식 Run 실패 요약도 노드 이름 + 같은 버튼(id는 details에만)
        error = snap["run"]["error"]
        assert "n1" not in error["message"]
        assert "응답자" in error["message"]
        assert error["details"]["node_id"] == "n1"
        assert error["fix"] == node["error"]["fix"]

        # 자식 Run은 따로 이어 가지 않는다: 409 + 상위·루트 Run id + [맨 위 실행 열기](D12)
        res = client.post(f"{API}/runs/{child['id']}/resume", json={"node_ids": ["n1"]})
        assert res.status_code == 409, res.text
        body = res.json()["error"]
        assert body["details"]["root_run_id"] == root_id
        assert body["details"]["parent_run_id"] == root_id
        assert _set(body["fix"]["actions"][0]["target"]) == {"role": "runs", "id": root_id}


def _set(value: dict[str, Any]) -> dict[str, Any]:
    """null 칸을 뺀 값(이슈 목록 응답은 null을 그대로 싣는다)."""
    return {k: v for k, v in value.items() if v is not None}


def test_validation_issues_carry_fix_actions_and_user_wording(tmp_path: Path) -> None:
    """대표 이슈(입구 없음·답변 없음·알 수 없는 종류)에 해결 버튼, 문구에 노드 id 없음(5.2R.5)."""
    with _client(tmp_path) as client:
        client.post(f"{API}/agents", json=_agent("helper"))
        graph = _graph("broken", "helper")
        graph["edges"] = []  # 입구·답변 없음
        graph["nodes"].append({"id": "n7", "type": "no-such-kind", "label": "옛 노드"})
        issues = client.post(f"{API}/graphs/broken/validate", json=graph).json()
        by_code = {i["code"]: i for i in issues}
        assert _set(by_code["unknown_node_type"]["fix"]["actions"][0]["target"]) == {
            "role": "definition:graph",
            "id": "broken",
            "section": "n7",
        }
        assert by_code["unknown_node_type"]["fix"]["actions"][1]["target"]["role"] == "settings"
        for issue in issues:
            assert "'n7'" not in issue["message"], issue
            assert "'n1'" not in issue["message"], issue

        graph["nodes"].pop()  # 모르는 종류를 빼면 팀 규칙이 돈다
        issues = client.post(f"{API}/graphs/broken/validate", json=graph).json()
        by_code = {i["code"]: i for i in issues}
        for code in ("team.no_entry", "team.no_reply"):
            target = _set(by_code[code]["fix"]["actions"][0]["target"])
            assert target == {"role": "definition:graph", "id": "broken"}, code

        # 실행 차단 응답: 문구 = 머리 + 첫 오류, fix = 첫 버튼(채팅·실행 화면이 그대로 그린다)
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        res = client.post(f"{API}/runs", json={"graph_id": "broken", "input": {"text": "hi"}})
        assert res.status_code == 422, res.text
        error = res.json()["error"]
        assert "입구" in error["message"]
        assert error["fix"]["actions"][0]["target"]["id"] == "broken"


def test_issue_fixes_table_is_data() -> None:
    """표를 바꾸면 버튼이 바뀐다(코드에 코드·역할 목록이 없다)."""
    from agent_console_link_runs_teams import DEFAULT_ISSUE_FIXES, IssueFixes, load_issue_fixes

    assert {"team.no_entry", "team.no_reply", "agent.no_backend", "unknown_node_type"} <= set(
        DEFAULT_ISSUE_FIXES.codes
    )
    custom = load_issue_fixes(
        '{"rules": [{"codes": ["team.no_entry"], "actions": [{"label": "열기 {graph_id}",'
        ' "target": {"role": "editor", "section": "{node_id}"}}]}]}'
    )
    fix = custom.fix_for("team.no_entry", team_kind="graph", graph_id="g")
    assert fix is not None
    assert fix.actions[0].label == "열기 g"
    assert fix.actions[0].target.section is None  # 빈 자리 = null
    assert custom.fix_for("team.no_reply", team_kind="graph", graph_id="g") is None
    assert IssueFixes().attach([], team_kind="graph", graph_id="g") == []


def test_preflight_blocks_own_session_member_without_backend() -> None:
    """자기 세션을 여는 위임 방식(``shares_session`` false)의 대상은 위임자의 백엔드를 쓰지 않는다:
    사전 점검이 방식 디스크립터를 넘겨 실행 전에 막는다(실행 중 실패 대신). 노드·연결·방식·백엔드
    이름은 모두 임의 이름(``Kit`` renamed)이다."""
    kit = KITS[-1]
    catalog = TeamCatalog(
        node_types=tuple(kit.node_types),
        edge_types=tuple(kit.edge_types),
        strategies=kit.strategy_map,
    )
    agents = {"pl": {"id": "pl", "name": "기획자"}}
    rules = TeamRules(
        _Lookup(agents),
        catalog=lambda: catalog,
        registries=lambda: None,
        workspace=lambda: None,
    )
    nodes = [
        kit.person(),
        kit.worker("lead", who="pl", settings={"backend": "zz-engine"}),
        kit.worker("far", who="pl"),
    ]
    edges = [
        kit.edge("m1", "entry", "me", "lead"),
        kit.edge("a1", "exit", "lead", "me"),
        kit.edge("d1", "invoke3", "lead", "far"),
    ]
    error = rules.preflight(kit.graph(nodes, edges), Services({}))
    assert error is not None
    assert error.code == ErrorCodes.BACKEND_UNRESOLVED
    assert [n["id"] for n in error.details["nodes"]] == ["far"]

    # 같은 세션 방식으로 부르면 위임자 세션에서 돌므로 막지 않는다
    edges[2] = kit.edge("d1", "invoke", "lead", "far")
    assert rules.preflight(kit.graph(nodes, edges), Services({})) is None
