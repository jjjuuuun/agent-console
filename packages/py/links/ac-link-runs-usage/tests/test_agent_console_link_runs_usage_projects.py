"""link-runs-usage: 계정 창 이벤트를 프로젝트 기록 DB에서도 찾는다(요청 11/07).

프로젝트 실행의 ``usage.rate_limit``은 그 프로젝트 기록 DB에만 있다(5.7R.33y2). 계정 창은 계정
단위라 앱 기록 + 모든 등록 프로젝트 기록 중 가장 최근 것을 보인다. 프로젝트 목록·기록 공간 포트가
없으면 그 부분만 꺼지고 앱 기록은 그대로 읽는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import KnownRecordsUnavailableReasons, RunEvent
from agent_console_link_runs_usage import (
    PROJECTS_LOOKUP,
    RECORDS_SPACES,
    MergedEventQuery,
    RunsUsageSettings,
    module,
)
from agent_console_link_runs_usage.testing import local_runs_module
from agent_console_mod_usage import module as usage
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_store import (
    InMemoryStorage,
    RecordsDb,
    RecordsUnavailable,
    SqliteStorage,
    open_records_db,
)
from agent_console_usage import USAGE_SOURCES_EXTENSION, RunEventUsageSource, as_usage_source

API = "/api/v1"
TOKEN = "t" * 32
RATE = "usage.rate_limit"


def _event(run_id: str, ts: float, window: str, ratio: float, seq: int = 1) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=ts,
        node_path=[],
        type=RATE,
        payload={"window": window, "status": "allowed", "utilization": ratio},
    )


@dataclass
class _Project:
    id: str
    archived: bool = False


class _Lookup:
    def __init__(self, projects: list[_Project]) -> None:
        self.projects = projects

    def list_projects(self) -> list[_Project]:
        return list(self.projects)


class _Spaces:
    """``records.spaces`` 가짜: 공간 이름 → 기록 DB(없으면 모르는 프로젝트, 예외면 그것)."""

    def __init__(self, dbs: dict[str, RecordsDb | Exception]) -> None:
        self.dbs = dbs
        self.opened: list[str] = []

    def open(self, space: str) -> RecordsDb:
        self.opened.append(space)
        found = self.dbs.get(space)
        if found is None:
            raise LookupError(space)
        if isinstance(found, Exception):
            raise found
        return found

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass


def _records(tmp_path: Path, name: str, events: list[RunEvent]) -> RecordsDb:
    db = open_records_db(tmp_path / name / "records.sqlite3", backup_dir=tmp_path / name / "bk")
    SqliteStorage(db.writable_engine()).events.append_many(events)
    return db


def _registries() -> Any:
    class _Registries:
        def __init__(self) -> None:
            self.extensions: dict[str, Registry[Any]] = {}

        def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
            if name not in self.extensions:
                self.extensions[name] = Registry(name, validator=validator)
            return self.extensions[name]

    regs = _Registries()
    regs.extension(USAGE_SOURCES_EXTENSION, validator=as_usage_source).register(
        "run-events", RunEventUsageSource()
    )
    return regs


def _projects_module(lookup: _Lookup | None, spaces: _Spaces | None) -> Module:
    provides = [k for k, v in ((PROJECTS_LOOKUP, lookup), (RECORDS_SPACES, spaces)) if v]

    def build(ctx: ModuleContext) -> ModuleParts:
        if lookup is not None:
            ctx.provide(PROJECTS_LOOKUP, lookup)
        if spaces is not None:
            ctx.provide(RECORDS_SPACES, spaces)
        return ModuleParts()

    return fake_module("fake-projects", kind="testing", provides=provides, on_build=build)


@contextmanager
def _client(
    host: InMemoryStorage, lookup: _Lookup | None, spaces: _Spaces | None
) -> Iterator[TestClient]:
    mods: list[Module] = [usage, module, local_runs_module(storage=host)]
    if lookup is not None or spaces is not None:
        mods.append(_projects_module(lookup, spaces))
    assembly = assemble(mods, base=BaseServices(registries=_registries()))
    assert {r.state.value for r in assembly.report} == {"active"}
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        yield client


def _windows(client: TestClient) -> dict[str, tuple[float | None, str | None]]:
    body = client.get(f"{API}/usage", params={"parts": "windows"}).json()
    return {w["window"]: (w["used_ratio"], w["raw"].get("run_id")) for w in body["windows"]}


def test_usage_windows_include_project_records(tmp_path: Path) -> None:
    """프로젝트에서만 돈 실행의 창도 보이고, 창마다 앱·프로젝트 중 가장 최근 값이 이긴다."""
    host = InMemoryStorage()
    host.events.append_many([_event("host-run", 10.0, "five_hour", 0.1)])
    dbs: dict[str, RecordsDb | Exception] = {
        "project:p1": _records(tmp_path, "p1", [_event("p1-run", 20.0, "five_hour", 0.4)]),
        "project:p2": _records(tmp_path, "p2", [_event("p2-run", 15.0, "seven_day", 0.7)]),
        "project:old": _records(tmp_path, "old", [_event("old-run", 99.0, "seven_day", 0.9)]),
        "project:gone": RecordsUnavailable(KnownRecordsUnavailableReasons.FOLDER_MISSING),
    }
    spaces = _Spaces(dbs)
    projects = [_Project("p1"), _Project("p2"), _Project("old", archived=True), _Project("gone")]
    projects.append(_Project("unknown"))  # 기록 공간이 모르는 프로젝트
    with _client(host, _Lookup(projects), spaces) as client:
        assert _windows(client) == {"five_hour": (0.4, "p1-run"), "seven_day": (0.7, "p2-run")}
    assert "project:old" not in spaces.opened  # 보관한 프로젝트는 열지 않는다
    for db in dbs.values():
        if isinstance(db, RecordsDb):
            db.close()


@pytest.mark.parametrize("which", ["no-lookup", "no-spaces", "none"])
def test_without_project_ports_only_app_records(tmp_path: Path, which: str) -> None:
    """프로젝트 목록이나 기록 공간이 없으면 그 부분만 꺼진다(앱 기록은 그대로)."""
    host = InMemoryStorage()
    host.events.append_many([_event("host-run", 10.0, "five_hour", 0.1)])
    db = _records(tmp_path, "p1", [_event("p1-run", 20.0, "five_hour", 0.4)])
    lookup = None if which in ("no-lookup", "none") else _Lookup([_Project("p1")])
    spaces = None if which in ("no-spaces", "none") else _Spaces({"project:p1": db})
    with _client(host, lookup, spaces) as client:
        assert _windows(client) == {"five_hour": (0.1, "host-run")}
    db.close()


def test_merged_query_orders_limits_and_skips_broken_sources() -> None:
    a, b = InMemoryStorage(), InMemoryStorage()
    a.events.append_many([_event("a", 1.0, "w", 0.1), _event("a", 5.0, "w", 0.5, seq=2)])
    b.events.append_many([_event("b", 3.0, "w", 0.3), _event("b", 7.0, "w", 0.7, seq=2)])

    class Broken:
        def latest_by_type(self, *_a: Any, **_k: Any) -> list[RunEvent]:
            raise RuntimeError("깨진 기록")

    query = MergedEventQuery(a.events, lambda: [Broken(), b.events])
    assert [e.ts for e in query.latest_by_type(RATE, limit=3)] == [7.0, 5.0, 3.0]
    assert [e.ts for e in query.latest_by_type(RATE, run_id="a", limit=10)] == [5.0, 1.0]

    def failing() -> list[Any]:
        raise RuntimeError("목록 실패")

    assert [e.ts for e in MergedEventQuery(a.events, failing).latest_by_type(RATE)] == [5.0]


def test_settings_prefix_and_seed() -> None:
    assert RunsUsageSettings().records_space_prefix == "project:"
    seeds = module.descriptor.settings_compat
    assert seeds is not None
    assert [s.source for s in seeds.seeds] == ["modules.options.link-projects-records.space_prefix"]
