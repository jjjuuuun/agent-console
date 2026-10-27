"""mod-logs: 필터 `thread`·`scope`·`max_seq`, 포트 `logs.scope_kinds`(X27)·`logs.filter_predicates`
(X28) (작업 5.5R.5).

- 등록이 없으면 `scope`·확장 이름은 422이고 나머지는 그대로다.
- 등록이 있으면 `/logs/schema` filters에 이름이 실리고 목록·세션·타임라인·집계·handoff·보관본이
  같은 필터를 따른다. 메모리·SQLite 색인 둘 다.
- 등록 모듈을 끄면 다시 422.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_logs.testing import FieldFilter, TableScopeKind
from agent_console_mod_logs import LOGS_QUERY, LogsService, module
from agent_console_mod_logs.testing import (
    QUERY_EXTENSIONS_ID,
    query_extensions_module,
    static_settings_module,
)
from agent_console_modkit import Assembly, BaseServices, Module, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "t" * 32
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}

A = {"schema_version": 1, "session": "sess-a", "thread": "main", "cwd": "/work/proj-a"}
B = {"schema_version": 1, "session": "sess-b", "thread": "main", "cwd": "/elsewhere/tool"}
SEARCH = {"tool": "search", "call_id": "c1", "tags": ["tool"]}
# 정규화 로그(normalized-v1) 두 세션: sess-a 7행(도구 search 2행, helper 스레드), sess-b 2행
LOG_FILES: dict[str, list[dict[str, Any]]] = {
    "session-a.jsonl": [
        {
            **A,
            "category": "input",
            "title": "첫 요청",
            "time": 1760000000,
            "tags": ["session_title"],
        },
        {
            **A,
            "category": "llm",
            "title": "답변",
            "model": "model-x",
            "message_id": "m1",
            "time": 1760000001,
            "usage": {"input_tokens": 10, "output_tokens": 3},
        },
        {
            **A,
            "category": "llm",
            "title": "답변(이어짐)",
            "model": "model-x",
            "message_id": "m1",
            "time": 1760000002,
            "usage": {"input_tokens": 10, "output_tokens": 8},
        },
        {
            **A,
            **SEARCH,
            "category": "tool_call",
            "title": "검색 호출",
            "stage": "start",
            "time": 1760000003,
        },
        {
            **A,
            **SEARCH,
            "category": "tool_result",
            "title": "검색 결과",
            "stage": "complete",
            "time": 1760000005,
        },
        {
            **A,
            "category": "handoff",
            "title": "위임",
            "from": ["main"],
            "to": ["helper"],
            "via": "delegate",
            "time": 1760000006,
        },
        {
            **A,
            "thread": "helper",
            "category": "error",
            "title": "실패",
            "time": 1760000007,
            "agent": {"label": "도우미", "parent_id": "main"},
        },
    ],
    "session-b.jsonl": [
        {**B, "category": "input", "title": "다른 곳 요청", "time": 1760100000},
        {
            **B,
            "category": "llm",
            "title": "답변",
            "model": "model-y",
            "message_id": "m9",
            "time": 1760100001,
            "usage": {"input_tokens": 1, "output_tokens": 2},
        },
    ],
}

SCOPE = TableScopeKind("fake", {"a": (["sess-a"], []), "b": (["sess-b"], [])})
TOOL = FieldFilter("fake_tool", "tool")


def _assembly(
    tmp_path: Path, modules: Sequence[Module], *, database: bool, disabled: Sequence[str] = ()
) -> Assembly:
    root = tmp_path / "logs-src"
    root.mkdir()
    for name, rows in LOG_FILES.items():
        lines = [json.dumps(row, ensure_ascii=False) for row in rows]
        (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings = WorkspaceSettings.model_validate(
        {
            "logs": {
                "sources": [
                    {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}
                ]
            }
        }
    )
    db = SqliteDatabase.open(tmp_path / "host.sqlite3") if database else None
    services = BaseServices(
        database=db,
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    config = ModulesConfig(options={"mod-logs": dict(QUIET)}, disabled=list(disabled))
    return assemble([module, static_settings_module(settings), *modules], config, base=services)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _path_422(client: TestClient, url: str, params: Mapping[str, Any]) -> str:
    res = client.get(f"{API}{url}", params=params)
    assert res.status_code == 422, (url, params, res.text)
    error = res.json()["error"]
    assert error["code"] == "validation_failed"
    return str(error["details"]["path"])


def _events(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    res = client.get(f"{API}/logs/events", params={"limit": 200, **params})
    assert res.status_code == 200, res.text
    return list(res.json()["items"])


@pytest.mark.parametrize("database", [True, False], ids=["sqlite", "memory"])
def test_without_registration_scope_and_extension_are_422(tmp_path: Path, database: bool) -> None:
    assembly = _assembly(tmp_path, [], database=database)
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        everything = _events(client)
        assert len(everything) == 9
        # 새 기본 필드는 등록 없이 동작한다
        helper = _events(client, thread="helper")
        assert helper
        assert {e["thread"] for e in helper} == {"helper"}
        top = everything[3]["seq"]
        assert [e["seq"] for e in _events(client, max_seq=top)] == [
            e["seq"] for e in everything if e["seq"] <= top
        ]
        schema = client.get(f"{API}/logs/schema").json()
        names = {f["id"] for f in schema["filters"]}
        assert {"thread", "scope", "max_seq"} <= names
        assert "fake_tool" not in names
        for url in ("/logs/events", "/logs/sessions", "/logs/handoffs", "/logs/archive"):
            assert _path_422(client, url, {"scope": "fake:a"}) == "scope"
            assert _path_422(client, url, {"fake_tool": "search"}) == "fake_tool"
        assert _path_422(client, "/logs/sessions/sess-a/timeline", {"scope": "fake:a"}) == "scope"
        res = client.post(
            f"{API}/logs/aggregate",
            json={"group_by": [], "metric": "events", "filter": {"scope": "fake:a"}},
        )
        assert res.status_code == 422
        assert res.json()["error"]["details"]["path"] == "filter.scope"


@pytest.mark.parametrize("database", [True, False], ids=["sqlite", "memory"])
def test_registered_scope_and_filter_follow_every_view(tmp_path: Path, database: bool) -> None:
    assembly = _assembly(tmp_path, [query_extensions_module([SCOPE], [TOOL])], database=database)
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        schema = client.get(f"{API}/logs/schema").json()
        assert [f["id"] for f in schema["filters"]][-1] == "fake_tool"

        in_a = _events(client, scope="fake:a")
        assert in_a
        assert {e["session"] for e in in_a} == {"sess-a"}
        searched = _events(client, fake_tool="search")
        assert len(searched) == 2
        assert {e["tool"] for e in searched} == {"search"}
        assert _events(client, scope="fake:b", fake_tool="search") == []

        # 페이지 넘김(limit 1)도 같은 결과
        seen: list[int] = []
        cursor: str | None = None
        for _ in range(20):
            params: dict[str, Any] = {"scope": "fake:a", "limit": 1}
            if cursor:
                params["cursor"] = cursor
            page = client.get(f"{API}/logs/events", params=params).json()
            seen += [e["seq"] for e in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert seen == [e["seq"] for e in in_a]

        sessions = client.get(f"{API}/logs/sessions", params={"scope": "fake:b"}).json()
        assert [s["session"] for s in sessions] == ["sess-b"]
        timeline = client.get(
            f"{API}/logs/sessions/sess-a/timeline", params={"fake_tool": "search"}
        ).json()
        assert {e["tool"] for e in timeline["events"]} == {"search"}
        assert client.get(f"{API}/logs/handoffs", params={"scope": "fake:b"}).json()["cells"] == []
        rows = client.post(
            f"{API}/logs/aggregate",
            json={"group_by": [], "metric": "events", "filter": {"fake_tool": ["search"]}},
        ).json()
        assert rows == [{"keys": {}, "value": 2.0}]
        archive = client.get(f"{API}/logs/archive", params={"fake_tool": "search"})
        assert archive.status_code == 200
        assert len(archive.json()["events"]) == 2

        # 모르는 종류·값은 422
        assert _path_422(client, "/logs/events", {"scope": "nope:1"}) == "scope"
        assert _path_422(client, "/logs/events", {"scope": "fake:zzz"}) == "scope"
        assert _path_422(client, "/logs/events", {"other": "1"}) == "other"

        service = assembly.port(LOGS_QUERY)
        assert isinstance(service, LogsService)
        flt = service.parse_filter({"scope": "fake:a", "fake_tool": "search"})
        assert [e.tool for e in service.events(flt).items] == ["search", "search"]


def test_disabling_registering_module_turns_names_off(tmp_path: Path) -> None:
    assembly = _assembly(
        tmp_path,
        [query_extensions_module([SCOPE], [TOOL])],
        database=True,
        disabled=[QUERY_EXTENSIONS_ID],
    )
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        assert _path_422(client, "/logs/events", {"scope": "fake:a"}) == "scope"
        assert _path_422(client, "/logs/events", {"fake_tool": "search"}) == "fake_tool"
        assert len(_events(client)) == 9


def test_duplicate_registrations_keep_first(tmp_path: Path) -> None:
    other = TableScopeKind("fake", {"a": (["sess-b"], [])})
    assembly = _assembly(
        tmp_path,
        [query_extensions_module([SCOPE, other], [TOOL, FieldFilter("fake_tool", "thread")])],
        database=False,
    )
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        assert {e["session"] for e in _events(client, scope="fake:a")} == {"sess-a"}
        filters = [f["id"] for f in client.get(f"{API}/logs/schema").json()["filters"]]
        assert filters.count("fake_tool") == 1
