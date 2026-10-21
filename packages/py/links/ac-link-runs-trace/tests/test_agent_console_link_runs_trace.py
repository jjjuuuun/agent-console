"""link-runs-trace: 위임 흐름·넘김 집계 경로, 당시 팀 구성의 연결 종류, 포트 계약, 경로 순서."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import Run, RunEvent
from agent_console_link_runs_trace import EventReader, RunReader, TraceViews, module
from agent_console_link_runs_trace.testing import local_runs_module
from agent_console_mod_runs import RUNS_EVENTS, RUNS_READER
from agent_console_mod_runs import module as runs
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import Registries
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore, InMemoryStorage

API = "/api/v1"
TOKEN = "t" * 32
RUN = "r1"


def _event(seq: int, type: str, payload: dict[str, Any], path: list[str] | None = None) -> RunEvent:
    return RunEvent(
        event_id=f"{RUN}-{seq}",
        run_id=RUN,
        seq=seq,
        ts=float(seq),
        node_path=path or [],
        attempt=1 if path else None,
        actor=path[0] if path else None,
        type=type,
        payload=payload,
    )


def _storage() -> InMemoryStorage:
    storage = InMemoryStorage()
    storage.runs.save(
        Run(
            id=RUN,
            graph_id="flow",
            graph_version="v0",
            status="completed",
            input={},
            origin="api",
            created_at=1.0,
        )
    )
    hop = {"edge_id": "h1", "source": {"node": "pl", "port": "out"}}
    storage.events.append_many(
        [
            _event(1, "node.started", {"status": "running"}, ["pl"]),
            _event(2, "node.completed", {"status": "succeeded"}, ["pl"]),
            _event(3, "edge.traversed", {**hop, "target": {"node": "qa", "port": "in"}}),
            _event(4, "node.started", {"status": "running"}, ["qa"]),
            _event(5, "node.completed", {"status": "succeeded"}, ["qa"]),
        ]
    )
    return storage


@contextmanager
def _client(
    tmp_path: Path, *modules: Any, config: ModulesConfig | None = None
) -> Iterator[tuple[TestClient, Assembly]]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=Registries(),
    )
    assembly = assemble(list(modules), config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def test_trace_and_handoffs_from_run_records(tmp_path: Path) -> None:
    with _client(tmp_path, local_runs_module(storage=_storage()), module) as (client, _a):
        trace = client.get(f"{API}/runs/{RUN}/trace").json()
        assert trace["run_id"] == RUN
        assert [(link["source"], link["target"]) for link in trace["links"]] == [
            ("node:pl#1", "node:qa#1")
        ]
        assert trace["links"][0]["kind"] is None  # 정의 읽기가 없으면 연결 종류 없이
        matrix = client.get(f"{API}/runs/handoffs").json()
        assert matrix["runs"] == 1
        assert client.get(f"{API}/runs/missing/trace").status_code == 404


def test_edge_kinds_from_current_graph_when_history_missing(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    store.create(
        "graph",
        {
            "id": "flow",
            "name": "flow",
            "nodes": [{"id": "pl", "type": "agent"}, {"id": "qa", "type": "agent"}],
            "edges": [
                {
                    "id": "h1",
                    "source": {"node": "pl", "port": "out"},
                    "target": {"node": "qa", "port": "in"},
                    "kind": "handoff",
                }
            ],
        },
    )
    storage = _storage()
    views = TraceViews(storage.runs, storage.events, history=lambda: store)
    run = views.require_run(RUN)
    assert views.trace(run).links[0].kind == "handoff"


def test_with_runs_module_handoffs_is_not_shadowed(tmp_path: Path) -> None:
    """``/runs/handoffs``(연동)가 실행 모듈의 ``/runs/{run_id}``보다 먼저 맞는다(호스트 순서)."""
    with _client(tmp_path, runs, local_definitions_module(), module) as (client, assembly):
        assert client.get(f"{API}/runs/handoffs").json()["runs"] == 0
        assert client.get(f"{API}/runs/nope").status_code == 404
        reader, events = assembly.port(RUNS_READER), assembly.port(RUNS_EVENTS)
        assert isinstance(reader, RunReader)
        assert isinstance(events, EventReader)
    config = ModulesConfig(disabled=["link-runs-trace"])
    with _client(tmp_path, runs, local_definitions_module(), module, config=config) as (
        client,
        _assembly,
    ):
        assert client.get(f"{API}/runs/x/trace").status_code == 404


def test_requires_run_ports() -> None:
    assembly = assemble([module])
    [report] = assembly.report
    assert report.state.value == "unsatisfied"
    assert set(report.missing) == {"runs.reader", "runs.events"}


# ---------------------------------------------------------------- 5R.14 자식 Run·호출


def _run(run_id: str, *, parent: str | None = None, created: float = 1.0) -> Run:
    return Run(
        id=run_id,
        graph_id="flow",
        graph_version="v0",
        status="completed",
        input={},
        origin="api",
        created_at=created,
        parent_run_id=parent,
        parent_node_id="T" if parent else None,
        root_run_id=RUN if parent else None,
    )


def _ev(run_id: str, seq: int, type: str, payload: dict[str, Any], path: list[str]) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=float(seq),
        node_path=path,
        attempt=1,
        actor=path[-1],
        type=type,
        payload=payload,
    )


def _nested_storage() -> InMemoryStorage:
    storage = InMemoryStorage()
    storage.runs.save(_run(RUN))
    storage.runs.save(_run("c1", parent=RUN, created=2.0))
    storage.runs.save(_run("g1", parent="c1", created=3.0))
    storage.events.append_many(
        [
            _ev(RUN, 1, "node.started", {"status": "running"}, ["T"]),
            _ev(RUN, 2, "run.child_started", {"child_run_id": "c1", "node_id": "T"}, ["T"]),
            _ev(RUN, 3, "node.started", {"status": "running", "call": 0}, ["T", "pl"]),
            _ev(RUN, 4, "node.completed", {"status": "succeeded", "call": 0}, ["T", "pl"]),
            _ev(RUN, 5, "node.completed", {"status": "succeeded"}, ["T"]),
            _ev("c1", 1, "node.started", {"status": "running"}, ["T2"]),
            _ev("c1", 2, "run.child_started", {"child_run_id": "g1", "node_id": "T2"}, ["T2"]),
            _ev("g1", 1, "node.started", {"status": "running"}, ["leaf"]),
        ]
    )
    return storage


def test_trace_includes_child_runs_and_handoffs_count_each_run_once(tmp_path: Path) -> None:
    storage = _nested_storage()
    with _client(tmp_path, local_runs_module(storage=storage), module) as (client, _a):
        trace = client.get(f"{API}/runs/{RUN}/trace").json()
        spans = {s["id"]: s for s in trace["spans"]}
        assert spans["run:c1/node:T2#1"]["parent_id"] == "node:T#1"
        assert spans["run:c1/node:T2#1"]["run_id"] == "c1"
        assert spans["run:g1/node:leaf#1"]["parent_id"] == "run:c1/node:T2#1"
        assert spans["run:g1/node:leaf#1"]["run_id"] == "g1"
        # 자식 Run을 직접 열면 그 Run이 trace의 Run(손자만 묶음)
        child = client.get(f"{API}/runs/c1/trace").json()
        assert {s["id"] for s in child["spans"]} == {"node:T2#1", "run:g1/node:leaf#1"}
        matrix = client.get(f"{API}/runs/handoffs").json()
        assert matrix["runs"] == 3
        # 호출 링크(T → pl)는 루트 Run에서만 한 번 센다
        assert [(c["source"], c["target"], c["count"]) for c in matrix["cells"]] == [("T", "pl", 1)]


def test_trace_without_children(tmp_path: Path) -> None:
    storage = _nested_storage()
    views = TraceViews(storage.runs, storage.events)
    flat = views.trace(views.require_run(RUN), children=False)
    assert all(s.run_id is None for s in flat.spans)


def test_call_edges_only_for_unique_pairs() -> None:
    from agent_console_contracts import Graph
    from agent_console_link_runs_trace.views import call_edges

    def edge(eid: str, src: str, dst: str) -> dict[str, Any]:
        return {
            "id": eid,
            "source": {"node": src, "port": "o"},
            "target": {"node": dst, "port": "i"},
            "kind": "k",
        }

    graph = Graph.model_validate(
        {
            "id": "g",
            "name": "g",
            "nodes": [{"id": n, "type": "agent"} for n in ("a", "b", "c")],
            "edges": [edge("e1", "a", "b"), edge("e2", "a", "c"), edge("e3", "a", "c")],
        }
    )
    assert call_edges(graph) == {("a", "b"): "e1"}
