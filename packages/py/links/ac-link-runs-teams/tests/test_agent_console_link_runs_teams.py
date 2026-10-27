"""link-runs-teams: 팀 규칙 검사·실행 준비·노드 서비스·목록 검증 요약·검증 경로, 포트 계약.

정의 모듈(``mod-definitions``)·실행 모듈(``mod-runs``)은 dev 의존이다(이 패키지는 import하지
않는다). 노드·백엔드는 설치된 entry point(``ac-nodes-core``·``ac-backend-fake-agent``)에서 읽는다.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import Graph
from agent_console_link_runs_teams import (
    GRAPH_VALIDATION,
    RUN_PREPARERS,
    RUN_SERVICES,
    DefinitionLookup,
    RunChecker,
    TeamRules,
    ValidationSummaries,
    module,
)
from agent_console_link_runs_teams.testing import local_runs_module
from agent_console_mod_definitions import GraphValidationSource
from agent_console_mod_definitions import module as definitions
from agent_console_mod_runs import RUNS_STARTER, RunPreparer, RunServiceProvider
from agent_console_mod_runs import module as runs
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core import AGENT_LOOKUP, TEAM_LOOKUP, WORKING_DIRECTORY
from agent_console_runtime import Registries, load_registries

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    return registries


def _agent(agent_id: str) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {"default": {"response": "답: $prompt"}},
    }


def _graph(graph_id: str, agent_ref: str) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _base(tmp_path: Path) -> BaseServices:
    return BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )


@contextmanager
def _client(
    tmp_path: Path, *modules: Any, config: ModulesConfig | None = None
) -> Iterator[tuple[TestClient, Assembly]]:
    assembly = assemble(list(modules), config, base=_base(tmp_path))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_port_contracts_with_runs_and_definitions(tmp_path: Path) -> None:
    """제공 구현 ↔ 소비 프로토콜(mod-runs 준비자·서비스 공급자, mod-definitions 검증 요약)."""
    with _client(tmp_path, definitions, runs, module) as (_http, assembly):
        [preparer] = assembly.ports(RUN_PREPARERS)
        [provider] = assembly.ports(RUN_SERVICES)
        assert isinstance(preparer, TeamRules)
        assert isinstance(preparer, RunPreparer)
        assert isinstance(provider, RunServiceProvider)
        as_preparer: RunPreparer = preparer
        as_provider: RunServiceProvider = provider
        summaries = assembly.port(GRAPH_VALIDATION)
        assert isinstance(summaries, ValidationSummaries)
        assert isinstance(summaries, GraphValidationSource)
        as_source: GraphValidationSource = summaries
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunChecker)
        assert isinstance(preparer.lookup, DefinitionLookup)
        assert preparer is provider
        assert callable(as_preparer.prepare)
        assert callable(as_provider.services)
        assert as_source.summaries([]) == {}


def test_rules_check_prepare_and_services(tmp_path: Path) -> None:
    with _client(tmp_path, definitions, runs, module) as (client, assembly):
        assert client.post(f"{API}/agents", json=_agent("fast")).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("flow", "fast")).status_code == 201
        assert client.post(f"{API}/graphs", json=_graph("ghost", "nobody")).status_code == 201

        # 검증 경로: 저장본·본문 그래프
        assert client.post(f"{API}/graphs/flow/validate").json() == []
        codes = {i["code"] for i in client.post(f"{API}/graphs/ghost/validate").json()}
        assert codes & {"agent.not_found", "team.agent_not_found"}
        body = Graph.model_validate(_graph("draft", "nobody")).model_dump(mode="json")
        assert client.post(f"{API}/graphs/flow/validate", json=body).json()
        assert client.post(f"{API}/graphs/missing/validate").status_code == 404

        # 실행: 팀 규칙 error가 있으면 422, 없으면 노드 서비스(에이전트 조회)로 끝까지 돈다
        assert client.post(f"{API}/runs", json={"graph_id": "ghost"}).status_code == 422
        run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"text": "hi"}})
        assert run.status_code == 202, run.text
        assert _wait(client, run.json()["id"])["run"]["status"] == "completed"

        [provider] = assembly.ports(RUN_SERVICES)
        env = type("Env", (), {"working_directory": tmp_path, "run_files_root": tmp_path / "r"})()
        services = provider.services(env)
        assert services[WORKING_DIRECTORY] == str(tmp_path)
        assert services[AGENT_LOOKUP]("fast").id == "fast"
        assert services[AGENT_LOOKUP]("nobody") is None


def test_validation_summary_cache_and_invalidation(tmp_path: Path) -> None:
    """목록 검증 요약은 워크스페이스 개정이 같으면 다시 계산하지 않고, 정의가 바뀌면 다시
    계산한다."""
    with _client(tmp_path, definitions, runs, module) as (client, assembly):
        client.post(f"{API}/agents", json=_agent("fast"))
        client.post(f"{API}/graphs", json=_graph("flow", "fast"))
        summaries = assembly.port(GRAPH_VALIDATION)
        assert isinstance(summaries, ValidationSummaries)
        calls: list[str] = []
        original = summaries.compute

        def counting(graph_id: str) -> Any:
            calls.append(graph_id)
            return original(graph_id)

        summaries.compute = counting  # type: ignore[method-assign]
        listed = {g["id"]: g for g in client.get(f"{API}/graphs").json()}
        assert listed["flow"]["validation"]["blocks_run"] is False
        client.get(f"{API}/graphs")
        assert calls == ["flow"]
        etag = client.get(f"{API}/agents/fast").headers["ETag"]
        assert client.delete(f"{API}/agents/fast", headers={"If-Match": etag}).status_code == 204
        after = {g["id"]: g for g in client.get(f"{API}/graphs").json()}
        assert calls == ["flow", "flow"]
        assert after["flow"]["validation"]["blocks_run"] is True


def test_generation_revision_when_store_has_no_fingerprint() -> None:
    class _Lookup:
        def get(self, kind: str, id: str) -> Any:
            raise LookupError(id)

    class _Checker:
        def check(self, graph: Graph) -> list[Any]:
            return []

        def load_graph(self, graph_id: str, version_hash: str | None = None) -> Graph:
            return Graph(id=graph_id, name=graph_id)

    summaries = ValidationSummaries(_Checker(), _Lookup())
    first = summaries.revision()
    assert first == summaries.revision()
    summaries.invalidate()
    assert summaries.revision() != first
    assert summaries.summaries(["g"])["g"] is not None


def test_disabled_link_removes_route_and_summary(tmp_path: Path) -> None:
    config = ModulesConfig(disabled=["link-runs-teams"])
    with _client(tmp_path, definitions, runs, module, config=config) as (client, _assembly):
        client.post(f"{API}/graphs", json=_graph("flow", "fast"))
        assert client.post(f"{API}/graphs/flow/validate").status_code == 404
        assert client.get(f"{API}/graphs").json()[0]["validation"] is None


def test_requires_runs_starter(tmp_path: Path) -> None:
    assembly = assemble([definitions, module], base=_base(tmp_path))
    report = assembly.status("link-runs-teams")
    assert report is not None
    assert report.state.value == "unsatisfied"
    assert report.missing == ("runs.starter",)


def test_standalone_local_runs_module(tmp_path: Path) -> None:
    """단독 실행 동반 모듈(검증만): 검증 경로가 엔진 + 팀 규칙으로 동작한다."""
    with _client(tmp_path, local_runs_module(), module) as (client, assembly):
        assert {r.state.value for r in assembly.report} == {"active"}
        assert client.post(f"{API}/graphs/none/validate").status_code == 404
        body = Graph.model_validate(_graph("draft", "nobody")).model_dump(mode="json")
        codes = {i["code"] for i in client.post(f"{API}/graphs/x/validate", json=body).json()}
        assert codes & {"agent.not_found", "team.agent_not_found"}


def _calls(func: object) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))  # type: ignore[arg-type]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def test_rules_use_team_package_functions() -> None:
    """같은 뜻 병합·차단 판정·준비 계산은 ``ac-teams`` 함수로 한다(자체 로직 없음, phase1r D3)."""
    assert {"merge_validation", "team_rules_apply"} <= _calls(TeamRules.check)
    assert {"validate_team"} <= _calls(TeamRules.team_issues)
    assert {"prepare_run"} <= _calls(TeamRules.prepare)
    assert {"validation_summary"} <= _calls(ValidationSummaries.compute)


# ---------------------------------------------------------------- 중첩 팀(5R.11, design §5R.7)


def _team_graph(graph_id: str, child: str, **config: Any) -> dict[str, Any]:
    """you → 중첩 팀 노드 T(자식 팀 구성 `child`) → 답변."""
    data = _graph(graph_id, "unused")
    data["nodes"][1] = {
        "id": "T",
        "type": "team",
        "label": "중첩",
        "config": {"team_ref": child, **config},
    }
    for edge in data["edges"]:
        for side in ("source", "target"):
            if edge[side]["node"] == "a":
                edge[side]["node"] = "T"
    return data


def _node_run(snap: dict[str, Any], node_id: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [nr for nr in snap["node_runs"] if nr["node_id"] == node_id]
    assert len(found) == 1, found
    return found[0]


def test_nested_team_validation_codes(tmp_path: Path) -> None:
    """팀 규칙이 자식 팀 구성을 읽어 자기·순환 참조·없음·입구 없음을 알린다."""
    with _client(tmp_path, definitions, runs, module) as (client, _assembly):
        assert client.post(f"{API}/agents", json=_agent("fast")).status_code == 201
        no_entry = _graph("lonely", "fast")
        no_entry["edges"] = [e for e in no_entry["edges"] if e["kind"] != "message"]
        for body in (
            _graph("child", "fast"),
            _team_graph("parent", "child"),
            _team_graph("me", "me"),
            _team_graph("a", "b"),
            _team_graph("b", "a"),
            _team_graph("lost", "ghost"),
            no_entry,
            _team_graph("empty", "lonely"),
        ):
            assert client.post(f"{API}/graphs", json=body).status_code == 201, body["id"]

        def codes(graph_id: str) -> list[str]:
            issues = client.post(f"{API}/graphs/{graph_id}/validate").json()
            return [i["code"] for i in issues if i["code"].startswith("team.")]

        assert codes("parent") == []
        assert codes("me") == ["team.recursive"]
        issue = client.post(f"{API}/graphs/a/validate").json()[0]
        assert (issue["code"], issue["details"]["path"]) == ("team.recursive", ["a", "b", "a"])
        assert issue["path"] == "/nodes/1/config/team_ref"
        assert codes("lost") == ["team.team_not_found"]
        assert codes("empty") == ["team.child_no_entry"]
        # 실행 전 검사도 같은 규칙(422)
        assert client.post(f"{API}/runs", json={"graph_id": "a"}).status_code == 422


def test_nested_team_runs_with_pinned_version(tmp_path: Path) -> None:
    with _client(tmp_path, definitions, runs, module) as (client, assembly):
        assert client.post(f"{API}/agents", json=_agent("fast")).status_code == 201
        old = _agent("slow")
        old["backend_options"] = {"default": {"response": "옛: $prompt"}}
        assert client.post(f"{API}/agents", json=old).status_code == 201
        created = client.post(f"{API}/graphs", json=_graph("child", "slow"))
        assert created.status_code == 201
        pinned = created.headers["ETag"].strip('"').removeprefix("W/").strip('"')
        changed = client.put(
            f"{API}/graphs/child",
            json=_graph("child", "fast"),
            headers={"If-Match": created.headers["ETag"]},
        )
        assert changed.status_code == 200, changed.text
        assert client.post(f"{API}/graphs", json=_team_graph("latest", "child")).status_code == 201
        body = _team_graph("pinned", "child", version=pinned)
        assert client.post(f"{API}/graphs", json=body).status_code == 201
        assert client.post(f"{API}/graphs/pinned/validate").json() == []

        # 노드 서비스로 팀 구성 조회가 들어간다(고정 버전 포함)
        [provider] = assembly.ports(RUN_SERVICES)
        env = type("Env", (), {"working_directory": tmp_path, "run_files_root": tmp_path / "r"})()
        lookup = provider.services(env)[TEAM_LOOKUP]
        assert lookup("child", None).nodes[1].config["agent_ref"] == "fast"
        assert lookup("child", pinned).nodes[1].config["agent_ref"] == "slow"
        assert lookup("child", "nope") is None
        assert lookup("ghost", None) is None

        for graph_id, expected in (("latest", "답: hi"), ("pinned", "옛: hi")):
            run = client.post(f"{API}/runs", json={"graph_id": graph_id, "input": {"text": "hi"}})
            assert run.status_code == 202, run.text
            snap = _wait(client, run.json()["id"])
            assert snap["run"]["status"] == "completed", snap["run"]
            assert _node_run(snap, "T")["outputs"] == {"out": expected}


def test_nested_team_without_link_fails_with_lookup_unavailable(tmp_path: Path) -> None:
    """연동을 끄면 중첩 팀 노드는 조회 수단이 없어 `team.lookup_unavailable`로 실패한다."""
    config = ModulesConfig(disabled=["link-runs-teams"])
    with _client(tmp_path, definitions, runs, module, config=config) as (client, _assembly):
        client.post(f"{API}/graphs", json=_graph("child", "fast"))
        client.post(f"{API}/graphs", json=_team_graph("parent", "child"))
        run = client.post(f"{API}/runs", json={"graph_id": "parent", "input": {"text": "hi"}})
        assert run.status_code == 202, run.text
        snap = _wait(client, run.json()["id"])
        assert snap["run"]["status"] == "failed"
        error = _node_run(snap, "T")["error"]
        assert error["code"] == "team.lookup_unavailable"
