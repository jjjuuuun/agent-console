"""로더 테스트: entry point(주입·테스트 전용 dist-info), 명시 모듈, 플러그인.

실제 설치된 패키지에 의존하지 않는다. 플러그인 모듈은 tmp_path에 만들어 sys.path에 잠시 올린다.
"""

import importlib.metadata
import sys
import textwrap
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from agent_console_registry import (
    LoadReport,
    Registry,
    load_entry_points,
    load_modules,
    load_plugins,
)

PLUGIN_SOURCE = textwrap.dedent(
    """
    class Greeter:
        version = 3

        def greet(self) -> str:
            return "hi"

    greeter = Greeter()
    other = "plain-string"

    class Namespace:
        inner = "nested"

    def explode():
        raise RuntimeError("boom")

    class Plugin:
        def register(self, target):
            target["from_plugin"] = "registered"

    plugin = Plugin()

    def plugin_function(target):
        target["from_function"] = "called"

    class BadPlugin:
        def register(self, target):
            target["partial"] = "yes"
            raise RuntimeError("plugin failed")

    bad_plugin = BadPlugin()
    """
)


@pytest.fixture
def plugin_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """tmp_path에 고유 이름의 플러그인 모듈을 만들고 그 이름을 돌려준다."""
    name = f"acreg_test_plugin_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


def _by_key(reports: list[LoadReport]) -> dict[str | None, LoadReport]:
    return {r.key: r for r in reports}


def _ep(name: str, value: str, group: str = "test.group") -> importlib.metadata.EntryPoint:
    return importlib.metadata.EntryPoint(name=name, value=value, group=group)


# ---------------------------------------------------------------- load_entry_points


def test_entry_points_injected_register_items_and_report_failures(plugin_module: str) -> None:
    reg: Registry[Any] = Registry("test")
    reports = load_entry_points(
        "test.group",
        reg,
        entry_points=[
            _ep("greeter", f"{plugin_module}:greeter"),
            _ep("missing_module", "acreg_definitely_missing_module_xyz:thing"),
            _ep("missing_attr", f"{plugin_module}:no_such_attr"),
        ],
    )
    by_key = _by_key(reports)
    assert by_key["greeter"].status == "loaded"
    assert by_key["greeter"].version == 1
    assert reg.get("greeter").greet() == "hi"
    assert by_key["missing_module"].status == "failed"
    assert "ModuleNotFoundError" in (by_key["missing_module"].error or "")
    assert by_key["missing_attr"].status == "failed"
    assert "AttributeError" in (by_key["missing_attr"].error or "")
    assert not by_key["missing_attr"].ok
    assert [e.key for e in reg.list()] == ["greeter"]


def test_entry_points_enabled_filter_skips_others(plugin_module: str) -> None:
    reg: Registry[Any] = Registry()
    reports = load_entry_points(
        "test.group",
        reg,
        enabled={"greeter"},
        entry_points=[
            _ep("greeter", f"{plugin_module}:greeter"),
            _ep("other", f"{plugin_module}:other"),
        ],
    )
    by_key = _by_key(reports)
    assert by_key["other"].status == "skipped"
    assert by_key["other"].ok
    assert "other" not in reg
    assert "greeter" in reg


def test_entry_points_validate_and_version_of(plugin_module: str) -> None:
    def must_greet(obj: Any) -> Any:
        if not hasattr(obj, "greet"):
            raise TypeError("greet() 없음")
        return obj

    reg: Registry[Any] = Registry()
    reports = load_entry_points(
        "test.group",
        reg,
        validate=must_greet,
        version_of=lambda item: int(item.version),
        entry_points=[
            _ep("greeter", f"{plugin_module}:greeter"),
            _ep("other", f"{plugin_module}:other"),
        ],
    )
    by_key = _by_key(reports)
    assert by_key["greeter"].version == 3
    assert reg.versions("greeter") == [3]
    assert by_key["other"].status == "failed"
    assert "TypeError" in (by_key["other"].error or "")


def test_entry_points_duplicate_with_existing_is_reported_not_raised(plugin_module: str) -> None:
    reg: Registry[Any] = Registry()
    reg.register("greeter", "already", source="manual")
    reports = load_entry_points(
        "test.group", reg, entry_points=[_ep("greeter", f"{plugin_module}:greeter")]
    )
    assert reports[0].status == "failed"
    assert "DuplicateKeyError" in (reports[0].error or "")
    assert reg.get("greeter") == "already"


def test_entry_points_import_time_exception_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = f"acreg_broken_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text("raise RuntimeError('import boom')\n", "utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    reports = load_entry_points(
        "g", Registry[Any](), entry_points=[_ep("broken", f"{name}:x", "g")]
    )
    assert reports[0].status == "failed"
    assert "import boom" in (reports[0].error or "")


def test_entry_points_discovered_from_test_only_dist_info(
    plugin_module: str, tmp_path: Path
) -> None:
    """설치 경로와 같은 방식(dist-info + entry_points.txt)으로 기본 탐색을 확인한다."""
    group = f"acreg.test.{uuid.uuid4().hex}"
    dist_info = tmp_path / "acreg_fake_dist-1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: acreg-fake-dist\nVersion: 1.0\n", "utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{group}]\ngreeter = {plugin_module}:greeter\nnested = {plugin_module}:Namespace.inner\n",
        "utf-8",
    )
    reg: Registry[Any] = Registry()
    reports = load_entry_points(group, reg)
    assert {r.key: r.status for r in reports} == {"greeter": "loaded", "nested": "loaded"}
    assert reg.get("nested") == "nested"
    assert "acreg-fake-dist 1.0" in reports[0].source


