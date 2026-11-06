"""호스트 DB 핸들: 켜진 모듈의 마이그레이션 계보만 올린다(design §3R.1.7)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent_console_modkit import (
    BaseServices,
    DatabaseHandle,
    MigrationBranch,
    ModuleContext,
    ModulesConfig,
    ModuleState,
    assemble,
)
from agent_console_modkit.testing import fake_module


class RecordingDatabase:
    """``DatabaseHandle`` 흉내: ``upgrade`` 호출을 기록한다."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.upgrades: list[list[str]] = []
        self.closed = False
        self._fail_on = fail_on

    @property
    def engine(self) -> Any:
        return object()

    def upgrade(self, branches: Iterable[MigrationBranch] = ()) -> None:
        names = [b.name for b in branches]
        if self._fail_on in names:
            raise RuntimeError("secret detail")
        self.upgrades.append(names)

    def close(self) -> None:
        self.closed = True


def _branch(name: str) -> MigrationBranch:
    return MigrationBranch(name, Path("/nowhere") / name)


def test_recording_database_satisfies_protocol() -> None:
    assert isinstance(RecordingDatabase(), DatabaseHandle)


def test_only_enabled_modules_branches_are_upgraded() -> None:
    db = RecordingDatabase()
    a = fake_module("mod-a", migrations=[_branch("a")])
    b = fake_module("mod-b", migrations=[_branch("b")])
    plain = fake_module("mod-plain")
    assembly = assemble(
        [a, b, plain], ModulesConfig(disabled=["mod-b"]), base=BaseServices(database=db)
    )
    assert db.upgrades == [["a"]]
    assert assembly.status("mod-b") is not None
    assert assembly.status("mod-b").state is ModuleState.DISABLED  # type: ignore[union-attr]


def test_unsatisfied_module_does_not_upgrade() -> None:
    db = RecordingDatabase()
    needs = fake_module("mod-needs", requires=["x.port"], migrations=[_branch("needs")])
    assemble([needs], None, base=BaseServices(database=db))
    assert db.upgrades == []


def test_migration_failure_fails_only_that_module_and_hides_message() -> None:
    db = RecordingDatabase(fail_on="a")
    a = fake_module("mod-a", migrations=[_branch("a")])
    b = fake_module("mod-b", migrations=[_branch("b")])
    assembly = assemble([a, b], None, base=BaseServices(database=db))
    status = {r.id: r for r in assembly.report}
    assert status["mod-a"].state is ModuleState.FAILED
    assert status["mod-a"].reason == "마이그레이션 실패(RuntimeError)"
    assert "secret" not in (status["mod-a"].reason or "")
    assert status["mod-b"].state is ModuleState.ACTIVE
    assert a.contexts == []  # build 하지 않았다


def test_without_database_module_still_builds() -> None:
    a = fake_module("mod-a", migrations=[_branch("a")])
    assembly = assemble([a], None, base=BaseServices())
    assert assembly.report[0].state is ModuleState.ACTIVE
    assert a.contexts[0].database is None


def _scoped(name: str, *scopes: str) -> MigrationBranch:
    return MigrationBranch(name, Path("/nowhere") / name, scopes=scopes)


def test_default_scope_is_app() -> None:
    assert _branch("a").scopes == ("app",)


def test_empty_scopes_are_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="scopes는 비어 있지 않은"):
        MigrationBranch("a", Path("/x"), scopes=())


def test_host_database_gets_only_app_scoped_branches() -> None:
    db = RecordingDatabase()
    both = fake_module("mod-both", migrations=[_scoped("both", "app", "project")])
    proj = fake_module("mod-proj", migrations=[_scoped("proj", "project")])
    assemble([both, proj], None, base=BaseServices(database=db))
    assert db.upgrades == [["both"]]


def test_active_migrations_lists_enabled_modules_by_scope() -> None:
    both = fake_module("mod-both", migrations=[_scoped("both", "app", "project")])
    proj = fake_module("mod-proj", migrations=[_scoped("proj", "project")])
    app_only = fake_module("mod-app", migrations=[_branch("appb")])
    off = fake_module("mod-off", migrations=[_scoped("off", "project")])
    seen: list[ModuleContext] = []
    spy = fake_module("mod-spy", on_build=lambda ctx: seen.append(ctx))
    assemble(
        [both, proj, app_only, off, spy], ModulesConfig(disabled=["mod-off"]), base=BaseServices()
    )
    ctx = seen[0]
    assert sorted(b.name for b in ctx.active_migrations("project")) == ["both", "proj"]
    assert sorted(b.name for b in ctx.active_migrations("app")) == ["appb", "both"]
    assert ctx.active_migrations("unknown") == ()
