"""mod-usage: 부분 조회(parts)·선택 포트·끄기·관측값 정리(design §3R.1.3·§3R.5)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    TokenRollupRow,
    Usage,
    UsageSettings,
    UsageSourceSetting,
    UsageWindowSnapshot,
    WorkspaceSettings,
)
from agent_console_mod_usage import (
    EVENT_QUERY,
    TOKEN_ROLLUPS,
    USAGE_SERVICE,
    USAGE_SOURCES,
    WORKSPACE_SETTINGS,
    TokenRollups,
    UsageReportService,
    module,
    parse_parts,
)
from agent_console_mod_usage.storage import SqliteUsageObservationRepository
from agent_console_modkit import BaseServices, DatabaseHandle, ModulesConfig, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_registry import Registry
from agent_console_store import SqliteDatabase
from agent_console_usage import FakeUsageSource, UsageSource, as_usage_source

FIXED = datetime(2026, 10, 17, tzinfo=UTC)
WINDOWS = {"windows": [{"window": "five_hour", "used_ratio": 0.5}]}


class _Registries:
    """호스트 레지스트리 묶음 흉내(``extension``만)."""

    def __init__(self) -> None:
        self.extensions: dict[str, Registry[Any]] = {}

    def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
        if name not in self.extensions:
            self.extensions[name] = Registry(name, validator=validator)
        return self.extensions[name]


def _registries() -> _Registries:
    regs = _Registries()
    sources: Registry[UsageSource] = regs.extension("usage_sources", validator=as_usage_source)
    sources.register("fake", FakeUsageSource())
    return regs


class _Rollups:
    def __init__(self) -> None:
        self.calls = 0

    def rollups(self, *, limit: int, tz: tzinfo) -> Sequence[TokenRollupRow]:
        self.calls += 1
        return [TokenRollupRow(model="m", runs=limit, usage=Usage(total_tokens=limit))]


class RecordingDb:
    """``DatabaseHandle`` 흉내: 올린 계보 이름만 기록."""

    def __init__(self) -> None:
        self.upgraded: list[list[str]] = []

    @property
    def engine(self) -> Any:
        return None

    def upgrade(self, branches: Iterable[Any] = ()) -> None:
        self.upgraded.append([b.name for b in branches])

    def close(self) -> None:
        pass


def _workspace() -> WorkspaceSettings:
    return WorkspaceSettings(
        usage=UsageSettings(sources=[UsageSourceSetting(id="fake", config=WINDOWS)])
    )


def _providers(rollups: _Rollups) -> Any:
    def build(ctx: Any) -> None:
        ctx.provide(TOKEN_ROLLUPS, rollups)
        ctx.provide(WORKSPACE_SETTINGS, _workspace)

    return fake_module("providers", provides=[TOKEN_ROLLUPS, WORKSPACE_SETTINGS], on_build=build)


def _base(database: DatabaseHandle | None = None) -> BaseServices:
    return BaseServices(clock=lambda: FIXED, registries=_registries(), database=database)


def _client(
    *modules: Any, config: ModulesConfig | None = None, database: DatabaseHandle | None = None
) -> TestClient:
    assembly = assemble([module, *modules], config, base=_base(database))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    return TestClient(create_host_app(assembly, policy=policy))


def test_parse_parts_ignores_unknown_and_defaults_to_all() -> None:
    assert parse_parts(None) == {"windows", "tokens"}
    assert parse_parts([""]) == {"windows", "tokens"}
    assert parse_parts(["windows", "tokens,windows"]) == {"windows", "tokens"}
    assert parse_parts(["future"]) == frozenset()


def test_windows_only_does_not_read_run_records(tmp_path: Path) -> None:
    """창만 요청하면 토큰 집계(실행 기록)를 부르지 않는다(D11 수용 기준)."""
    rollups = _Rollups()
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    with _client(_providers(rollups), database=db) as client:
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        assert body["rollups"] is None
        assert [w["window"] for w in body["windows"]] == ["five_hour"]
        assert rollups.calls == 0
        both = client.get("/api/v1/usage").json()
        assert [(r["model"], r["runs"]) for r in both["rollups"]] == [("m", 500)]
        assert rollups.calls == 1
        tokens = client.get("/api/v1/usage", params={"parts": "tokens"}).json()
        assert tokens["windows"] is None
        assert rollups.calls == 2
    # 창을 모은 두 번만 기록한다(같은 (출처, 창, 관측 시각)은 한 행으로 교체된다)
    [row] = SqliteUsageObservationRepository(db.engine).latest()
    assert (row.source, row.window, row.observed_at) == ("fake", "five_hour", FIXED.timestamp())
    db.close()


def test_without_optional_ports_rollups_are_empty_and_test_only_source_is_off() -> None:
    with _client() as client:
        body = client.get("/api/v1/usage").json()
        assert body["rollups"] == []
        assert body["windows"] == []
        [source] = client.get("/api/v1/usage/sources").json()
        # fake는 test_only: 설정에 적지 않으면 켜지지 않는다(5.2R.27)
        assert source["enabled"] is False
        assert source["descriptor"]["id"] == "fake"
        assert source["descriptor"]["test_only"] is True


def test_disabled_module_routes_are_404() -> None:
    with _client(config=ModulesConfig(disabled=["mod-usage"])) as client:
        assert client.get("/api/v1/usage").status_code == 404
        assert client.get("/api/v1/usage/sources").status_code == 404


def test_settings_schema_and_service_port() -> None:
    rollups = _Rollups()
    config = ModulesConfig(options={"mod-usage": {"rollup_run_limit": 7}})
    assembly = assemble([module, _providers(rollups)], config, base=_base())
    service = assembly.port(USAGE_SERVICE)
    assert isinstance(service, UsageReportService)
    report = asyncio.run(service.report(["tokens"]))
    assert report.rollups is not None
    assert report.rollups[0].runs == 7
    bad = assemble([module], ModulesConfig(options={"mod-usage": {"nope": 1}}), base=_base())
    assert bad.report[0].state.value == "failed"


def test_rollup_provider_matches_protocol() -> None:
    assert isinstance(_Rollups(), TokenRollups)
    assert {EVENT_QUERY.name, TOKEN_ROLLUPS.name, WORKSPACE_SETTINGS.name, USAGE_SOURCES.name} == {
        p.name for p in module.descriptor.optional
    }


async def test_prune_runs_in_background_when_database_exists(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    config = ModulesConfig(options={"mod-usage": {"retention_seconds": 60}})
    assembly = assemble([module], config, base=_base(db))  # 계보가 켜지면서 올라간다
    repo = SqliteUsageObservationRepository(db.engine)
    now = FIXED.timestamp()
    repo.record(UsageWindowSnapshot(source="s", window="w", observed_at=now - 120))
    repo.record(UsageWindowSnapshot(source="s", window="w", observed_at=now - 10))
    await assembly.start()
    try:
        for _ in range(200):
            if len(repo.history("s", "w")) == 1:
                break
            await asyncio.sleep(0.01)
    finally:
        await assembly.stop()
    assert [h.observed_at for h in repo.history("s", "w")] == [now - 10]
    db.close()


def test_without_database_nothing_is_recorded_and_everything_else_works() -> None:
    with _client(_providers(_Rollups())) as client:
        assert client.get("/api/v1/usage").status_code == 200


def test_module_declares_usage_branch_and_enabling_it_only() -> None:
    db = RecordingDb()
    assemble([module], ModulesConfig(disabled=["mod-usage"]), base=_base(db))
    assert db.upgraded == []
    assemble([module], None, base=_base(db))
    assert db.upgraded == [["usage"]]


def test_without_registries_loads_installed_sources() -> None:
    assembly = assemble([module], base=BaseServices(clock=lambda: FIXED))
    service = assembly.port(USAGE_SERVICE)
    assert service is not None
    assert "fake" in {s.descriptor.id for s in service.sources()}


@pytest.mark.parametrize("parts", [["windows"], ["tokens"]])
def test_report_service_without_http(parts: list[str]) -> None:
    rollups = _Rollups()
    from agent_console_usage import UsageService

    sources: Registry[UsageSource] = Registry("usage_sources", validator=as_usage_source)
    service = UsageReportService(
        UsageService(sources, clock=FIXED.timestamp), rollups=rollups, clock=FIXED.timestamp
    )
    report = asyncio.run(service.report(parts))
    assert (report.windows is None) == ("windows" not in parts)
    assert (report.rollups is None) == ("tokens" not in parts)
