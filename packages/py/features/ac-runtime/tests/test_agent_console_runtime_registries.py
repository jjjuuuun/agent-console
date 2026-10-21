"""레지스트리 묶음의 등록 검사(H4/D12)·`plugins.modules` 경로·세션 변환(design §2R.1)."""

from __future__ import annotations

import types
from typing import Any

import pytest

from agent_console_contracts import SessionRef as ContractSessionRef
from agent_console_registry import InvalidExtensionError, RegistryError
from agent_console_runtime import (
    EnvSecretProvider,
    Registries,
    SessionRef,
    load_registry_plugins,
    session_refs,
)


class Classifier:
    def classify(self, text: str) -> str:
        return text


def as_classifier(obj: Any) -> Classifier:
    item = obj() if isinstance(obj, type) else obj
    if not isinstance(item, Classifier):
        raise TypeError(f"classifier가 아니다: {obj!r}")
    return item


def _module(**attrs: Any) -> Any:
    module = types.ModuleType("fake_registry_plugin")
    for name, value in attrs.items():
        setattr(module, name, value)
    return lambda _name: module


def test_builtin_registries_validate_every_register_call() -> None:
    regs = Registries()
    for registry in (
        regs.node_types,
        regs.edge_types,
        regs.backends,
        regs.secret_providers,
        regs.delegation_strategies,
        regs.interaction_kinds,
    ):
        with pytest.raises(InvalidExtensionError):
            registry.register("bad", object())  # type: ignore[arg-type]
    regs.secret_providers.register("env", EnvSecretProvider({}))
    assert "env" in regs.secret_providers


def test_extension_validator_attached_on_create_or_later() -> None:
    regs = Registries()
    created = regs.extension("classifiers", validator=as_classifier)
    assert created.validator is as_classifier
    assert isinstance(created.register("cls", Classifier).item, Classifier)

    later = regs.extension("later")
    later.register("ok", Classifier())
    assert regs.extension("later", validator=as_classifier) is later
    with pytest.raises(InvalidExtensionError):
        later.register("bad", "x")
    with pytest.raises(RegistryError):
        regs.extension("later", validator=lambda o: o)
    assert regs.all()[-2:] == [created, later]


def test_plugin_registering_invalid_object_is_reported_failed() -> None:
    regs = Registries()
    regs.extension("classifiers", validator=as_classifier)

    def plugin(target: Registries) -> None:
        target.extension("classifiers").register("broken", 42)

    def bad_node(target: Registries) -> None:
        target.node_types.register("fake", object())  # type: ignore[arg-type]

    reports = load_registry_plugins(
        ["m:plugin", "m:bad_node"], regs, import_module=_module(plugin=plugin, bad_node=bad_node)
    )
    assert [r.status for r in reports] == ["failed", "failed"]
    assert all("InvalidExtensionError" in (r.error or "") for r in reports)
    assert "broken" not in regs.extension("classifiers")
    assert "fake" not in regs.node_types


def test_plugin_enabled_filter_disables_unlisted_keys() -> None:
    regs = Registries()
    regs.extension("classifiers", validator=as_classifier)

    def plugin(target: Registries) -> None:
        target.extension("classifiers").register("keep", Classifier())
        target.extension("classifiers").register("drop", Classifier())
        target.extension("brand_new").register("also_drop", object())

    reports = load_registry_plugins(
        ["m:plugin"], regs, enabled={"keep"}, import_module=_module(plugin=plugin)
    )
    by_key = {r.key: r.status for r in reports}
    assert by_key == {"plugin": "loaded", "drop": "disabled", "also_drop": "disabled"}
    assert "keep" in regs.extension("classifiers")
    assert "drop" not in regs.extension("classifiers")
    assert "also_drop" not in regs.extension("brand_new")


def test_session_refs_converts_contract_to_engine_model() -> None:
    contract = {"lead": ContractSessionRef(backend="b", session_id="s1", data={"k": 1})}
    converted = session_refs(contract)
    assert converted == {"lead": SessionRef(backend="b", session_id="s1", data={"k": 1})}
    converted["lead"].data["k"] = 2
    assert contract["lead"].data == {"k": 1}  # 원본과 공유하지 않는다
    assert session_refs({}) == {}
