"""link-wiki-runs 모듈 조립: 위키·실행 모듈과 함께 fake-agent 실행, 모듈 매트릭스(7R.14).

design §7R.4 끄기 표:
- ``mod-wiki``·``mod-runs``·이 연동이 켜짐 → 에이전트 도구·지침·``wiki.*`` 이벤트, 위키 REST
  ``/wiki/changes?author_run=``에 쓴 주체(실행·에이전트 이름)가 보이고 ``capabilities.runs`` 참.
- ``mod-wiki`` 끔(이 연동은 unsatisfied) → 실행은 정상, "적용하지 못한 칸" 경고(R13.5) 1건.
- 이 연동만 끔 → 위키 REST는 동작(``capabilities.runs`` 거짓), 실행은 정상 + 같은 경고 1건.

정의·실행·위키 모듈과 다른 연동은 dev 의존이다(이 패키지는 import하지 않는다). 리소스 종류는
설치된 entry point에서 읽는다(통합 서버에서는 ``mod-resources`` 호스트 플러그인 로더가 한다).
위키 규칙·위키는 테스트 안에서 REST로 만든다(저장소 데이터에 두지 않는다).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, KnownIssueCodes
from agent_console_contracts.wiki import wiki_access_defaults
from agent_console_link_definitions_teams import module as definitions_teams
from agent_console_link_runs_teams import module as runs_teams
from agent_console_link_wiki_runs import (
    DEFINITION_CHECKS,
    MODULE_ID,
    WikiResourceCheck,
    load_wiki_resource_type,
    module,
    wiki_slot,
)
from agent_console_mod_definitions import module as definitions
from agent_console_mod_resources import module as resources
from agent_console_mod_runs import module as runs
from agent_console_mod_wiki import module as wiki
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core import RESOURCE_TYPES_EXTENSION
from agent_console_resources import SLOT_UNSUPPORTED, load_resource_types
from agent_console_runtime import Registries, load_registries

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
RTYPE = load_wiki_resource_type()
TOOLS = {op: t["name"] for op, t in wiki_access_defaults()["tools"].items()}
BODY = "팀 결정: 응답 형식은 JSON v2"
WIKI = "team-notes"


def _write(folder: Path, item_id: str, document: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item_id}.yaml").write_text(json.dumps(document, ensure_ascii=False), "utf-8")


def _agent(
    agent_id: str, name: str, response: str, *calls: tuple[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": name,
        "backend": "fake-agent",
        "backend_options": {
            "default": {
                "response": response,
                "host_tool_calls": [{"tool": t, "input": i, "append": False} for t, i in calls],
            }
        },
        "resources": [{"ref": "wiki-rw"}],
    }


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": {},
    }


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    _write(
        ws / "resources",
        "wiki-rw",
        {
            "id": "wiki-rw",
            "type": RTYPE.id,
            "name": "위키 접근",
            "config": {"wikis": [{"wiki": WIKI, "access": ["read", "search", "write"]}]},
        },
    )
    _write(
        ws / "agents",
        "keeper",
        _agent(
            "keeper",
            "위키 관리자",
            "$host_1_status",
            (TOOLS["write"], {"path": "decisions/format", "content": BODY}),
        ),
    )
    _write(
        ws / "agents",
        "reader",
        _agent("reader", "읽는 이", "$host_1", (TOOLS["read"], {"path": "decisions/format"})),
    )
    _write(
        ws / "graphs",
        "g1",
        {
            "id": "g1",
            "name": "팀",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "k", "type": "agent", "label": "k", "config": {"agent_ref": "keeper"}},
                {"id": "r", "type": "agent", "label": "r", "config": {"agent_ref": "reader"}},
            ],
            "edges": [
                _edge("m1", "you", "says", "k", "in", "message"),
                _edge("h1", "k", "out", "r", "in", "handoff"),
                _edge("r1", "r", "out", "you", "hears", "reply"),
            ],
        },
    )
    _write(
        ws / "graphs",
        "solo",
        {
            "id": "solo",
            "name": "혼자",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "k", "type": "agent", "label": "k", "config": {"agent_ref": "keeper"}},
            ],
            "edges": [
                _edge("m1", "you", "says", "k", "in", "message"),
                _edge("r1", "k", "out", "you", "hears", "reply"),
            ],
        },
    )
    return ws


@contextmanager
def _client(tmp_path: Path, *, disabled: tuple[str, ...] = ()) -> Iterator[tuple[TestClient, Any]]:
    registries = Registries()
    load_registries(registries)
    load_resource_types(registries.extension(RESOURCE_TYPES_EXTENSION))
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=_workspace(tmp_path), state=tmp_path / "state"),
        registries=registries,
    )
    config = ModulesConfig(disabled=list(disabled))
    assembly = assemble(
        [definitions, resources, runs, runs_teams, definitions_teams, wiki, module],
        config,
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _make_wiki(client: TestClient) -> None:
    rules = {
        "id": "house",
        "name": "집 규칙",
        "write_rules": [
            {"id": "no-temp", "deny_patterns": ["TEMPNOTE"], "message": "임시 메모 금지"}
        ],
    }
    assert client.post(f"{API}/wiki/rules", json=rules).status_code == 201
    created = client.post(f"{API}/wiki/wikis", json={"name": "Team Notes", "rules": ["house"]})
    assert created.status_code == 201, created.text
    assert created.json()["wiki"]["id"] == WIKI


def _run(client: TestClient, graph_id: str = "g1") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    created = client.post(f"{API}/runs", json={"graph_id": graph_id, "input": {"text": "시작"}})
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()["run"]
        if run["status"] in TERMINAL:
            events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
            return run, events
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _of(events: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"].startswith(prefix)]


def _slot_warnings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e["payload"]["details"]
        for e in _of(events, "log.warning")
        if e["payload"]["details"].get("code") == SLOT_UNSUPPORTED
    ]


def test_run_writes_reads_and_wiki_rest_shows_author(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        assert assembly.status(MODULE_ID).state == "active"
        _make_wiki(client)
        assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is True
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": "wiki.changed"}})
            client.get(f"{API}/wiki/info")  # 구독이 자리 잡을 시간
            run, events = _run(client)
            message = ws.receive_json()
        assert run["status"] == "completed", run
        assert message["type"] == "wiki.changed"
        assert (message["payload"]["wiki_id"], message["payload"]["paths"]) == (
            WIKI,
            ["decisions/format"],
        )
        found = _of(events, "wiki.")
        assert [(e["type"], e["payload"]["status"]) for e in found] == [
            ("wiki.write", "ok"),
            ("wiki.read", "ok"),
        ]
        assert all(BODY not in json.dumps(e["payload"], ensure_ascii=False) for e in found)
        [reply] = _of(events, "run.reply")
        assert BODY in reply["payload"]["text"]
        assert _slot_warnings(events) == []

        # 에이전트 정의를 지워도 기록에 그때 이름이 남는다
        assert client.delete(f"{API}/agents/keeper").status_code in (200, 204)
        page = client.get(f"{API}/wiki/changes", params={"author_run": run["id"]}).json()
        [item] = page["items"]
        assert (item["wiki"], item["path"], item["op"]) == (WIKI, "decisions/format", "create")
        author = item["author"]
        assert (author["kind"], author["agent_id"], author["label"]) == (
            "agent",
            "keeper",
            "위키 관리자",
        )
        assert (author["run_id"], author["root_run_id"], author["graph_id"]) == (
            run["id"],
            run["id"],
            "g1",
        )
        text = client.get(f"{API}/wiki/wikis/{WIKI}/pages/decisions/format").json()["content"]
        assert text == BODY


def test_wiki_module_off_run_completes_with_one_slot_warning(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("mod-wiki",)) as (client, assembly):
        report = assembly.status(MODULE_ID)
        assert report.state == "unsatisfied"
        assert report.missing == ("wiki.service",)
        run, events = _run(client, "solo")
        assert run["status"] == "completed", run
        assert _of(events, "wiki.") == []
        [warning] = _slot_warnings(events)
        assert warning["slot"] == wiki_slot(RTYPE)
        assert warning["resources"] == ["wiki-rw"]
        assert client.get(f"{API}/wiki/info").status_code == 404


def test_link_off_wiki_rest_works_and_run_warns_once(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=(MODULE_ID,)) as (client, _assembly):
        _make_wiki(client)
        assert client.get(f"{API}/wiki/info").json()["capabilities"]["runs"] is False
        run, events = _run(client, "solo")
        assert run["status"] == "completed", run
        assert _of(events, "wiki.") == []
        assert len(_slot_warnings(events)) == 1
        page = client.get(f"{API}/wiki/wikis/{WIKI}/pages/decisions/format")
        assert page.status_code == 404


def test_run_against_missing_wiki_warns_unavailable(tmp_path: Path) -> None:
    """위키를 만들지 않은 공간: 도구는 오고 호출은 ``wiki_unavailable``, 경고 1건."""
    with _client(tmp_path) as (client, _assembly):
        run, events = _run(client, "solo")
        assert run["status"] == "completed", run
        [event] = _of(events, "wiki.")
        assert event["payload"]["status"] == "wiki_unavailable"
        codes = [e["payload"]["details"].get("code") for e in _of(events, "log.warning")]
        assert codes.count(KnownIssueCodes.WIKI_WIKI_UNAVAILABLE) == 1
        assert _slot_warnings(events) == []


def test_resource_save_carries_unknown_wiki_warning(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        _make_wiki(client)
        [check] = [c for c in assembly.ports(DEFINITION_CHECKS) if isinstance(c, WikiResourceCheck)]
        doc = {
            "id": "wiki-ghost",
            "type": RTYPE.id,
            "name": "x",
            "config": {"wikis": [{"wiki": WIKI}, {"wiki": "ghost"}]},
        }
        assert [(i.code, i.path) for i in check.issues("resource", doc)] == [
            (KnownIssueCodes.WIKI_UNKNOWN_WIKI, "/config/wikis/1/wiki")
        ]
        created = client.post(f"{API}/resources", json=doc)
        assert created.status_code == 201
        [issue] = json.loads(created.headers["x-console-issues"])
        assert (issue["severity"], issue["code"], issue["details"]) == (
            "warning",
            KnownIssueCodes.WIKI_UNKNOWN_WIKI,
            {"wiki": "ghost"},
        )


# ---------------------------------------------------------------- 노드 종류 wiki-update(7R.17)

UPDATE_RESULT = "구현 완료: 로그인 API"


def _update_team(tmp_path: Path, **config: Any) -> None:
    """사람 → dev(fake) → keep(wiki-update) → 사람. 위키 리소스 없는 에이전트."""
    ws = tmp_path / "ws"
    _write(
        ws / "agents",
        "dev",
        {
            "id": "dev",
            "name": "개발",
            "backend": "fake-agent",
            "backend_options": {"default": {"response": UPDATE_RESULT}},
        },
    )
    _write(
        ws / "graphs",
        "upd",
        {
            "id": "upd",
            "name": "기록 팀",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "dev", "type": "agent", "label": "dev", "config": {"agent_ref": "dev"}},
                {"id": "keep", "type": "wiki-update", "label": "기록", "config": config},
            ],
            "edges": [
                _edge("m1", "you", "says", "dev", "in", "message"),
                _edge("h1", "dev", "out", "keep", "in", "handoff"),
                _edge("r1", "keep", "out", "you", "hears", "reply"),
            ],
        },
    )


def _node_runs(client: TestClient, run_id: str) -> dict[str, dict[str, Any]]:
    snapshot = client.get(f"{API}/runs/{run_id}").json()
    return {n["node_id"]: n for n in snapshot["node_runs"]}


def test_wiki_update_node_appends_section_and_records_system_author(tmp_path: Path) -> None:
    _update_team(tmp_path, wiki=WIKI, path="log", content="## {node_id}\n{input}\n")
    with _client(tmp_path) as (client, _assembly):
        _make_wiki(client)
        types = {t["id"] for t in client.get(f"{API}/node-types").json()}
        assert "wiki-update" in types
        issues = client.post(f"{API}/graphs/upd/validate").json()
        assert [i for i in issues if i["severity"] == "error"] == []
        assert not [i for i in issues if i["code"] == "wiki.update_unavailable"]
        put = client.put(
            f"{API}/wiki/wikis/{WIKI}/pages/log",
            json={"content": "# 작업 기록\n"},
            headers={"If-None-Match": "*"},
        )
        assert put.status_code in (200, 201), put.text

        run, events = _run(client, "upd")
        assert run["status"] == "completed", run
        text = client.get(f"{API}/wiki/wikis/{WIKI}/pages/log").json()["content"]
        assert text == f"# 작업 기록\n## keep\n{UPDATE_RESULT}\n"
        [event] = _of(events, "wiki.")
        assert (event["type"], event["payload"]["status"]) == ("wiki.write", "ok")
        assert UPDATE_RESULT not in json.dumps(event["payload"], ensure_ascii=False)
        page = client.get(f"{API}/wiki/changes", params={"author_run": run["id"]}).json()
        [item] = page["items"]
        assert (item["author"]["kind"], item["author"]["label"]) == ("system", "keep")


def test_wiki_update_rule_rejection_fails_node(tmp_path: Path) -> None:
    _update_team(tmp_path, wiki=WIKI, path="log", content="TEMPNOTE {input}")
    with _client(tmp_path) as (client, _assembly):
        _make_wiki(client)
        run, events = _run(client, "upd")
        nodes = _node_runs(client, run["id"])
        assert nodes["keep"]["status"] == "failed"
        error = nodes["keep"]["error"]
        assert error["code"] == KnownIssueCodes.WIKI_RULE_REJECTED
        assert error["details"]["rule_id"] == "no-temp"
        [event] = _of(events, "wiki.")
        assert event["payload"]["status"] == "rule_rejected"
        assert client.get(f"{API}/wiki/wikis/{WIKI}/pages/log").status_code == 404


def test_wiki_update_with_wiki_module_off_warns_in_validation(tmp_path: Path) -> None:
    _update_team(tmp_path, wiki=WIKI, path="log")
    with _client(tmp_path, disabled=("mod-wiki",)) as (client, _assembly):
        issues = client.post(f"{API}/graphs/upd/validate").json()
        [warn] = [i for i in issues if i["code"] == "wiki.update_unavailable"]
        assert warn["severity"] == "warning"
        run, events = _run(client, "upd")
        assert run["status"] == "completed", run
        assert _node_runs(client, run["id"])["keep"]["status"] == "skipped"
        codes = [e["payload"]["details"].get("code") for e in _of(events, "log.warning")]
        assert codes.count("wiki.update_unavailable") == 1
        assert _of(events, "wiki.") == []
