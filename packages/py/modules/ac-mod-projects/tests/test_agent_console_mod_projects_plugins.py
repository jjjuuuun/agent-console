"""폴더 선택 창 제공자 플러그인 로더(X35): ``plugins.enabled``·``plugins.disabled``를 따른다."""

from __future__ import annotations

import sys
import textwrap
import uuid
from collections.abc import Iterator, Mapping, Sequence
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_local_folders import CancelSignal, CommandOutcome
from agent_console_mod_projects import (
    FOLDER_DIALOGS_EXTENSION,
    FOLDER_DIALOGS_GROUP,
    ProjectsModule,
    as_folder_dialog_provider,
)
from agent_console_mod_projects.plugins import load_plugins
from agent_console_modkit import (
    BaseServices,
    ExtensionRegistries,
    ModulesConfig,
    Paths,
    PluginLoadContext,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app

TOKEN = "t" * 32
API = "/api/v1"

PROVIDERS = textwrap.dedent(
    """
    class Keep:
        id = "keep"

        def available(self, environ):
            return True

        def pick(self, *, initial, title, timeout, cancel):
            return "/picked"

    class Drop(Keep):
        id = "drop"

    not_a_provider = object()
    """
)


@pytest.fixture
def providers_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    name = f"acmp_dialogs_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(PROVIDERS, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


def _eps(module: str) -> list[EntryPoint]:
    return [
        EntryPoint(name="keep", value=f"{module}:Keep", group=FOLDER_DIALOGS_GROUP),
        EntryPoint(name="drop", value=f"{module}:Drop", group=FOLDER_DIALOGS_GROUP),
        EntryPoint(name="bad", value=f"{module}:not_a_provider", group=FOLDER_DIALOGS_GROUP),
        EntryPoint(name="other", value=f"{module}:Keep", group="other.group"),
    ]


def test_loader_reads_group_into_bundle(providers_module: str) -> None:
    bundle = ExtensionRegistries()
    ctx = PluginLoadContext(registries=bundle)
    reports = load_plugins(ctx, entry_points=_eps(providers_module))
    status = {r.key: r.status for _, r in reports}
    assert status == {"bad": "failed", "drop": "loaded", "keep": "loaded"}
    assert {g for g, _ in reports} == {FOLDER_DIALOGS_EXTENSION}
    registry = bundle.extension(FOLDER_DIALOGS_EXTENSION)
    assert registry.get("keep").id == "keep"  # 클래스는 인스턴스로 만든다


def test_loader_follows_effective_enabled(providers_module: str) -> None:
    """호스트가 ``plugins.disabled``를 뺀 결과(``ctx.enabled``)를 다른 그룹과 똑같이 따른다."""
    bundle = ExtensionRegistries()
    ctx = PluginLoadContext(
        registries=bundle,
        enabled=frozenset({"keep", "bad"}),
        disabled=frozenset({"drop"}),
        allow_unlisted=True,
    )
    reports = load_plugins(ctx, entry_points=_eps(providers_module))
    status = {r.key: r.status for _, r in reports}
    assert status["drop"] == "skipped"
    assert "drop" not in bundle.extension(FOLDER_DIALOGS_EXTENSION)
    assert "keep" in bundle.extension(FOLDER_DIALOGS_EXTENSION)


def test_loader_without_bundle_extension_reports_nothing() -> None:
    assert load_plugins(PluginLoadContext(registries=object())) == []


def test_as_folder_dialog_provider_rejects_wrong_shape() -> None:
    with pytest.raises(TypeError):
        as_folder_dialog_provider(object())


class _Runner:
    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
        cancel: CancelSignal | None = None,
    ) -> CommandOutcome:
        return CommandOutcome(1)


def _pick(tmp_path: Path, registries: object | None) -> dict[str, object]:
    mod = ProjectsModule(runner=_Runner(), platform="linux", which=lambda _n: None)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
    )
    assembly = assemble([mod], ModulesConfig(), base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        body: dict[str, object] = client.post(f"{API}/projects/folders/pick", json={}).json()
    return body


def test_module_uses_providers_from_bundle(tmp_path: Path, providers_module: str) -> None:
    bundle = ExtensionRegistries()
    load_plugins(
        PluginLoadContext(registries=bundle, enabled=frozenset({"keep"})),
        entry_points=_eps(providers_module),
    )
    body = _pick(tmp_path, bundle)
    assert body.get("provider") == "keep"


def test_module_skips_disabled_provider(tmp_path: Path, providers_module: str) -> None:
    bundle = ExtensionRegistries()
    load_plugins(
        PluginLoadContext(registries=bundle, enabled=frozenset()),
        entry_points=_eps(providers_module),
    )
    body = _pick(tmp_path, bundle)
    assert body.get("provider") != "keep"
