"""5.7R.22 (4b V6): 공유 메모리 R0·끄기 통합 시험(design §5.7R.11 시험 1~9).

요구: R0.1, R0.2, R16.1, R16.7, R10.7.

통합 서버(33모듈 조립, TestClient·fake 백엔드)로 본다. 범위 종류·리소스·에이전트·팀·정리 규칙·
대응표·구조도 칸은 전부 이 테스트 안에서 만든 **사용자 설정 데이터**다.
(코드 패치·저장소 데이터 파일 없음)

시험 번호(design §5.7R.11)와 테스트:

1. 빈 workspace → ``test_empty_workspace_has_only_package_defaults``
2. ``include_default_scope_kinds: false``
   → ``test_no_scope_kinds_tool_is_scope_unavailable_rest_still_works``
3. 기본 종류 id를 null로 지우기 / 같은 id를 사용자 정의로 바꾸기
   → ``test_nulling_default_kind_keeps_entries_visible_and_blocks_agent``,
   ``test_redefining_default_kind_id_changes_the_scope_template``
4. 이름이 전혀 다른 범위 종류만으로 같은 시나리오
   → ``test_scenario_is_identical_under_other_kind_names``
5. 도구 이름 바꾸기 → ``test_tool_names_follow_resource_config``
6. 모듈 매트릭스 6줄 → ``test_matrix_*``
7. 대응표 기본 ``memory.*`` 규칙 끄기 → ``test_turning_off_default_memory_event_rule``
8. 구조도 Memory 칸은 데이터로만 → ``test_architecture_memory_cell_is_user_data_only``
9. 정리 규칙 기본(빈 목록) → ``test_retention_default_is_empty_and_changes_nothing``
10. 이식성은 5.7R.26(``poe portability``)이 맡는다 — 여기서 다루지 않는다.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_link_memory_runs import MODULE_ID as LINK_ID
from agent_console_link_memory_runs import load_memory_resource_type
from agent_console_memory import load_default_scope_kinds
from agent_console_resources import SLOT_UNSUPPORTED
from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

MEMORY_MODULE = "mod-memory"
NO_PROJECT_GATE: dict[str, dict[str, Any]] = {"link-projects-runs": {"require_project": False}}
LOG_OPTIONS: dict[str, dict[str, Any]] = {
    **NO_PROJECT_GATE,
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}
DEFAULT_KINDS = set(load_default_scope_kinds())
# 패키지 기본 데이터에서 "팀 구성 id 틀"을 쓰는 종류를 찾는다(이름은 코드에 적지 않는다)
TEAM = next(k for k, v in load_default_scope_kinds().items() if v.id == "{/graph_id}")
RTYPE = load_memory_resource_type().id
SOURCE = "platform-runs"
ENTRIES = f"{API}/memory/entries"
GRAPH_ID = "solo"
ACCESS_ID = "mem-access"
Calls = list[tuple[str, dict[str, Any]]]


# ---- 사용자 데이터를 만드는 도우미(전부 테스트 안의 데이터) -------------------------------------


def _solo_graph() -> dict[str, Any]:
    return {
        "id": GRAPH_ID,
        "name": "혼자",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "keeper", "type": "agent", "label": "keeper", "config": {"agent_ref": "keeper"}},
        ],
        "edges": [
            {
                "id": "m",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "keeper", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r",
                "source": {"node": "keeper", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _access(scopes: list[dict[str, Any]], tools: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {"scopes": scopes}
    if tools:
        config["tools"] = dict(tools)
    return {"id": ACCESS_ID, "type": RTYPE, "name": "접근", "config": config}


def _set_memory(client: TestClient, section: Mapping[str, Any] | None) -> None:
    """설정 PUT으로 `memory` 섹션을 바꾼다(None = 섹션 없음)."""
    body: dict[str, Any] = client.get(f"{API}/settings").json()
    if section is None:
        body.pop("memory", None)
    else:
        body["memory"] = dict(section)
    res = client.put(f"{API}/settings", json=body)
    assert res.status_code == 200, res.text


def _create_all(client: TestClient, access: dict[str, Any] | None, calls: Calls) -> None:
    keeper = agent_doc("keeper", "끝", resources=[{"ref": ACCESS_ID}] if access else [])
    keeper["backend_options"]["default"]["host_tool_calls"] = [
        {"tool": tool, "input": data, "append": False} for tool, data in calls
    ]
    if access is not None:
        assert client.post(f"{API}/resources", json=access).status_code == 201
    assert client.post(f"{API}/agents", json=keeper).status_code == 201
    assert client.post(f"{API}/graphs", json=_solo_graph()).status_code == 201


def _events_of(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for _ in range(200):
        events = client.get(f"{API}/runs/{run_id}/events").json()
        if any(e["type"] in ("run.completed", "run.finished") for e in events):
            return events
        time.sleep(0.05)
    return events


def _run(client: TestClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = client.post(f"{API}/runs", json={"graph_id": GRAPH_ID, "input": {"text": "go"}})
    assert started.status_code == 202, started.text
    snap = wait_run(client, started.json()["id"], timeout=30)
    return snap["run"], _events_of(client, snap["run"]["id"])


def _memory_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e["type"].startswith("memory.")]


def _slot_warnings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e["payload"]["details"]
        for e in events
        if e["type"] == "log.warning"
        and (e["payload"].get("details") or {}).get("code") == SLOT_UNSUPPORTED
    ]


def _modules(client: TestClient) -> dict[str, str]:
    return {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}


def _kind_ids(client: TestClient) -> list[str]:
    return [k["kind"] for k in client.get(f"{API}/memory/scope-kinds").json()["kinds"]]


def _create_entry(client: TestClient, kind: str, scope_id: str, key: str) -> dict[str, Any]:
    res = client.post(
        ENTRIES, json={"scope": {"kind": kind, "id": scope_id}, "key": key, "content": "본문"}
    )
    assert res.status_code == 201, res.text
    created: dict[str, Any] = res.json()
    return created


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    """서버를 열고 닫는 공장(한 테스트 안에서 여러 조립을 차례로 연다)."""
    stack: list[Any] = []

    def open_server(
        *,
        disabled: list[str] | None = None,
        options: dict[str, dict[str, Any]] | None = None,
        name: str = "s",
    ) -> TestClient:
        extra: dict[str, Any] = {"modules": {"disabled": disabled}} if disabled else {}
        settings = make_settings(tmp_path / name, options=options or NO_PROJECT_GATE, **extra)
        ctx = server(settings)
        client = ctx.__enter__()
        stack.append(ctx)
        return client

    yield open_server
    while stack:
        stack.pop().__exit__(None, None, None)


# ---- 시험 1: 빈 workspace ------------------------------------------------------------------


def test_empty_workspace_has_only_package_defaults(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    assert _modules(client)[MEMORY_MODULE] == "active"
    kinds = client.get(f"{API}/memory/scope-kinds").json()
    # 이름은 패키지 데이터에서 읽는다(여기에 이름을 적지 않는다)
    assert sorted(_kind_ids(client)) == sorted(DEFAULT_KINDS)
    assert {k["origin"] for k in kinds["kinds"]} == {"default"}
    assert kinds["include_defaults"] is True
    # 항목·범위·태그 0, 사용자 데이터(리소스·에이전트·팀) 0
    assert client.get(ENTRIES).json()["items"] == []
    assert client.get(f"{API}/memory/scopes").json() == []
    assert client.get(f"{API}/memory/tags").json()["tags"] == []
    memory_resources = [r for r in client.get(f"{API}/resources").json() if r.get("type") == RTYPE]
    assert memory_resources == []
    assert client.get(f"{API}/agents").json() == []
    assert client.get(f"{API}/graphs").json() == []
    # 설정 검사는 문제를 내지 않는다(콘솔 오류 0에 해당하는 서버 쪽 확인)
    assert client.post(f"{API}/memory/settings/check", json={}).json() == []
    assert client.get(f"{API}/health").status_code == 200


# ---- 시험 2: 기본 범위 종류 전부 끄기 -----------------------------------------------------------


def test_no_scope_kinds_tool_is_scope_unavailable_rest_still_works(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    _set_memory(client, {"include_default_scope_kinds": False})
    assert _kind_ids(client) == []
    assert client.get(f"{API}/memory/scope-kinds").json()["include_defaults"] is False
    # 접근 설정이 이름만 가리켜도 해석할 종류가 없다 → 도구는 scope_unavailable, 실행은 정상
    shared = TEAM
    _create_all(
        client,
        _access([{"kind": shared, "access": ["read", "write"]}]),
        [("memory_write", {"key": "k", "content": "x"}), ("memory_read", {"key": "k"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert [e["payload"]["status"] for e in _memory_events(events)] == ["scope_unavailable"] * 2
    assert client.get(ENTRIES).json()["items"] == []
    # 항목을 만드는 REST와 다른 기능은 정상(범위 종류 해석이 없어도 저장은 된다)
    assert client.get(f"{API}/runs/{run['id']}").status_code == 200
    assert client.get(f"{API}/memory/scopes").status_code == 200


# ---- 시험 3: 기본 종류 지우기·바꾸기 -------------------------------------------------------------


def test_nulling_default_kind_keeps_entries_visible_and_blocks_agent(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    team = TEAM
    created = _create_entry(client, team, "g-old", "옛/메모")
    _set_memory(client, {"scope_kinds": {team: None}})
    kinds = {k["kind"]: k for k in client.get(f"{API}/memory/scope-kinds").json()["kinds"]}
    assert kinds[team]["disabled"] is True
    # 지운 종류의 항목은 화면에 남고 "알 수 없는 범위 종류"로 표시
    [summary] = [s for s in client.get(f"{API}/memory/scopes").json() if s["scope"]["kind"] == team]
    assert summary["kind_known"] is False
    assert client.get(f"{ENTRIES}/{created['id']}").status_code == 200
    # 에이전트는 못 쓴다
    _create_all(
        client,
        _access([{"kind": team, "access": ["read", "write"]}]),
        [("memory_read", {"key": "옛/메모"}), ("memory_write", {"key": "새", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert [e["payload"]["status"] for e in _memory_events(events)] == ["scope_unavailable"] * 2
    # 남은 기본 종류는 그대로 동작한다
    assert len(client.get(f"{API}/memory/scope-kinds").json()["kinds"]) == len(DEFAULT_KINDS)


def test_redefining_default_kind_id_changes_the_scope_template(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    team = TEAM
    # 같은 id를 사용자 정의로 통째로 바꾼다: 기본은 팀 id, 바꾼 틀은 에이전트 id
    _set_memory(
        client,
        {"scope_kinds": {team: {"label": "내 에이전트", "id": "{/agent_id}"}}},
    )
    [custom] = [
        k for k in client.get(f"{API}/memory/scope-kinds").json()["kinds"] if k["kind"] == team
    ]
    assert (custom["label"], custom["origin"]) == ("내 에이전트", "user")
    _create_all(
        client,
        _access([{"kind": team, "access": ["write"]}]),
        [("memory_write", {"key": "k", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    [event] = _memory_events(events)
    assert event["payload"]["scope"] == {"kind": team, "id": "keeper"}  # 틀대로 계산된 범위


# ---- 시험 4: 이름이 전혀 다른 범위 종류 ---------------------------------------------------------


def _shape(events: list[dict[str, Any]], names: tuple[str, str]) -> list[Any]:
    out: list[Any] = []
    for e in _memory_events(events):
        p = e["payload"]
        scope = p.get("scope") or {}
        out.append(
            (
                e["type"],
                p["status"],
                p.get("version"),
                p.get("results"),
                p.get("bytes"),
                scope.get("id"),
            )
        )
        assert not any(n in json.dumps(p, ensure_ascii=False) for n in ("본문-x",))
    assert all(n not in ("",) for n in names)
    return out


@pytest.mark.parametrize(
    "names",
    [("notes", "journal"), ("alpha", "beta")],
    ids=["notes-journal", "alpha-beta"],
)
def test_scenario_is_identical_under_other_kind_names(
    make_client: Callable[..., TestClient], names: tuple[str, str]
) -> None:
    per_graph, everyone = names
    client = make_client()
    _set_memory(
        client,
        {
            "include_default_scope_kinds": False,
            "scope_kinds": {
                per_graph: {"label": "A", "id": "{/graph_id}"},
                everyone: {"label": "B", "id": ""},
            },
        },
    )
    assert sorted(_kind_ids(client)) == sorted(names)
    _create_all(
        client,
        _access(
            [
                {"kind": per_graph, "access": ["read", "search", "write", "delete"]},
                {"kind": everyone, "access": ["read"]},
            ]
        ),
        [
            ("memory_write", {"key": "결정/api", "content": "본문-x"}),
            ("memory_search", {"query": "본문"}),
            ("memory_read", {"key": "결정/api"}),
            ("memory_write", {"key": "공지", "content": "본문-x", "scope": everyone}),  # 권한 없음
            ("memory_delete", {"key": "결정/api"}),
        ],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    shape = _shape(events, names)
    assert [s[:2] for s in shape] == [
        ("memory.write", "ok"),
        ("memory.search", "ok"),
        ("memory.read", "ok"),
        ("memory.write", "denied"),
        ("memory.delete", "ok"),
    ]
    assert shape[0][5] == GRAPH_ID  # 틀 `{/graph_id}`로 계산한 범위 id
    # 이름에 따라 달라지는 값은 범위 종류 이름뿐 — 다른 이름 쌍으로 같은 모양은 아래 비교로 확인
    _SHAPES[names[0]] = shape
    if len(_SHAPES) == 2:
        first, second = _SHAPES.values()
        assert first == second


_SHAPES: dict[str, list[Any]] = {}


# ---- 시험 5: 도구 이름 ---------------------------------------------------------------------------


def test_tool_names_follow_resource_config(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    _set_memory(
        client,
        {"include_default_scope_kinds": False, "scope_kinds": {"k1": {"label": "K", "id": ""}}},
    )
    _create_all(
        client,
        _access(
            [{"kind": "k1", "access": ["read", "write"]}],
            tools={"write": {"name": "jot", "description": "적기"}},
        ),
        [("jot", {"key": "a", "content": "x"}), ("memory_write", {"key": "b", "content": "y"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    [event] = _memory_events(events)  # 기본 이름의 호출은 도구가 없어 이벤트도 없다
    assert event["payload"]["tool"] == "jot"
    assert [i["key"] for i in client.get(ENTRIES).json()["items"]] == ["a"]


# ---- 시험 6: 모듈 매트릭스 -----------------------------------------------------------------------

RUNS_MODULES = ("mod-runs",)


def _all_modules(client: TestClient) -> list[str]:
    return list(_modules(client))


def test_matrix_memory_module_only(make_client: Callable[..., TestClient]) -> None:
    """표 1행: ``mod-memory``만(나머지 끔) → REST 동작, 에이전트 도구 없음."""
    probe = make_client(name="probe")
    everything = _all_modules(probe)
    keep = {MEMORY_MODULE}
    client = make_client(disabled=[m for m in everything if m not in keep], name="only")
    statuses = _modules(client)
    assert statuses[MEMORY_MODULE] == "active"
    assert all(
        s != "active" for m, s in statuses.items() if m != MEMORY_MODULE and m != "mod-store"
    )
    assert client.get(f"{API}/health").status_code == 200
    created = _create_entry(client, TEAM, "g", "k")
    assert client.get(f"{ENTRIES}/{created['id']}").status_code == 200
    assert client.get(f"{API}/memory/export").status_code == 200
    assert client.get(f"{API}/runs").status_code == 404  # 실행 기능이 없다
    assert client.get(f"{API}/logs/events").status_code == 404


def test_matrix_runs_without_memory_warns_once(make_client: Callable[..., TestClient]) -> None:
    """표 2행: 실행 쪽만 → 칸을 받을 공급자가 없어 경고 1건, 실행은 정상. 메모리 경로는 404."""
    client = make_client(disabled=[MEMORY_MODULE])
    statuses = _modules(client)
    assert statuses[MEMORY_MODULE] == "disabled"
    assert statuses[LINK_ID] != "active"
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["read"]}]),
        [("memory_read", {"key": "k"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert _memory_events(events) == []
    assert len(_slot_warnings(events)) == 1
    assert client.get(ENTRIES).status_code == 404
    assert client.get(f"{API}/memory/scope-kinds").status_code == 404


def test_matrix_both_with_link_tools_and_events(make_client: Callable[..., TestClient]) -> None:
    """표 3행: 둘 + link-memory-runs → 에이전트 도구와 ``memory.*`` 이벤트, 경고 없음."""
    client = make_client()
    assert _modules(client)[LINK_ID] == "active"
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["read", "write"]}]),
        [("memory_write", {"key": "k", "content": "x"}), ("memory_read", {"key": "k"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert [e["payload"]["status"] for e in _memory_events(events)] == ["ok", "ok"]
    assert _slot_warnings(events) == []
    [entry] = client.get(ENTRIES, params={"author_run": run["id"]}).json()["items"]
    assert entry["updated_by"]["kind"] == "agent"


def test_matrix_link_off_memory_screen_works_tools_gone(
    make_client: Callable[..., TestClient],
) -> None:
    """표 6행: ``link-memory-runs`` 끔 → 메모리 REST는 동작, 도구 없음, 경고 1건."""
    client = make_client(disabled=[LINK_ID])
    assert _modules(client)[LINK_ID] == "disabled"
    assert client.get(f"{API}/memory/scope-kinds").status_code == 200
    _create_entry(client, TEAM, "g", "k")
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["read", "write"]}]),
        [("memory_write", {"key": "z", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert _memory_events(events) == []
    assert len(_slot_warnings(events)) == 1
    assert [i["key"] for i in client.get(ENTRIES).json()["items"]] == ["k"]


def _scan(client: TestClient, run_id: str) -> int:
    last = -1
    for _ in range(100):
        assert client.post(f"{API}/logs/scan", json={"source_ids": [SOURCE]}).status_code == 202
        rows = client.post(
            f"{API}/logs/aggregate",
            json={"group_by": [], "metric": "events", "filter": {"run_id": [run_id]}},
        ).json()
        got = int(rows[0]["value"]) if rows else 0
        if got and got == last:
            return got
        last = got
        time.sleep(0.1)
    raise AssertionError(f"색인이 끝나지 않았다: {last}")


def test_matrix_logs_index_memory_events_by_category(
    make_client: Callable[..., TestClient],
) -> None:
    """표 4행: 위 + 로그 모듈 → ``memory.*``가 ``platform-runs`` 출처로 색인(범주 ``memory``)."""
    client = make_client(options=LOG_OPTIONS)
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["write"]}]),
        [("memory_write", {"key": "k", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    expected = len(_memory_events(events))
    assert expected == 1
    _scan(client, run["id"])
    page = client.get(
        f"{API}/logs/events",
        params={"scope": f"run:{run['id']}", "category": "memory", "limit": 50},
    ).json()
    assert len(page["items"]) == expected


def test_matrix_logs_module_off_run_and_memory_still_work(
    make_client: Callable[..., TestClient],
) -> None:
    """로그 모듈을 끄면 로그 경로만 사라지고 메모리·실행은 그대로다."""
    client = make_client(disabled=["mod-logs"])
    assert client.get(f"{API}/logs/events").status_code == 404
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["write"]}]),
        [("memory_write", {"key": "k", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    assert len(_memory_events(events)) == 1
    assert len(client.get(ENTRIES).json()["items"]) == 1


# ---- 시험 7: 대응표 기본 규칙 끄기 ---------------------------------------------------------------


def test_turning_off_default_memory_event_rule(make_client: Callable[..., TestClient]) -> None:
    client = make_client(options=LOG_OPTIONS)
    body: dict[str, Any] = client.get(f"{API}/settings").json()
    body["logs"] = {
        "sources": [{"id": SOURCE, "enabled": True, "config": {"event_map": {"memory.*": {}}}}]
    }
    assert client.put(f"{API}/settings", json=body).status_code == 200
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["write"]}]),
        [("memory_write", {"key": "k", "content": "x"})],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    types = [e["type"] for e in _memory_events(events)]
    assert len(types) == 1
    _scan(client, run["id"])
    scope: dict[str, str | int] = {"scope": f"run:{run['id']}", "limit": 200}
    items = client.get(f"{API}/logs/events", params=scope).json()["items"]
    memory_logs = [e for e in items if e["title"].startswith("memory.")]
    assert [e["category"] for e in memory_logs] == ["other"]
    assert (
        client.get(f"{API}/logs/events", params={**scope, "category": "memory"}).json()["items"]
        == []
    )
    assert {"llm", "tool_call", "system"} <= {e["category"] for e in items}  # 다른 로그는 그대로


# ---- 시험 8: 구조도 Memory 칸 = 데이터 -----------------------------------------------------------


def test_architecture_memory_cell_is_user_data_only(make_client: Callable[..., TestClient]) -> None:
    client = make_client(options=LOG_OPTIONS)
    listing = client.get(f"{API}/architecture/profiles").json()
    default_id = listing["default_profile"]
    base = client.get(f"{API}/architecture/profiles/{default_id}").json()["profile"]
    assert "memory" not in base["cells"]  # 패키지 기본 프로필에 Memory 칸이 없다
    profile = copy.deepcopy(base)
    when = {"all": [{"path": "/category", "op": "eq", "value": "memory"}]}
    profile["cells"]["memory"] = {
        "label": "Memory",
        "x": 810,
        "y": 730,
        "zone": "runtime",
        "tone": "gold",
        "metrics": ["count"],
        "when": when,
    }
    profile["coverage"][SOURCE]["cells"].append("memory")
    settings: dict[str, Any] = client.get(f"{API}/settings").json()
    settings["architecture"] = {"profiles": {"with-memory": profile}}
    assert client.put(f"{API}/settings", json=settings).status_code == 200
    assert "with-memory" in {
        p["id"] for p in client.get(f"{API}/architecture/profiles").json()["profiles"]
    }
    _create_all(
        client,
        _access([{"kind": TEAM, "access": ["write"]}]),
        [
            ("memory_write", {"key": "k", "content": "x"}),
            ("memory_write", {"key": "j", "content": "y"}),
        ],
    )
    run, events = _run(client)
    assert run["status"] == "completed", run
    _scan(client, run["id"])
    view = client.get(
        f"{API}/logs/architecture", params={"scope": f"run:{run['id']}", "profile": "with-memory"}
    ).json()
    [cell] = [c for c in view["cells"] if c["id"] == "memory"]
    assert cell["metrics"]["count"]["value"] == len(_memory_events(events)) == 2
    # 칸을 지우면 기본 프로필의 칸 목록 그대로(코드에 칸 이름이 없다)
    default_view = client.get(
        f"{API}/logs/architecture", params={"scope": f"run:{run['id']}", "profile": default_id}
    ).json()
    assert [c["id"] for c in default_view["cells"]] == list(base["cells"])


# ---- 시험 9: 정리 규칙 기본 = 빈 목록 ----------------------------------------------------


def test_retention_default_is_empty_and_changes_nothing(
    make_client: Callable[..., TestClient],
) -> None:
    client = make_client()
    old = _create_entry(client, TEAM, "g", "오래된")
    plan = client.post(f"{API}/memory/retention/plan").json()
    assert plan["count"] == 0
    assert plan["items"] == []
    result = client.post(f"{API}/memory/retention/apply").json()
    assert result["archived"] == 0
    assert result.get("deleted", 0) == 0
    entry = client.get(f"{ENTRIES}/{old['id']}").json()
    assert (entry["archived"], entry["version"]) == (False, 1)
    # 규칙은 사용자 데이터: 넣으면 그 규칙만 적용되고 지우면 다시 아무 일도 없다
    rule = {
        "id": "tmp",
        "when": {"all": [{"path": "/key", "op": "eq", "value": "오래된"}]},
        "action": "archive",
    }
    _set_memory(client, {"retention": {"rules": [rule]}})
    assert client.post(f"{API}/memory/retention/plan").json()["count"] == 1
    _set_memory(client, None)
    assert client.post(f"{API}/memory/retention/plan").json()["count"] == 0
    assert client.get(f"{ENTRIES}/{old['id']}").json()["archived"] is False
