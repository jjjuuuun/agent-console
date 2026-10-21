"""5.2R.29 모듈 옵션 읽기 전용 조회(`GET /modules/{id}/options`).

스키마·가린 값·YAML 조각, 쓰기 없음. 기준 모듈 목록은 설치된 모듈(entry point)에서 만든다
(고정 목록 없음). 비밀 미노출은 예제 모듈로 본다.
"""

from __future__ import annotations

import io
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, SecretStr
from ruamel.yaml import YAML

from agent_console_contracts import X_UI, ModuleInfo, ModuleOptionsView
from agent_console_modkit import (
    OPTIONS_MASK,
    Module,
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
    assemble,
)
from agent_console_server import create_app, installed_modules
from agent_console_server.testing import API, TEST_TOKEN, default_environ, make_settings

EXAMPLE_ID = "mod-options-example"
PLAIN_KEY = "sk-live-abcdef1234567890"
PLAIN_TOKEN = "plain-token-value-123456"
PLAIN_NOTE = "Bearer abcdefghijklmnop1234"


class _ExampleOptions(BaseModel):
    limit: int = 3
    token: SecretStr | None = None
    env: dict[str, str] = Field(default_factory=dict)
    note: str = ""
    folder: Path | None = None


class _ExampleModule:
    descriptor = ModuleDescriptor(
        id=EXAMPLE_ID,
        version="0.0.1",
        kind="feature",
        title="옵션 예제",
        settings_schema=_ExampleOptions,
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        return ModuleParts()


def _client(
    tmp_path: Path,
    *,
    options: Mapping[str, Mapping[str, Any]] | None = None,
    **extra: Any,
) -> Iterator[TestClient]:
    settings = make_settings(tmp_path, options=options, **extra)
    modules: list[Module] = [*installed_modules(), _ExampleModule()]
    app = create_app(settings, environ=default_environ(), token=TEST_TOKEN, modules=modules)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TEST_TOKEN
        yield client


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    yield from _client(
        tmp_path,
        options={
            EXAMPLE_ID: {
                "token": PLAIN_TOKEN,
                "env": {"API_KEY": PLAIN_KEY, "MODE": "fast"},
                "note": PLAIN_NOTE,
                "folder": "data",
            }
        },
    )


def _view(client: TestClient, module_id: str) -> ModuleOptionsView:
    res = client.get(f"{API}/modules/{module_id}/options")
    assert res.status_code == 200, res.text
    return ModuleOptionsView.model_validate(res.json())


def test_every_installed_module_has_a_read_only_view(client: TestClient) -> None:
    infos = [ModuleInfo.model_validate(m) for m in client.get(f"{API}/modules").json()]
    with_schema = 0
    for info in infos:
        view = _view(client, info.id)
        assert view.module_id == info.id
        if view.schema_ is None:
            assert view.yaml_snippet == ""  # 스키마 없음
            continue
        with_schema += 1
        data = YAML(typ="safe").load(io.StringIO(view.yaml_snippet))
        assert OPTIONS_MASK not in view.yaml_snippet
        if OPTIONS_MASK not in str(view.values):
            assert data == {"modules": {"options": {info.id: view.values}}}
    assert with_schema >= 3


def test_installed_module_schemas_carry_form_help(client: TestClient) -> None:
    """번들 모듈 옵션 스키마는 라벨·설명·x-ui.tier를 갖는다(`schema-help-lint`가 전체를 본다)."""
    for module in installed_modules():
        if module.descriptor.settings_schema is None:
            continue
        schema = _view(client, module.descriptor.id).schema_
        assert schema is not None
        for name, prop in schema.get("properties", {}).items():
            where = f"{module.descriptor.id}.{name}"
            assert prop.get("title"), where
            assert prop.get("description"), where
            assert prop.get(X_UI, {}).get("tier") in ("basic", "advanced"), where


def test_secrets_are_masked_in_values_and_snippet(client: TestClient) -> None:
    res = client.get(f"{API}/modules/{EXAMPLE_ID}/options")
    assert res.status_code == 200
    for plain in (PLAIN_KEY, PLAIN_TOKEN, "abcdefghijklmnop1234"):
        assert plain not in res.text
    view = ModuleOptionsView.model_validate(res.json())
    assert view.values["token"] == OPTIONS_MASK
    assert view.values["env"] == {"API_KEY": OPTIONS_MASK, "MODE": "fast"}
    assert view.values["note"] == OPTIONS_MASK
    assert view.values["limit"] == 3
    assert view.values["folder"] == "data"  # 경로 표시는 기본으로 켜짐
    # 조각: 가린 줄은 주석, 붙여 넣은 그대로 모듈 설정 검증을 통과하고 비밀·가림 문자열이 없다
    assert OPTIONS_MASK not in view.yaml_snippet
    assert "# token: <" in view.yaml_snippet
    pasted = YAML(typ="safe").load(io.StringIO(view.yaml_snippet))["modules"]["options"]
    parsed = _ExampleOptions.model_validate(pasted[EXAMPLE_ID])
    assert parsed.token is None
    assert parsed.env == {"MODE": "fast"}
    assert parsed.note == ""


def test_mask_matches_secret_rules() -> None:
    from agent_console_secret_rules import REDACTED

    assert REDACTED == OPTIONS_MASK


def test_secrets_are_masked_without_the_rules_provider(tmp_path: Path) -> None:
    """`secrets.rules` 포트를 주는 모듈을 꺼도 기본 규칙으로 가린다."""
    providers = assemble(installed_modules()).provided_ports().get("secrets.rules", [])
    assert providers, "비밀 규칙 포트 제공 모듈이 설치되어 있어야 한다"
    for client in _client(
        tmp_path,
        options={EXAMPLE_ID: {"env": {"API_KEY": PLAIN_KEY}}},
        modules={"disabled": providers},
    ):
        res = client.get(f"{API}/modules/{EXAMPLE_ID}/options")
        assert res.status_code == 200
        assert PLAIN_KEY not in res.text


def test_paths_are_hidden_when_expose_paths_is_off(tmp_path: Path) -> None:
    for client in _client(
        tmp_path,
        options={EXAMPLE_ID: {"folder": "data"}},
        security={"expose_paths": False},
    ):
        assert _view(client, EXAMPLE_ID).values["folder"] == OPTIONS_MASK


def test_unknown_module_is_404(client: TestClient) -> None:
    res = client.get(f"{API}/modules/no-such-module/options")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_options_cannot_be_written(client: TestClient, method: str) -> None:
    res = client.request(method, f"{API}/modules/{EXAMPLE_ID}/options", json={"limit": 9})
    assert res.status_code == 405
    assert _view(client, EXAMPLE_ID).values["limit"] == 3


def test_openapi_documents_the_read_only_route(client: TestClient) -> None:
    paths = client.get(f"{API}/openapi.json").json()["paths"]
    route = paths[f"{API}/modules/{{module_id}}/options"]
    assert set(route) == {"get"}
