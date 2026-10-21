"""레지스트리 검사기(H4/D12)와 `load_plugins(enabled=, watch=)` 단위 테스트."""

from types import SimpleNamespace
from typing import Any

import pytest

from agent_console_registry import (
    InvalidExtensionError,
    Registry,
    RegistryError,
    load_entry_points,
    load_plugins,
)


class Thing:
    def __init__(self, name: str = "t") -> None:
        self.name = name


def as_thing(obj: Any) -> Thing:
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, Thing):
        raise TypeError(f"Thing이 아니다: {obj!r}")
    return item


def test_register_runs_validator_and_stores_converted_value() -> None:
    reg: Registry[Thing] = Registry("things", validator=as_thing)
    entry = reg.register("cls", Thing)  # type: ignore[arg-type]  # 클래스 → 인스턴스
    assert isinstance(entry.item, Thing)
    assert reg.validator is as_thing
    with pytest.raises(InvalidExtensionError) as info:
        reg.register("bad", "not a thing")  # type: ignore[arg-type]
    assert isinstance(info.value, TypeError)
    assert "bad" in str(info.value)
    assert "bad" not in reg


def test_rejected_replace_keeps_existing_entry() -> None:
    reg: Registry[Thing] = Registry("things", validator=as_thing)
    good = Thing("good")
    reg.register("a", good)
    with pytest.raises(InvalidExtensionError):
        reg.register("a", object(), replace=True)  # type: ignore[arg-type]
    assert reg.get("a") is good


def test_set_validator_checks_existing_entries() -> None:
    reg: Registry[Any] = Registry("things")
    reg.register("ok", Thing)
    reg.set_validator(as_thing)
    assert isinstance(reg.get("ok"), Thing)
    reg.set_validator(as_thing)  # 같은 검사기는 그대로
    with pytest.raises(RegistryError):
        reg.set_validator(lambda obj: obj)

    loose: Registry[Any] = Registry("loose")
    loose.register("bad", 1)
    with pytest.raises(InvalidExtensionError):
        loose.set_validator(as_thing)
    assert loose.validator is None  # 실패하면 붙지 않는다
    assert loose.get("bad") == 1


def test_unregister_one_version_or_all() -> None:
    reg: Registry[int] = Registry()
    reg.register("a", 1, version=1)
    reg.register("a", 2, version=2)
    reg.unregister("a", 2)
    assert reg.versions("a") == [1]
    reg.unregister("a")
    assert "a" not in reg
    assert len(reg) == 0
    reg.unregister("missing")  # 없으면 아무 일도 없다


def test_entry_point_loader_also_goes_through_registry_validator() -> None:
    reg: Registry[Thing] = Registry("things", validator=as_thing)
    module = SimpleNamespace(good=Thing, bad="nope")
    eps = [
        SimpleNamespace(name="good", value="m:good", load=lambda: module.good),
        SimpleNamespace(name="bad", value="m:bad", load=lambda: module.bad),
    ]
    reports = load_entry_points("g", reg, entry_points=eps)  # type: ignore[arg-type]
    by_key = {r.key: r for r in reports}
    assert by_key["good"].status == "loaded"
    assert by_key["bad"].status == "failed"
    assert "InvalidExtensionError" in (by_key["bad"].error or "")


def _plugin_importer(**plugins: Any) -> Any:
    module = SimpleNamespace(**plugins)
    return lambda name: module


def test_plugin_registering_invalid_object_is_reported_failed() -> None:
    reg: Registry[Thing] = Registry("things", validator=as_thing)

    def plugin(target: Registry[Thing]) -> None:
        target.register("ok", Thing())
        target.register("broken", object())  # type: ignore[arg-type]

    reports = load_plugins(["m:plugin"], reg, import_module=_plugin_importer(plugin=plugin))
    assert [r.status for r in reports] == ["failed"]
    assert "InvalidExtensionError" in (reports[0].error or "")
    assert "broken" not in reg
    assert "ok" in reg  # 실패 전에 등록한 항목은 남는다(문서화된 동작)


def test_plugin_enabled_filter_unregisters_and_reports_disabled() -> None:
    a: Registry[Thing] = Registry("a", validator=as_thing)
    b: Registry[Thing] = Registry("b", validator=as_thing)
    original = Thing("original")
    b.register("shared", original)
    target = SimpleNamespace(a=a, b=b)

    def plugin(t: Any) -> None:
        t.a.register("on", Thing())
        t.a.register("off", Thing())
        t.b.register("shared", Thing("override"), replace=True)

    reports = load_plugins(
        ["m:plugin"],
        target,
        enabled={"on"},
        watch=lambda: [a, b],
        import_module=_plugin_importer(plugin=plugin),
    )
    statuses = sorted((r.status, r.key) for r in reports)
    assert statuses == [("disabled", "off"), ("disabled", "shared"), ("loaded", "plugin")]
    assert all(r.ok for r in reports)
    assert "on" in a
    assert "off" not in a
    assert b.get("shared") is original  # 덮어쓴 항목은 원래대로
    disabled = next(r for r in reports if r.key == "off")
    assert disabled.source == "plugin m:plugin -> a:off"


def test_plugin_enabled_requires_watch() -> None:
    with pytest.raises(ValueError, match="watch"):
        load_plugins(["m:x"], object(), enabled={"x"})


def test_plugin_enabled_none_keeps_everything() -> None:
    reg: Registry[Thing] = Registry("things", validator=as_thing)
    reports = load_plugins(
        ["m:plugin"],
        reg,
        watch=lambda: [reg],
        import_module=_plugin_importer(plugin=lambda t: t.register("x", Thing())),
    )
    assert [r.status for r in reports] == ["loaded"]
    assert "x" in reg
