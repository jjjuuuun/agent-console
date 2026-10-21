"""호스트 DB 핸들: 켜진 모듈의 마이그레이션 계보만 올린다(design §3R.1.7)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent_console_modkit import (
    BaseServices,
    DatabaseHandle,
    MigrationBranch,
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
