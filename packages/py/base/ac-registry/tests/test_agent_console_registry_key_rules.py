"""같은 key를 두 플러그인이 등록할 때의 규칙(문서 "플러그인 공통 - 이름과 중복"과 같은 내용).

1. 한 레지스트리에서 key는 ``(key, version)``으로 하나다. 같은 것이 또 오면 뒤의 것이 ``failed``
   (``DuplicateKeyError``, 메시지에 먼저 등록한 출처)이고 먼저 것이 남는다.
2. entry point는 ``(이름, 값)`` 순으로 읽는다. 같은 그룹에 같은 이름이 둘이면 값(모듈 경로)이 앞서는
   쪽이 이긴다 — 넘긴 순서(설치 순서)와 상관없다. 기본 구현도 entry point라 같은 규칙을 따른다.
3. 버전이 다르면 함께 남고, 버전 없이 조회하면 최신이다.
4. 레지스트리(그룹)가 다르면 같은 key도 서로 상관없다.
5. ``register(target)`` 플러그인이 이미 있는 key를 등록하면 그 플러그인이 ``failed``이고 먼저 것이
   남는다. 덮어쓰기는 ``register(..., replace=True)``로 명시할 때만이다. 덮어쓴 key가 ``disabled``로
   빠지면 원래 항목이 되살아난다.
"""

from __future__ import annotations

import importlib.metadata
import sys
from types import ModuleType
from typing import Any

import pytest

from agent_console_registry import Registry, load_entry_points, load_plugins

GROUP = "test.rules"


def _ep(name: str, value: str, group: str = GROUP) -> importlib.metadata.EntryPoint:
    return importlib.metadata.EntryPoint(name=name, value=value, group=group)


def _modules(**attrs: Any) -> dict[str, ModuleType]:
    """``{"모듈 이름": 모듈}`` — 인자 이름 ``모듈__속성``이 그 모듈의 속성이 된다."""
    out: dict[str, ModuleType] = {}
    for path, value in attrs.items():
        module_name, _, attr = path.partition("__")
        module = out.setdefault(module_name, ModuleType(module_name))
        setattr(module, attr, value)
    return out


@pytest.fixture
def fake_modules(monkeypatch: pytest.MonkeyPatch) -> dict[str, ModuleType]:
    """``load()``가 찾을 가짜 모듈(기본 구현 ``aaa_default``·플러그인 ``zzz_plugin``)."""
    mods = _modules(aaa_default__relay="default relay", zzz_plugin__relay="plugin relay")
    for name, module in mods.items():
        monkeypatch.setitem(sys.modules, name, module)
    return mods


@pytest.mark.parametrize("order", ["default-first", "plugin-first"])
def test_same_name_same_group_first_value_wins_regardless_of_order(
    fake_modules: dict[str, ModuleType], order: str
) -> None:
    eps = [_ep("relay", "aaa_default:relay"), _ep("relay", "zzz_plugin:relay")]
    if order == "plugin-first":
        eps.reverse()
    registry: Registry[Any] = Registry("rules")
    reports = load_entry_points(GROUP, registry, entry_points=eps)
    assert [(r.key, r.status) for r in reports] == [("relay", "loaded"), ("relay", "failed")]
    assert registry.get("relay") == "default relay"
    assert "aaa_default:relay" in registry.get_entry("relay").source
    loser = reports[1]
    assert "zzz_plugin:relay" in loser.source
    assert loser.error is not None
    assert "DuplicateKeyError" in loser.error
    assert "aaa_default:relay" in loser.error  # 누가 먼저 가졌는지 보인다


def test_value_order_decides_even_when_plugin_sorts_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기본 구현도 특별하지 않다: 플러그인 값이 앞서면 플러그인이 이기고 기본 구현이 실패."""
    mods = _modules(acme__relay="acme relay", agent_console_x__relay="default relay")
    for name, module in mods.items():
        monkeypatch.setitem(sys.modules, name, module)
    registry: Registry[Any] = Registry("rules")
    reports = load_entry_points(
        GROUP,
        registry,
        entry_points=[_ep("relay", "agent_console_x:relay"), _ep("relay", "acme:relay")],
    )
    assert [(r.source.split()[-1], r.status) for r in reports] == [
        ("(acme:relay)", "loaded"),
        ("(agent_console_x:relay)", "failed"),
    ]
    assert registry.get("relay") == "acme relay"


def test_different_versions_coexist_and_latest_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    class V1:
        version = 1

    class V2:
        version = 2

    mods = _modules(v_one__item=V1(), v_two__item=V2())
    for name, module in mods.items():
        monkeypatch.setitem(sys.modules, name, module)
    registry: Registry[Any] = Registry("rules")
    reports = load_entry_points(
        GROUP,
        registry,
        entry_points=[_ep("item", "v_two:item"), _ep("item", "v_one:item")],
        version_of=lambda obj: int(obj.version),
    )
    assert [(r.status, r.version) for r in reports] == [("loaded", 1), ("loaded", 2)]
    assert registry.versions("item") == [1, 2]
    assert registry.get("item").version == 2
    assert registry.get("item", 1).version == 1


def test_same_key_in_other_registry_is_independent(fake_modules: dict[str, ModuleType]) -> None:
    alpha: Registry[Any] = Registry("alpha")
    beta: Registry[Any] = Registry("beta")
    a = load_entry_points(
        "g.alpha", alpha, entry_points=[_ep("relay", "aaa_default:relay", "g.alpha")]
    )
    b = load_entry_points("g.beta", beta, entry_points=[_ep("relay", "zzz_plugin:relay", "g.beta")])
    assert [r.status for r in (*a, *b)] == ["loaded", "loaded"]
    assert (alpha.get("relay"), beta.get("relay")) == ("default relay", "plugin relay")


def _plugin_modules(replace: bool) -> dict[str, ModuleType]:
    def register(target: Registry[Any]) -> None:
        target.register("relay", "from plugin", source="plugin", replace=replace)

    return _modules(local_plugin__plugin=register)


@pytest.mark.parametrize("replace", [False, True])
def test_register_plugin_after_entry_points(replace: bool) -> None:
    registry: Registry[Any] = Registry("rules")
    registry.register("relay", "from entry point", source="entry_point test.rules:relay")
    mods = _plugin_modules(replace)
    reports = load_plugins(["local_plugin:plugin"], registry, import_module=mods.__getitem__)
    if replace:  # 명시적 덮어쓰기만 바꾼다
        assert [r.status for r in reports] == ["loaded"]
        assert registry.get("relay") == "from plugin"
    else:
        assert [r.status for r in reports] == ["failed"]
        assert "DuplicateKeyError" in (reports[0].error or "")
        assert registry.get("relay") == "from entry point"


def test_replaced_key_that_is_disabled_restores_original() -> None:
    registry: Registry[Any] = Registry("rules")
    registry.register("relay", "from entry point", source="entry_point test.rules:relay")
    mods = _plugin_modules(replace=True)
    reports = load_plugins(
        ["local_plugin:plugin"],
        registry,
        disabled={"relay"},
        watch=lambda: [registry],
        import_module=mods.__getitem__,
    )
    assert [(r.key, r.status) for r in reports] == [("plugin", "loaded"), ("relay", "disabled")]
    entry = registry.get_entry("relay")
    assert (entry.item, entry.source) == ("from entry point", "entry_point test.rules:relay")
