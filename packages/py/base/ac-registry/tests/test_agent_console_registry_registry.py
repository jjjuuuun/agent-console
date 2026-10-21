"""Registry[T] 단위 테스트: 등록·조회·목록·버전·중복·전역 상태 없음."""

import pytest

from agent_console_registry import (
    DuplicateKeyError,
    Registry,
    RegistryError,
    UnknownExtensionError,
)


def test_register_and_get_returns_item() -> None:
    reg: Registry[str] = Registry("things")
    entry = reg.register("a", "A", source="test")
    assert reg.get("a") == "A"
    assert entry.key == "a"
    assert entry.version == 1
    assert entry.source == "test"
    assert "a" in reg
    assert len(reg) == 1


def test_get_without_version_returns_latest_and_versions_listed() -> None:
    reg: Registry[str] = Registry()
    reg.register("a", "v2", version=2)
    reg.register("a", "v1", version=1)
    assert reg.get("a") == "v2"
    assert reg.get("a", version=1) == "v1"
    assert reg.versions("a") == [1, 2]
    assert reg.versions("missing") == []


def test_list_is_sorted_latest_only_by_default() -> None:
    reg: Registry[int] = Registry()
    reg.register("b", 1)
    reg.register("a", 10, version=1)
    reg.register("a", 20, version=2)
    assert [(e.key, e.version, e.item) for e in reg.list()] == [("a", 2, 20), ("b", 1, 1)]
    assert [(e.key, e.version) for e in reg.list(all_versions=True)] == [
        ("a", 1),
        ("a", 2),
        ("b", 1),
    ]


def test_duplicate_key_and_version_raises() -> None:
    reg: Registry[str] = Registry("node_kinds")
    reg.register("a", "first", source="src-1")
    with pytest.raises(DuplicateKeyError) as info:
        reg.register("a", "second")
    assert info.value.key == "a"
    assert info.value.existing_source == "src-1"
    assert "node_kinds" in str(info.value)
    assert reg.get("a") == "first"


def test_duplicate_allowed_only_with_explicit_replace() -> None:
    reg: Registry[str] = Registry()
    reg.register("a", "first")
    reg.register("a", "second", replace=True)
    assert reg.get("a") == "second"


def test_unknown_key_or_version_raises_unknown_extension_which_is_key_error() -> None:
    reg: Registry[str] = Registry("x")
    reg.register("a", "A")
    with pytest.raises(UnknownExtensionError, match="'nope'"):
        reg.get("nope")
    with pytest.raises(KeyError):
        reg.get("a", version=9)
    with pytest.raises(RegistryError):
        reg.get("nope")


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError, match="key"):
        Registry[str]().register("", "x")


def test_registries_are_independent_no_global_state() -> None:
    first: Registry[str] = Registry("same-name")
    second: Registry[str] = Registry("same-name")
    first.register("a", "A")
    assert "a" not in second
    assert second.list() == []


def test_list_returns_copy() -> None:
    reg: Registry[str] = Registry()
    reg.register("a", "A")
    reg.list().clear()
    assert len(reg.list()) == 1
