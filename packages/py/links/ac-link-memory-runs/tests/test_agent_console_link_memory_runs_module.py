"""link-memory-runs 모듈 조립: 메모리·실행 모듈과 함께 fake-agent 실행, 모듈 매트릭스(5.7R.15).

design §5.7R.2 표 2·3·6행:
- ``mod-memory``·``mod-runs``·이 연동이 켜짐 → 에이전트 도구·``memory.*`` 이벤트, 메모리 REST에 쓴
  주체(실행)가 보인다.
- ``mod-memory`` 끔(이 연동은 unsatisfied) → 실행은 정상, "적용하지 못한 칸" 경고(R13.5) 1건.
- 이 연동만 끔 → 메모리 REST는 동작, 실행은 정상 + 같은 경고 1건.

정의·실행·메모리 모듈과 다른 연동은 dev 의존이다(이 패키지는 import하지 않는다). 리소스 종류는
설치된 entry point에서 읽는다(통합 서버에서는 ``mod-resources`` 호스트 플러그인 로더가 한다).
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
from agent_console_link_definitions_teams import module as definitions_teams
from agent_console_link_memory_runs import (
    DEFINITION_CHECKS,
    MODULE_ID,
    MemoryResourceCheck,
    load_memory_resource_type,
    memory_slot,
    module,
)
from agent_console_link_runs_teams import module as runs_teams
from agent_console_mod_definitions import module as definitions
from agent_console_mod_memory import module as memory
from agent_console_mod_resources import module as resources
from agent_console_mod_runs import module as runs
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core import RESOURCE_TYPES_EXTENSION
from agent_console_resources import SLOT_UNSUPPORTED, load_resource_types
from agent_console_runtime import Registries, load_registries

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
RTYPE = load_memory_resource_type()
BODY = "팀 결정: 응답 형식은 JSON v2"


def _write(folder: Path, item_id: str, document: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item_id}.yaml").write_text(json.dumps(document, ensure_ascii=False), "utf-8")


def _agent(agent_id: str, response: str, *calls: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {
            "default": {
                "response": response,
                "host_tool_calls": [{"tool": t, "input": i, "append": False} for t, i in calls],
            }
        },
        "resources": [{"ref": "mem"}],
    }


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "settings.yaml").write_text(
        json.dumps(
            {
                "memory": {
                    "include_default_scope_kinds": False,
                    "scope_kinds": {"notes": {"label": "노트", "id": "{/graph_id}"}},
                }
            },
            ensure_ascii=False,
        ),
        "utf-8",
    )
    _write(
        ws / "resources",
        "mem",
        {
            "id": "mem",
            "type": RTYPE.id,
            "name": "노트 접근",
            "config": {"scopes": [{"kind": "notes", "access": ["read", "search", "write"]}]},
        },
    )
    _write(
        ws / "agents",
        "writer",
        _agent("writer", "$host_1_status", ("memory_write", {"key": "결정/형식", "content": BODY})),
    )
    _write(
        ws / "agents",
        "reader",
        _agent("reader", "$host_1", ("memory_read", {"key": "결정/형식"})),
    )
    _write(
        ws / "graphs",
        "g1",
        {
            "id": "g1",
            "name": "팀",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "w", "type": "agent", "label": "w", "config": {"agent_ref": "writer"}},
                {"id": "r", "type": "agent", "label": "r", "config": {"agent_ref": "reader"}},
            ],
            "edges": [
                {
                    "id": "m1",
                    "source": {"node": "you", "port": "says"},
                    "target": {"node": "w", "port": "in"},
                    "kind": "message",
                    "config": {},
                },
                {
                    "id": "h1",
                    "source": {"node": "w", "port": "out"},
                    "target": {"node": "r", "port": "in"},
                    "kind": "handoff",
                    "config": {},
                },
                {
                    "id": "r1",
                    "source": {"node": "r", "port": "out"},
                    "target": {"node": "you", "port": "hears"},
                    "kind": "reply",
                    "config": {},
                },
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
                {"id": "w", "type": "agent", "label": "w", "config": {"agent_ref": "writer"}},
            ],
            "edges": [
                {
                    "id": "m1",
                    "source": {"node": "you", "port": "says"},
                    "target": {"node": "w", "port": "in"},
                    "kind": "message",
                    "config": {},
                },
                {
                    "id": "r1",
                    "source": {"node": "w", "port": "out"},
                    "target": {"node": "you", "port": "hears"},
                    "kind": "reply",
                    "config": {},
                },
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
        [definitions, resources, runs, runs_teams, definitions_teams, memory, module],
        config,
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


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


def test_run_writes_reads_and_rest_shows_author(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        assert assembly.status(MODULE_ID).state == "active"
        run, events = _run(client)
        assert run["status"] == "completed", run
        mem = _of(events, "memory.")
        assert [(e["type"], e["payload"]["status"]) for e in mem] == [
            ("memory.write", "ok"),
            ("memory.read", "ok"),
        ]
        assert mem[0]["payload"]["scope"] == {"kind": "notes", "id": "g1"}
        assert all(BODY not in json.dumps(e["payload"], ensure_ascii=False) for e in mem)
        [reply] = _of(events, "run.reply")
        assert BODY in reply["payload"]["text"]
        assert _slot_warnings(events) == []

        page = client.get(f"{API}/memory/entries", params={"author_run": run["id"]}).json()
        [item] = page["items"]
        assert (item["key"], item["version"]) == ("결정/형식", 1)
        assert item["updated_by"]["kind"] == "agent"
        assert (item["updated_by"]["agent_id"], item["updated_by"]["graph_id"]) == ("writer", "g1")


def test_memory_module_off_run_completes_with_one_slot_warning(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("mod-memory",)) as (client, assembly):
        report = assembly.status(MODULE_ID)
        assert report.state == "unsatisfied"
        assert report.missing == ("memory.service",)
        run, events = _run(client, "solo")
        assert run["status"] == "completed", run
        assert _of(events, "memory.") == []
        [warning] = _slot_warnings(events)
        assert warning["slot"] == memory_slot(RTYPE)
        assert warning["resources"] == ["mem"]
        # 메모리 에이전트가 둘인 팀은 노드마다 1건(실행은 정상)
        run, events = _run(client)
        assert run["status"] == "completed", run
        assert len(_slot_warnings(events)) == 2
        assert client.get(f"{API}/memory/scope-kinds").status_code == 404


def test_link_off_memory_rest_works_and_run_warns_once(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=(MODULE_ID,)) as (client, _assembly):
        run, events = _run(client, "solo")
        assert run["status"] == "completed", run
        assert _of(events, "memory.") == []
        assert len(_slot_warnings(events)) == 1
        kinds = client.get(f"{API}/memory/scope-kinds").json()["kinds"]
        assert [k["kind"] for k in kinds] == ["notes"]
        assert client.get(f"{API}/memory/entries").json()["items"] == []


def test_definition_check_warns_unknown_scope_kind(tmp_path: Path) -> None:
    with _client(tmp_path) as (_unused, assembly):
        checks = assembly.ports(DEFINITION_CHECKS)
        [check] = [c for c in checks if isinstance(c, MemoryResourceCheck)]
        doc = {
            "id": "x",
            "type": RTYPE.id,
            "name": "x",
            "config": {"scopes": [{"kind": "notes"}, {"kind": "ghost"}]},
        }
        issues = check.issues("resource", doc)
        assert [(i.code, i.path) for i in issues] == [
            (KnownIssueCodes.MEMORY_UNKNOWN_SCOPE_KIND, "/config/scopes/1/kind")
        ]
