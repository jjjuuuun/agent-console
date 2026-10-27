"""모듈 조립: 실제 `mod-logs`(메모리·SQLite 색인) + `mod-architecture` + 이 연동.

- `GET /logs/architecture`·`GET /logs/events/{uid}/architecture`, `/logs/schema` filters에 `arch`.
- 클릭 수 일치를 HTTP로(이벤트 목록 질의 = 칸 `count`), 수집 중 `max_seq` 경계.
- 모듈 매트릭스(design §5.5R.3 표): 연동을 끄면 경로 404·`arch` 422, `mod-architecture`나
  `mod-logs`를
  끄면 연동은 `unsatisfied`이고 남은 기능은 그대로.
- 오류: 상한 초과 422 `architecture.scope_too_large`, 프로필 없음 404, 모르는 필터 422.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_contracts.architecture import ArchitectureView
from agent_console_link_logs_architecture import MODULE_ID, module
from agent_console_link_logs_architecture.testing import click_count_mismatches, demo_profiles
from agent_console_mod_architecture import module as architecture_module
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_modkit import Assembly, BaseServices, Module, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "t" * 32
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}
LOGS_ID = "mod-logs"
ARCH_ID = "mod-architecture"


def _rows(rng: random.Random, count: int, start: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(count):
        category = rng.choice(["input", "llm", "tool", "agent", "error", "other"])
        row: dict[str, Any] = {
            "schema_version": 1,
            "session": rng.choice(["S1", "S1", "S2"]),
            "thread": rng.choice(["main", "main", "sub1", "sub2"]),
            "category": category,
            "title": f"e{start + i}",
            "time": 1_760_000_000 + start + i,
            "status": rng.choice(["", "", "ok", "failed"]),
            "tags": rng.sample(["tool_call", "tool_result", "x"], rng.randint(0, 2)),
        }
        if rng.random() < 0.6:
            row["tool"] = rng.choice(["Read", "Grep", "Write"])
        if category == "llm":
            row["model"] = rng.choice(["m1", "m2"])
        rows.append(row)
    return rows


def _write(root: Path, name: str, rows: Sequence[Mapping[str, Any]]) -> None:
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    (root / name).write_text(text, encoding="utf-8")


def _settings(root: Path, architecture: Mapping[str, Any] | None) -> WorkspaceSettings:
    profile = demo_profiles()["demo"].model_dump(mode="json", by_alias=True, exclude_unset=True)
    section = (
        dict(architecture)
        if architecture is not None
        else {"profiles": {"demo": profile}, "default_profile": "demo"}
    )
    return WorkspaceSettings.model_validate(
        {
            "logs": {
                "sources": [
                    {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}
                ]
            },
            "architecture": section,
        }
    )


def _assembly(
    tmp_path: Path,
    *,
    database: bool,
    disabled: Sequence[str] = (),
    architecture: Mapping[str, Any] | None = None,
    arch_options: Mapping[str, Any] | None = None,
) -> tuple[Assembly, Path]:
    root = tmp_path / "logs-src"
    root.mkdir(exist_ok=True)
    db = SqliteDatabase.open(tmp_path / "host.sqlite3") if database else None
    services = BaseServices(
        database=db,
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    options: dict[str, Any] = {
        LOGS_ID: dict(QUIET),
        MODULE_ID: {"source_kinds": {"normalized-v1": "kind-a"}},
    }
    if arch_options:
        options[ARCH_ID] = dict(arch_options)
    config = ModulesConfig(options=options, disabled=list(disabled))
    modules: list[Module] = [
        logs_module,
        architecture_module,
        module,
        static_settings_module(_settings(root, architecture)),
    ]
    return assemble(modules, config, base=services), root


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _count(client: TestClient, params: Mapping[str, Any]) -> int:
    total = 0
    cursor: str | None = None
    while True:
        query = {**params, "limit": 50}
        if cursor:
            query["cursor"] = cursor
        res = client.get(f"{API}/logs/events", params=query)
        assert res.status_code == 200, res.text
        body = res.json()
        total += len(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return total


def _view(client: TestClient, **params: Any) -> ArchitectureView:
    res = client.get(f"{API}/logs/architecture", params=params)
    assert res.status_code == 200, res.text
    return ArchitectureView.model_validate(res.json())


@pytest.mark.parametrize("database", [True, False], ids=["sqlite", "memory"])
def test_architecture_and_click_counts_over_http(tmp_path: Path, database: bool) -> None:
    rng = random.Random(1)
    assembly, root = _assembly(tmp_path, database=database)
    _write(root, "a.jsonl", _rows(rng, 120, 0))
    states = {r.id: r.state for r in assembly.report}
    assert states[MODULE_ID] == "active"
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        names = [f["id"] for f in client.get(f"{API}/logs/schema").json()["filters"]]
        assert {"arch", "arch_group", "arch_sources"} <= set(names)

        view = _view(client, session="S1")
        assert view.profile == "demo"
        assert view.event_total == _count(client, {"session": "S1"})
        assert [(s.id, s.kind) for s in view.sources] == [("normalized-v1", "kind-a")]
        wrong, checked = click_count_mismatches(
            view, lambda p: _count(client, p), {"session": "S1"}
        )
        assert wrong == []
        assert checked >= 5

        # 수집이 이어져도 옛 결과의 max_seq로 거르면 수가 같다
        _write(root, "b.jsonl", _rows(rng, 40, 1000))
        assert client.post(f"{API}/logs/scan").status_code == 202
        wrong, _ = click_count_mismatches(view, lambda p: _count(client, p), {"session": "S1"})
        assert wrong == []
        later = _view(client, session="S1")
        assert later.event_total > view.event_total
        wrong, _ = click_count_mismatches(later, lambda p: _count(client, p), {"session": "S1"})
        assert wrong == []

        # 멤버십
        first = client.get(f"{API}/logs/events", params={"session": "S1", "limit": 1}).json()
        uid = first["items"][0]["uid"]
        found = client.get(f"{API}/logs/events/{uid}/architecture").json()
        assert found["profile"] == "demo"
        assert found["uid"] == uid
        missing = client.get(f"{API}/logs/events/nope/architecture")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("database", [True, False], ids=["sqlite", "memory"])
def test_errors(tmp_path: Path, database: bool) -> None:
    assembly, root = _assembly(tmp_path, database=database, arch_options={"max_scope_events": 5})
    _write(root, "a.jsonl", _rows(random.Random(2), 20, 0))
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        too_big = client.get(f"{API}/logs/architecture", params={"session": "S1"})
        assert too_big.status_code == 422
        error = too_big.json()["error"]
        assert error["code"] == "architecture.scope_too_large"
        assert error["details"]["limit"] == 5
        assert error["details"]["events"] > 5
        bad = client.get(f"{API}/logs/architecture", params={"nope": "1"})
        assert bad.status_code == 422
        assert bad.json()["error"]["details"]["path"] == "nope"
        unknown = client.get(f"{API}/logs/events", params={"arch": "demo:cell:missing"})
        assert unknown.status_code == 422
        assert unknown.json()["error"]["details"]["path"] == "arch"


def test_no_profiles_is_404_and_logs_still_work(tmp_path: Path) -> None:
    assembly, root = _assembly(tmp_path, database=False, architecture={"include_defaults": False})
    _write(root, "a.jsonl", _rows(random.Random(3), 10, 0))
    with _client(assembly) as client:
        assert client.post(f"{API}/logs/scan").status_code == 202
        res = client.get(f"{API}/logs/architecture", params={"session": "S1"})
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "architecture.profile_not_found"
        assert client.get(f"{API}/architecture/profiles").json()["profiles"] == []
        assert _count(client, {"session": "S1"}) > 0


@pytest.mark.parametrize(
    ("disabled", "link_state"),
    [([MODULE_ID], "disabled"), ([ARCH_ID], "unsatisfied"), ([LOGS_ID], "unsatisfied")],
)
def test_module_matrix(tmp_path: Path, disabled: list[str], link_state: str) -> None:
    """§5.5R.3 표: 끈 쪽의 경로는 404, `arch`는 422, 남은 기능은 그대로."""
    assembly, root = _assembly(tmp_path, database=False, disabled=disabled)
    _write(root, "a.jsonl", _rows(random.Random(4), 10, 0))
    states = {r.id: r.state for r in assembly.report}
    assert states[MODULE_ID] == link_state
    with _client(assembly) as client:
        assert client.get(f"{API}/logs/architecture").status_code == 404
        assert client.get(f"{API}/logs/events/x/architecture").status_code == 404
        if LOGS_ID not in disabled:
            assert client.post(f"{API}/logs/scan").status_code == 202
            assert _count(client, {"session": "S1"}) > 0
            res = client.get(f"{API}/logs/events", params={"arch": "demo:cell:tools"})
            assert res.status_code == 422
            names = [f["id"] for f in client.get(f"{API}/logs/schema").json()["filters"]]
            assert "arch" not in names
        if ARCH_ID not in disabled:
            assert client.get(f"{API}/architecture/profiles").status_code == 200
