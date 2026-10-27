"""5.5R.11: 범위 종류 ``run``·``run-tree``(X27) — 해석, 모듈 등록, 끄면 422.

design §5.5R.3 켜고 끄기 표 4·5행.

fake 백엔드 위임 실행으로 센 수는 ``tests/integration/test_integration_scope_runs_55r11.py``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, NodeRun, WorkspaceSettings
from agent_console_contracts.logs import LogSettings
from agent_console_link_logs_runs import (
    LOG_SCOPE_KINDS,
    RUN_SCOPE_KIND,
    RUN_TREE_SCOPE_KIND,
    RunScopeKind,
    module,
    run_scope_kinds,
    run_tree_ids,
)
from agent_console_link_logs_runs.testing import (
    LocalLogs,
    MemoryRunRecords,
    PlatformRunsRig,
    run_event,
    run_record,
    runs_module,
)
from agent_console_logs import LogFilter, LogQueryExtensions, LogScopeKind, query_context
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_modkit import BaseServices, Module, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

API = "/api/v1"
TOKEN = "t" * 32
OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}


def _tree(records: MemoryRunRecords) -> None:
    """r1 ─ c1 ─ g1 (자식·손자), r2는 따로. 세션: r1 = s1(NodeRun), c1 = s2(NodeRun),
    g1 = s3(플랫폼 이벤트로만 알림)."""
    records.runs.save(run_record("r1"))
    records.runs.save(run_record("c1", created_at=2.0, parent_run_id="r1"))
    records.runs.save(run_record("g1", created_at=3.0, parent_run_id="c1"))
    records.runs.save(run_record("r2", created_at=4.0))
    for run_id, node, session in (("r1", "a", "s1"), ("c1", "ca", "s2")):
        records.runs.save_node_run(
            NodeRun(run_id=run_id, node_id=node, status="succeeded", backend_session_id=session)
        )
    records.events.append(
        run_event(1, "node.started", {"status": "running"}, ("a",)),
        run_event(1, "node.started", {"status": "running"}, ("ca",), run_id="c1"),
        run_event(
            1,
            "agent.session_started",
            {"session_id": "s3", "backend": "fake-agent"},
            ("ga",),
            run_id="g1",
        ),
        run_event(1, "node.started", {"status": "running"}, ("x",), run_id="r2"),
    )


def _rig() -> tuple[PlatformRunsRig, LocalLogs]:
    rig = PlatformRunsRig()
    _tree(rig.records)
    rig.scan()
    return rig, LocalLogs(index=rig.index)


def test_run_scope_is_platform_events_and_run_sessions() -> None:
    rig, logs = _rig()
    run, tree = run_scope_kinds(rig.records.runs, logs)
    assert isinstance(run, LogScopeKind)
    assert (run.id, tree.id) == (RUN_SCOPE_KIND, RUN_TREE_SCOPE_KIND) == ("run", "run-tree")
    one = run.resolve("r1")
    assert (one.run_ids, one.sessions) == (frozenset({"r1"}), frozenset({"s1"}))
    child = run.resolve("c1")
    assert (child.run_ids, child.sessions) == (frozenset({"c1"}), frozenset({"s2"}))


def test_run_tree_scope_includes_all_descendants() -> None:
    rig, logs = _rig()
    _run, tree = run_scope_kinds(rig.records.runs, logs)
    scope = tree.resolve("r1")
    assert scope.run_ids == frozenset({"r1", "c1", "g1"})
    assert scope.sessions == frozenset({"s1", "s2", "s3"})  # s3 = 색인된 플랫폼 이벤트의 세션
    assert tree.resolve("g1").run_ids == frozenset({"g1"})
    assert run_tree_ids(rig.records.runs, "r1") == ["r1", "c1", "g1"]


def test_run_tree_walk_stops_on_cycles() -> None:
    records = MemoryRunRecords()
    records.runs.save(run_record("a", parent_run_id="b"))
    records.runs.save(run_record("b", parent_run_id="a"))
    assert run_tree_ids(records.runs, "a") == ["a", "b"]


@pytest.mark.parametrize("value", ["", "  ", "nope"])
def test_bad_values_raise_value_error(value: str) -> None:
    rig, logs = _rig()
    for kind in run_scope_kinds(rig.records.runs, logs):
        with pytest.raises(ValueError, match="Run"):
            kind.resolve(value)


def test_scope_filters_index_queries_through_extensions() -> None:
    """``LogQueryExtensions``로 풀면 색인 질의가 그 Run(트리)의 이벤트만 센다."""
    rig, logs = _rig()
    ext = LogQueryExtensions.collect(run_scope_kinds(rig.records.runs, logs))

    def runs_of(scope: str) -> list[str]:
        flt = ext.parse({"scope": scope, "limit": 100})
        ctx = ext.refine(flt, query_context(None))
        return sorted(e.run_id for e in rig.index.query_events(flt, ctx).items)

    assert runs_of("run:r1") == ["r1"]
    assert runs_of("run:c1") == ["c1"]
    assert runs_of("run-tree:r1") == ["c1", "g1", "r1"]
    assert runs_of("run-tree:r2") == ["r2"]


def test_kind_ids_are_arguments() -> None:
    rig, logs = _rig()
    kind = RunScopeKind(rig.records.runs, logs, kind_id="실행트리", tree=True)
    assert kind.id == "실행트리"
    assert kind.run_ids("r1") == ["r1", "c1", "g1"]
    [only] = run_scope_kinds(rig.records.runs, logs, kinds=[("job", False)])
    assert (only.id, only.run_ids("c1")) == ("job", ["c1"])


# ---------------------------------------------------------------- 모듈 조립


def _external_logs(folder: Path) -> WorkspaceSettings:
    """외부 세션 로그: s1·s2·s3 세션 이벤트 하나씩 + 범위 밖 세션 zz."""
    rows = [
        {"schema_version": 1, "category": "llm", "title": f"외부 {s}", "session": s}
        for s in ("s1", "s2", "s3", "zz")
    ]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    source = {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}
    return WorkspaceSettings(logs=LogSettings.model_validate({"sources": [source]}))


@contextmanager
def _client(tmp_path: Path, *, disabled: tuple[str, ...] = ()) -> Iterator[TestClient]:
    records = MemoryRunRecords()
    _tree(records)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    modules: list[Module] = [
        logs_module,
        static_settings_module(_external_logs(tmp_path / "ext")),
        runs_module(records),
        module,
    ]
    assembly = assemble(modules, ModulesConfig(options=OPTIONS, disabled=list(disabled)), base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert client.post(f"{API}/logs/scan").status_code == 202
        yield client


def _titles(client: TestClient, **params: Any) -> list[str]:
    response = client.get(f"{API}/logs/events", params={"limit": 200, **params})
    assert response.status_code == 200, response.text
    return sorted(item["title"] for item in response.json()["items"])


def test_module_registers_scope_kinds_with_union_of_events_and_sessions(tmp_path: Path) -> None:
    assert LOG_SCOPE_KINDS in module.descriptor.provides
    with _client(tmp_path) as client:
        assert _titles(client, scope="run:r1") == ["a running", "외부 s1"]
        assert _titles(client, scope="run-tree:r1") == [
            "a running",
            "ca running",
            "세션 시작 s3",
            "외부 s1",
            "외부 s2",
            "외부 s3",
        ]
        # 다른 필터와 함께(AND), 집계도 같은 범위
        assert _titles(client, scope="run-tree:r1", source="normalized-v1") == [
            "외부 s1",
            "외부 s2",
            "외부 s3",
        ]
        rows = client.post(
            f"{API}/logs/aggregate",
            json={"group_by": [], "metric": "events", "filter": {"scope": "run-tree:r1"}},
        ).json()
        assert rows[0]["value"] == 6
        bad = client.get(f"{API}/logs/events", params={"scope": "run:nope"})
        assert bad.status_code == 422
        assert bad.json()["error"]["details"]["path"] == "scope"
        # 기존 세션 로그 탭은 그대로(플랫폼 이벤트를 빼고 그 Run 세션의 외부 이벤트)
        tab = client.get(f"{API}/runs/r1/logs").json()
        assert ([i["title"] for i in tab["items"]], tab["total"]) == (["외부 s1"], 1)


def test_disabled_link_makes_run_scope_unknown_and_logs_still_work(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("link-logs-runs",)) as client:
        for scope in ("run:r1", "run-tree:r1"):
            response = client.get(f"{API}/logs/events", params={"scope": scope})
            assert response.status_code == 422, scope
            assert response.json()["error"]["details"]["path"] == "scope"
        # 세션 단위 질의(세션 구조도가 쓰는 범위)는 그대로
        assert _titles(client, session="s1") == ["외부 s1"]
        assert client.get(f"{API}/logs/sessions/s1/timeline").status_code == 200


def test_scope_kind_reads_index_with_filter_shape() -> None:
    """``run_sessions``는 기존 ``/runs/{id}/logs``와 같은 집계를 쓴다(필터 모양 회귀)."""
    _rig_unused, logs = _rig()
    page = logs.events(LogFilter(run_id=("g1",), limit=10))
    assert [e.session for e in page.items] == ["s3"]
