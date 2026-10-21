"""5.2R.29: 모듈 옵션 읽기 전용 보기(스키마·가린 값·YAML 조각), 쓰기 없음."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, SecretStr
from ruamel.yaml import YAML

from agent_console_modkit import (
    OPTIONS_MASK,
    ModulesConfig,
    assemble,
    mask_values,
    read_module_options,
)
from agent_console_modkit.host import (
    MASKED_LINE_NOTE,
    SecurityPolicy,
    create_host_app,
    options_yaml_snippet,
)
from agent_console_modkit.host import (
    REDACTED as HOST_REDACTED,
)
from agent_console_modkit.testing import fake_module

API = "/api/v1"
PLAIN = "plain-value-should-not-leak"


class Inner(BaseModel):
    api_key: str | None = None
    limit: int = 1


class Opts(BaseModel):
    limit: int = 3
    token: SecretStr | None = None
    hidden: str | None = Field(default=None, json_schema_extra={"x-secret": True})
    folder: Path | None = None
    nested: Inner = Field(default_factory=Inner)
    backends: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _policy() -> SecurityPolicy:
    return SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])


def _key_finder(values: Any, at: str = "") -> list[str]:
    """테스트용 비밀 판정: 키 이름에 key·token이 들어가면 의심."""
    out: list[str] = []
    if isinstance(values, dict):
        for k, v in values.items():
            where = f"{at}/{k}"
            if isinstance(v, str) and ("key" in k.lower() or "token" in k.lower()):
                out.append(where)
            else:
                out.extend(_key_finder(v, where))
    return out


# ---------------------------------------------------------------- read_module_options


def test_no_schema_means_schema_none() -> None:
    view = read_module_options(fake_module("mod-a").descriptor)
    assert view.schema is None
    assert view.values == {}
    assert view.valid


def test_defaults_are_filled_and_schema_is_returned() -> None:
    view = read_module_options(fake_module("mod-a", settings_schema=Opts).descriptor, None)
    assert view.values["limit"] == 3
    assert view.values["nested"] == {"api_key": None, "limit": 1}
    assert view.schema is not None
    assert "limit" in view.schema["properties"]
    assert view.masked == ()


def test_schema_secret_fields_are_always_masked() -> None:
    d = fake_module("mod-a", settings_schema=Opts).descriptor
    view = read_module_options(d, {"token": PLAIN, "hidden": PLAIN})
    assert view.values["token"] == OPTIONS_MASK
    assert view.values["hidden"] == OPTIONS_MASK
    assert set(view.masked) == {"/token", "/hidden"}
    assert PLAIN not in repr(view)


def test_injected_finder_masks_nested_and_dynamic_keys() -> None:
    d = fake_module("mod-a", settings_schema=Opts).descriptor
    raw = {
        "nested": {"api_key": PLAIN},
        "backends": {"sdk": {"env": {"API_TOKEN": PLAIN, "MODE": "x"}}},
    }
    view = read_module_options(d, raw, secret_paths=_key_finder)
    assert view.values["nested"]["api_key"] == OPTIONS_MASK
    assert view.values["backends"]["sdk"]["env"] == {"API_TOKEN": OPTIONS_MASK, "MODE": "x"}
    assert "/backends/sdk/env/API_TOKEN" in view.masked
    assert PLAIN not in repr(view.values)


def test_finder_results_with_path_prefix_are_accepted() -> None:
    values, masked = mask_values({"a": {"b": PLAIN}}, None, secret_paths=lambda _: ["path=/a/b"])
    assert values == {"a": {"b": OPTIONS_MASK}}
    assert masked == ("/a/b",)


def test_finder_failure_masks_everything() -> None:
    def broken(_: Any) -> list[str]:
        raise RuntimeError("boom")

    d = fake_module("mod-a", settings_schema=Opts).descriptor
    view = read_module_options(d, {"nested": {"api_key": PLAIN}}, secret_paths=broken)
    assert all(v == OPTIONS_MASK for v in view.values.values())
    assert PLAIN not in repr(view.values)


def test_hide_paths_masks_path_fields() -> None:
    d = fake_module("mod-a", settings_schema=Opts).descriptor
    shown = read_module_options(d, {"folder": "/home/me/work"})
    assert shown.values["folder"] == "/home/me/work"
    hidden = read_module_options(d, {"folder": "/home/me/work"}, hide_paths=True)
    assert hidden.values["folder"] == OPTIONS_MASK


def test_invalid_settings_show_raw_values_masked() -> None:
    d = fake_module("mod-a", settings_schema=Opts).descriptor
    view = read_module_options(d, {"limit": "many", "token": PLAIN})
    assert not view.valid
    assert view.values["limit"] == "many"
    assert view.values["token"] == OPTIONS_MASK


def test_read_does_not_change_the_input() -> None:
    raw = {"token": PLAIN, "nested": {"api_key": PLAIN}}
    d = fake_module("mod-a", settings_schema=Opts).descriptor
    read_module_options(d, raw, secret_paths=_key_finder)
    assert raw == {"token": PLAIN, "nested": {"api_key": PLAIN}}


# ---------------------------------------------------------------- Assembly.module_options


def test_assembly_reads_options_of_disabled_modules_and_unknown_is_none() -> None:
    a = fake_module("mod-a", settings_schema=Opts)
    b = fake_module("mod-b")
    cfg = ModulesConfig(disabled=["mod-a"], options={"mod-a": {"limit": 9}})
    assembly = assemble([a, b], cfg)
    view = assembly.module_options("mod-a")
    assert view is not None
    assert view.values["limit"] == 9
    none_schema = assembly.module_options("mod-b")
    assert none_schema is not None
    assert none_schema.schema is None
    assert assembly.module_options("mod-zzz") is None


# ---------------------------------------------------------------- YAML 조각


def test_snippet_round_trips_under_modules_options() -> None:
    values = {"limit": 3, "names": ["a", "b"], "nested": {"x": None, "이름": "값"}}
    text = options_yaml_snippet("mod-a", values)
    data = YAML(typ="safe").load(io.StringIO(text))
    assert data == {"modules": {"options": {"mod-a": values}}}
    assert "이름" in text  # 한글을 이스케이프하지 않는다


def _load(text: str) -> Any:
    return YAML(typ="safe").load(io.StringIO(text))["modules"]["options"]["mod-a"]


def test_masked_scalar_becomes_a_comment_line() -> None:
    text = options_yaml_snippet("mod-a", {"limit": 3, "token": OPTIONS_MASK}, masked=["/token"])
    assert f"      # token: {MASKED_LINE_NOTE}" in text.splitlines()
    assert OPTIONS_MASK not in text
    assert _load(text) == {"limit": 3}  # 붙여 넣으면 그 키는 빠진다(기본값)


def test_container_left_with_only_masked_lines_is_commented_out() -> None:
    values = {"env": {"API_KEY": OPTIONS_MASK}, "keys": [OPTIONS_MASK, OPTIONS_MASK], "x": 1}
    masked = ["/env/API_KEY", "/keys/0", "/keys/1"]
    text = options_yaml_snippet("mod-a", values, masked=masked)
    # 빈 {}·[]·null로 바뀌지 않고 키가 빠진다(기본값)
    assert _load(text) == {"x": 1}
    assert "      # env:" in text
    assert "      # keys:" in text
    assert "# API_KEY:" in text
    assert "# - " in text


def test_nested_containers_are_commented_bottom_up() -> None:
    values = {"a": {"b": {"c": OPTIONS_MASK}}, "x": 1}
    text = options_yaml_snippet("mod-a", values, masked=["/a/b/c"])
    assert _load(text) == {"x": 1}


def test_all_values_masked_leaves_module_with_defaults() -> None:
    text = options_yaml_snippet("mod-a", {"token": OPTIONS_MASK}, masked=["/token"])
    assert _load(text) == {}
    assert "    mod-a: {}" in text


def test_mixed_container_keeps_unmasked_entries() -> None:
    values = {"env": {"API_KEY": OPTIONS_MASK, "MODE": "fast"}}
    text = options_yaml_snippet("mod-a", values, masked=["/env/API_KEY"])
    assert _load(text) == {"env": {"MODE": "fast"}}
    assert OPTIONS_MASK not in text


def test_partial_copy_of_snippet_cannot_carry_the_mask() -> None:
    """조각 어느 줄을 골라 복사해도 가림 문자열이 값으로 들어가지 않는다."""
    values = {"a": OPTIONS_MASK, "b": {"c": OPTIONS_MASK}}
    text = options_yaml_snippet("mod-a", values, masked=["/a", "/b/c"])
    for line in text.splitlines():
        assert OPTIONS_MASK not in line
        if "secret://" in line:
            assert line.lstrip().startswith("#")


def test_one_mask_string_in_modkit() -> None:
    assert HOST_REDACTED == OPTIONS_MASK


def test_empty_values_render_as_empty_mapping() -> None:
    data = YAML(typ="safe").load(io.StringIO(options_yaml_snippet("mod-a", {})))
    assert data == {"modules": {"options": {"mod-a": {}}}}


# ---------------------------------------------------------------- 호스트 경로


@pytest.fixture
def client() -> TestClient:
    a = fake_module("mod-a", settings_schema=Opts)
    b = fake_module("mod-b")
    cfg = ModulesConfig(options={"mod-a": {"token": PLAIN, "limit": 5}})
    app = create_host_app(assemble([a, b], cfg), policy=_policy())
    return TestClient(app)


def test_get_options_returns_schema_values_and_snippet(client: TestClient) -> None:
    res = client.get(f"{API}/modules/mod-a/options")
    assert res.status_code == 200
    body = res.json()
    assert body["module_id"] == "mod-a"
    assert body["schema"]["type"] == "object"
    assert body["values"]["limit"] == 5
    assert body["values"]["token"] == OPTIONS_MASK
    assert "mod-a:" in body["yaml_snippet"]
    assert PLAIN not in res.text


def test_get_options_without_schema(client: TestClient) -> None:
    body = client.get(f"{API}/modules/mod-b/options").json()
    assert body["schema"] is None
    assert body["yaml_snippet"] == ""


def test_unknown_module_is_404(client: TestClient) -> None:
    res = client.get(f"{API}/modules/nope/options")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_methods(client: TestClient, method: str) -> None:
    res = client.request(
        method.upper(),
        f"{API}/modules/mod-a/options",
        headers={"x-console-token": "t" * 32},
        json={"limit": 1},
    )
    assert res.status_code == 405