def test_entry_points_unknown_group_is_empty() -> None:
    assert load_entry_points(f"acreg.none.{uuid.uuid4().hex}", Registry[Any]()) == []


# ---------------------------------------------------------------- load_modules


def test_load_modules_default_and_explicit_keys(plugin_module: str) -> None:
    reg: Registry[Any] = Registry()
    reports = load_modules(
        [
            f"{plugin_module}:greeter",
            f"custom = {plugin_module}:other",
            f"{plugin_module}:Namespace.inner",
        ],
        reg,
    )
    assert all(r.status == "loaded" for r in reports), reports
    assert reg.get("greeter").greet() == "hi"
    assert reg.get("custom") == "plain-string"
    assert reg.get("inner") == "nested"


def test_load_modules_failures_are_reported(plugin_module: str) -> None:
    reg: Registry[Any] = Registry()
    reports = load_modules(
        [
            "no_colon_here",
            "acreg_definitely_missing_module_xyz:thing",
            f"{plugin_module}:no_such_attr",
            f"{plugin_module}:greeter",
            f"greeter={plugin_module}:other",  # 중복 key
        ],
        reg,
    )
    assert [r.status for r in reports] == ["failed", "failed", "failed", "loaded", "failed"]
    assert reports[0].key is None
    assert "ValueError" in (reports[0].error or "")
    assert "DuplicateKeyError" in (reports[4].error or "")
    assert reg.get("greeter").greet() == "hi"


def test_load_modules_with_injected_importer() -> None:
    fake = ModuleType("virtual_mod")
    fake.thing = "from-fake"  # type: ignore[attr-defined]

    def importer(name: str) -> ModuleType:
        if name == "virtual_mod":
            return fake
        raise ModuleNotFoundError(name)

    reg: Registry[str] = Registry()
    reports = load_modules(["virtual_mod:thing", "other_mod:x"], reg, import_module=importer)
    assert [r.status for r in reports] == ["loaded", "failed"]
    assert reg.get("thing") == "from-fake"


# ---------------------------------------------------------------- load_plugins


def test_load_plugins_calls_register_or_callable_and_reports_errors(plugin_module: str) -> None:
    target: dict[str, str] = {}
    reports = load_plugins(
        [
            f"{plugin_module}:plugin",
            f"{plugin_module}:plugin_function",
            f"{plugin_module}:bad_plugin",
            f"{plugin_module}:other",
            "bad path",
        ],
        target,
    )
    assert [r.status for r in reports] == ["loaded", "loaded", "failed", "failed", "failed"]
    assert "plugin failed" in (reports[2].error or "")
    assert "TypeError" in (reports[3].error or "")
    assert target == {"from_plugin": "registered", "from_function": "called", "partial": "yes"}


# ---------------------------------------------------------------- 회귀 (QA 후속)


@pytest.fixture
def exiting_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """import 중에 sys.exit()를 호출하는 모듈."""
    name = f"acreg_exiting_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text("import sys\nsys.exit(3)\n", "utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


def test_system_exit_during_import_is_reported_by_all_loaders(exiting_module: str) -> None:
    path = f"{exiting_module}:x"
    reports = [
        *load_entry_points("g", Registry[Any](), entry_points=[_ep("exiting", path, "g")]),
        *load_modules([path], Registry[Any]()),
        *load_plugins([path], target={}),
    ]
    assert [r.status for r in reports] == ["failed", "failed", "failed"]
    assert all("SystemExit" in (r.error or "") for r in reports)


def test_system_exit_inside_plugin_register_is_reported() -> None:
    def exiting_register(target: object) -> None:
        sys.exit(1)

    fake = ModuleType("virtual_exit")
    fake.plugin = exiting_register  # type: ignore[attr-defined]
    reports = load_plugins(["virtual_exit:plugin"], target={}, import_module=lambda _: fake)
    assert reports[0].status == "failed"
    assert "SystemExit" in (reports[0].error or "")


def test_keyboard_interrupt_still_propagates() -> None:
    def importer(name: str) -> ModuleType:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        load_modules(["m:x"], Registry[Any](), import_module=importer)
    with pytest.raises(KeyboardInterrupt):
        load_plugins(["m:x"], target={}, import_module=importer)


@pytest.mark.parametrize("path", ["=a:b", " = a:b"])
def test_empty_explicit_key_is_format_error(path: str) -> None:
    calls: list[str] = []

    def importer(name: str) -> ModuleType:
        calls.append(name)
        return ModuleType(name)

    reg: Registry[Any] = Registry()
    module_reports = load_modules([path], reg, import_module=importer)
    plugin_reports = load_plugins([path], target={}, import_module=importer)
    for report in (*module_reports, *plugin_reports):
        assert report.status == "failed"
        assert report.key is None
        assert "ValueError" in (report.error or "")
    assert calls == []
    assert len(reg) == 0


def test_plugin_without_register_and_not_callable_is_reported(plugin_module: str) -> None:
    target: dict[str, str] = {}
    reports = load_plugins([f"{plugin_module}:Namespace.inner"], target)
    assert reports[0].status == "failed"
    assert "TypeError" in (reports[0].error or "")
    assert target == {}
