"""`plugins.modules`(설치하지 않은 로컬 모듈)로 runtime 밖 확장 지점도 등록한다(1R.26 개선).

`register(registries)` 플러그인이 `registries.extension(<이름>)`으로 사용량 출처(X13)와
가져오기 출처 공장(X14)을 등록하면 entry point로 등록한 것과 똑같이 API에 나타난다.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agent_console_server.testing import API, make_settings, server

_PLUGIN = """
from agent_console_contracts import ImportSourceDescriptor
from agent_console_imports import IMPORT_SOURCES_EXTENSION, ScanResult
from agent_console_usage import USAGE_SOURCES_EXTENSION, FakeUsageSource, as_usage_source


class _LocalUsage(FakeUsageSource):
    descriptor = FakeUsageSource.descriptor.model_copy(
        update={"id": "local-usage", "title": "로컬 사용량"}
    )


class _LocalImport:
    descriptor = ImportSourceDescriptor(id="local-import", title="로컬 가져오기")

    def scan(self):
        return ScanResult(root=None)


def register(registries):
    registries.extension(USAGE_SOURCES_EXTENSION).register(
        "local-usage", as_usage_source(_LocalUsage), source="module"
    )
    registries.extension(IMPORT_SOURCES_EXTENSION).register(
        "local-import", lambda ctx: [_LocalImport()], source="module"
    )
"""


def test_module_plugin_registers_usage_and_import_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "ac_server_test_module_plugin.py").write_text(
        textwrap.dedent(_PLUGIN), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(plugin_dir))
    settings = make_settings(
        tmp_path, plugins={"modules": ["ac_server_test_module_plugin:register"]}
    )
    with server(settings) as client:
        usage_ids = {s["descriptor"]["id"] for s in client.get(f"{API}/usage/sources").json()}
        assert "local-usage" in usage_ids
        import_ids = {s["id"] for s in client.get(f"{API}/resources/import/sources").json()}
        assert "local-import" in import_ids


_BAD_PLUGIN = """
from agent_console_usage import USAGE_SOURCES_EXTENSION


def register(registries):
    # 사용량 출처가 아닌 객체: 레지스트리 검사기가 거부해야 한다(H4/D12)
    registries.extension(USAGE_SOURCES_EXTENSION).register("not-a-source", object())
"""


def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, code: str) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(code), encoding="utf-8")
    monkeypatch.syspath_prepend(str(plugin_dir))


def _plugins(client: object) -> list[dict[str, object]]:
    info = client.get(f"{API}/server-info").json()  # type: ignore[attr-defined]
    plugins: list[dict[str, object]] = info["plugins"]
    return plugins


def test_module_plugin_with_invalid_object_is_reported_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, monkeypatch, "ac_server_test_bad_plugin", _BAD_PLUGIN)
    settings = make_settings(tmp_path, plugins={"modules": ["ac_server_test_bad_plugin:register"]})
    with server(settings) as client:
        mine = [p for p in _plugins(client) if p["group"] == "plugins.modules"]
        assert len(mine) == 1
        assert mine[0]["loaded"] is False
        error = mine[0]["error"]
        assert isinstance(error, dict)
        assert error["code"] == "plugin_load_failed"
        assert "InvalidExtensionError" in str(error["message"])
        usage_ids = {s["descriptor"]["id"] for s in client.get(f"{API}/usage/sources").json()}
        assert "not-a-source" not in usage_ids


def test_module_plugin_respects_plugins_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, monkeypatch, "ac_server_test_module_plugin", _PLUGIN)
    settings = make_settings(
        tmp_path,
        plugins={
            "modules": ["ac_server_test_module_plugin:register"],
            "enabled": ["local-usage"],  # local-import는 꺼짐
        },
    )
    with server(settings) as client:
        mine = {p["name"]: p for p in _plugins(client) if p["group"] == "plugins.modules"}
        assert mine["register"]["loaded"] is True
        assert mine["local-import"]["loaded"] is False
        assert mine["local-import"]["error"] is None  # 꺼진 것은 오류가 아니다
        usage_ids = {s["descriptor"]["id"] for s in client.get(f"{API}/usage/sources").json()}
        assert "local-usage" in usage_ids
        import_ids = {s["id"] for s in client.get(f"{API}/resources/import/sources").json()}
        assert "local-import" not in import_ids
