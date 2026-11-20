"""mod-memory 자동 정리 한 주기(5.7R.46): 대상 고르기(``retention.auto``)·공간마다 실패
건너뜀·제공자 선택 메서드 ``existing()``이 없으면 공용만. 공간 제공자는 테스트 안의 가짜(프로세스
메모리 저장소)다."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_conditions import default_operators
from agent_console_contracts import ErrorCodes
from agent_console_contracts.memory import MemoryScopeRef, MemoryWriteRequest
from agent_console_memory import InMemoryMemoryStore, MemoryStore
from agent_console_mod_memory import (
    MEMORY_SERVICE,
    MEMORY_SPACES,
    MemoryService,
    MemorySpaceServices,
    parse_memory_settings,
    retention_targets,
    run_retention_cycle,
)
from agent_console_modkit import Assembly, Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

NOTES = MemoryScopeRef(kind="notes", id="")
RULE = {
    "id": "temp",
    "when": {"all": [{"path": "/tags", "op": "contains", "value": "임시"}]},
    "action": "delete",
}


def _section(auto: dict[str, Any] | None = None, rules: bool = True) -> dict[str, Any]:
    retention: dict[str, Any] = {"rules": [RULE] if rules else []}
    if auto is not None:
        retention["auto"] = auto
    return {
        "include_default_scope_kinds": False,
        "scope_kinds": {"notes": {"label": "노트", "id": ""}},
        "retention": retention,
    }


@dataclass
class _Space:
    store: MemoryStore
    context: Mapping[str, str] = field(default_factory=dict)


class _GoneError(Exception):
    code = ErrorCodes.PROJECT_FOLDER_MISSING


@dataclass
class _Spaces:
    spaces: dict[str, _Space]
    names: list[str] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)

    def open(self, space: str) -> _Space:
        self.opened.append(space)
        if space not in self.spaces:
            raise _GoneError("폴더 없음")
        return self.spaces[space]

    def existing(self) -> list[str]:
        return list(self.names)


class _NoListing:
    def __init__(self, spaces: _Spaces) -> None:
        self.inner = spaces

    def open(self, space: str) -> _Space:
        return self.inner.open(space)


def _library(provider: Any, section: dict[str, Any]) -> MemoryService:
    operators, _ = default_operators()

    def make(store: MemoryStore, context: Mapping[str, str] | None = None) -> MemoryService:
        return MemoryService(
            store,
            section=lambda: section,
            operators=lambda: operators,
            context_overrides=context,
            spaces=spaces_ref[0] if spaces_ref else None,
        )

    spaces_ref: list[MemorySpaceServices] = []
    spaces = MemorySpaceServices(lambda: provider, make)
    spaces_ref.append(spaces)
    library = make(InMemoryMemoryStore())
    spaces.library = library
    return library


def _temp(service: MemoryService) -> str:
    request = MemoryWriteRequest(scope=NOTES, key="t", content="x", tags=["임시"])
    return service.create(request).id


def _deleted(store: MemoryStore, entry_id: str) -> bool:
    found = store.get(entry_id, include_deleted=True)
    return found is not None and found.deleted_at is not None


def _provider(*names: str) -> _Spaces:
    return _Spaces({n: _Space(InMemoryMemoryStore()) for n in ("a", "b")}, list(names))


def test_cycle_order_library_then_existing_and_failures_skipped() -> None:
    provider = _provider("gone", "a", "a", "b")
    library = _library(provider, _section())
    ids = {name: _temp(library.space(name or None)) for name in ("", "a", "b")}
    provider.opened.clear()
    result = run_retention_cycle(library)
    assert list(result.results) == [None, "a", "b"]  # 같은 이름은 한 번, 순서 그대로
    assert result.failed == {"gone": ErrorCodes.PROJECT_FOLDER_MISSING}
    assert _deleted(library.store, ids[""])
    assert all(_deleted(provider.spaces[n].store, ids[n]) for n in ("a", "b"))
    for name in ("a", "b"):
        version = library.space(name).versions(ids[name])[-1]
        assert (version.author.kind, version.author.label) == ("system", "temp")


def test_apply_failure_in_one_space_continues(monkeypatch: Any) -> None:
    provider = _provider("a", "b")
    library = _library(provider, _section())
    b_entry = _temp(library.space("b"))

    def broken() -> Any:
        raise OSError("잠김")

    monkeypatch.setattr(library.space("a"), "apply_retention", broken)
    result = run_retention_cycle(library)
    assert list(result.results) == [None, "b"]
    assert result.failed == {"a": "OSError"}
    assert _deleted(provider.spaces["b"].store, b_entry)


def test_targets_follow_auto_setting() -> None:
    provider = _provider("a", "b")
    library = _library(provider, _section())

    def targets(auto: dict[str, Any]) -> list[str | None]:
        settings, issues = parse_memory_settings({"retention": {"auto": auto}})
        assert issues == []
        return retention_targets(library, settings.retention.auto)

    assert targets({}) == [None, "a", "b"]
    assert targets({"projects": False}) == [None]
    assert targets({"exclude_projects": ["b"]}) == [None, "a"]
    assert targets({"library": False}) == ["a", "b"]


def test_no_rules_opens_nothing() -> None:
    provider = _provider("a")
    library = _library(provider, _section(rules=False))
    entry = _temp(library.space("a"))
    provider.opened.clear()
    assert run_retention_cycle(library).results == {}
    assert provider.opened == []
    assert not _deleted(provider.spaces["a"].store, entry)


def test_provider_without_existing_or_broken_is_library_only() -> None:
    no_listing = _library(_NoListing(_provider("a")), _section())
    assert list(run_retention_cycle(no_listing).results) == [None]

    class _Broken(_Spaces):
        def existing(self) -> list[str]:
            raise RuntimeError("목록 실패")

    broken = _library(_Broken({}), _section())
    assert list(run_retention_cycle(broken).results) == [None]
    alone = MemoryService(InMemoryMemoryStore(), section=lambda: _section())
    assert alone.existing_spaces() == []


def test_module_uses_spaces_existing(make_assembly: Callable[..., Assembly]) -> None:
    provider = _provider("a")

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(MEMORY_SPACES, provider)
        return ModuleParts()

    extra: list[Module] = [fake_module("memory-spaces", provides=(MEMORY_SPACES,), on_build=build)]
    assembly = make_assembly(settings={"memory": _section()}, extra=extra)
    service = assembly.port(MEMORY_SERVICE)
    assert isinstance(service, MemoryService)
    entry = _temp(service.space("a"))
    assert service.existing_spaces() == ["a"]
    run_retention_cycle(service)
    assert _deleted(provider.spaces["a"].store, entry)


def test_auto_parse_keeps_valid_fields_and_rules() -> None:
    settings, issues = parse_memory_settings(
        {"retention": {"rules": [RULE], "auto": {"projects": False, "library": [1]}}}
    )
    assert settings.retention.auto.projects is False
    assert settings.retention.auto.library is True
    assert len(settings.retention.rules) == 1
    assert [i.path for i in issues] == ["/memory/retention/auto/library"]
    _, issues = parse_memory_settings({"retention": {"auto": "전부"}})
    assert [i.path for i in issues] == ["/memory/retention/auto"]
    settings, issues = parse_memory_settings({"retention": {"auto": None}})
    assert issues == []
    assert settings.retention.auto.library is True


# ---- 멈춤(11/20 서버 종료와 겹칠 때) --------------------------------------------


def test_should_stop_skips_remaining_targets() -> None:
    """멈춤 요청이면 남은 저장소를 열지도 정리하지도 않고 ``stopped``로 끝난다."""
    provider = _provider("a", "b")
    library = _library(provider, _section())
    ids = {name: _temp(library.space(name or None)) for name in ("", "a", "b")}
    provider.opened.clear()
    asked: list[int] = []

    def should_stop() -> bool:
        asked.append(1)
        return len(asked) > 1  # 공용만 하고 멈춘다

    result = run_retention_cycle(library, should_stop=should_stop)
    assert list(result.results) == [None]
    assert result.stopped
    assert result.failed == {}
    assert provider.opened == []
    assert not any(_deleted(provider.spaces[n].store, ids[n]) for n in ("a", "b"))


def test_periodic_cancel_waits_for_running_space_and_stops_the_rest(monkeypatch: Any) -> None:
    """배경 작업이 취소되면(서버 종료) 하던 공간이 끝날 때까지 기다리고, 남은 공간은 하지 않는다.

    조립기는 종료 훅(공간 풀·저장소 닫기)보다 배경 작업 취소를 먼저 하므로, 정리 스레드가 닫힌
    저장소를 쓰지 않는다.
    """
    import asyncio
    import threading

    from agent_console_mod_memory.module import run_retention_periodically
    from agent_console_modkit import WorkGate

    provider = _provider("a", "b")
    library = _library(provider, _section())
    b_entry = _temp(library.space("b"))
    space_a = library.space("a")
    entered = threading.Event()
    release = threading.Event()
    real = space_a.apply_retention

    def slow() -> Any:
        entered.set()
        assert release.wait(5)
        return real()

    monkeypatch.setattr(space_a, "apply_retention", slow)
    gate = WorkGate()

    async def scenario() -> None:
        task = asyncio.create_task(run_retention_periodically(library, 0.01, gate=gate))
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0.1)
        assert not task.done()  # 하던 공간이 끝나기 전에는 끝나지 않는다
        release.set()
        try:
            await asyncio.wait_for(task, 5)
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - 취소가 전달되어야 한다
            raise AssertionError("취소가 다시 던져지지 않았다")

    asyncio.run(scenario())
    assert gate.closed
    assert gate.busy == 0
    assert not _deleted(provider.spaces["b"].store, b_entry)  # 남은 공간은 하지 않았다
