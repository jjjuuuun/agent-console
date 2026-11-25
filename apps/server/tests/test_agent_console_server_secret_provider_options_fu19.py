"""FU.19 QA: 비밀 공급자 설정 훅의 값이 `/server-info`·로그·시작 거부 메시지에 새지 않는다.

가짜 공급자(스키마에 `x-secret`·`format: password`·`format: path`와 평문 비밀 의심 자유 문장)를
`plugins.modules`로 등록하고 `secrets.providers.<key>`에 값을 준다.
"""

from __future__ import annotations

import json
import logging
import sys
import textwrap
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_server import ConfigError, create_app
from agent_console_server.testing import API, TEST_TOKEN, default_environ, make_settings

KEY = "fu19-fake"
SECRET_X = "x-secret-value-8812"
SECRET_PW = "password-format-value-4471"
PLAIN = "sk-live-abcdef1234567890"
PATH_VALUE = "/very/private/place/secrets.env"

MODULE_SOURCE = textwrap.dedent(
    """
    from typing import Any


    class FakeProvider:
        def __init__(self, options: dict[str, Any] | None = None) -> None:
            self._options = options or {}

        def get_secret(self, name: str) -> str | None:
            return None

        @classmethod
        def options_schema(cls) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "x-secret": True, "title": "토큰"},
                    "pw": {"type": "string", "format": "password", "title": "암호"},
                    "where": {"type": "string", "format": "path", "title": "위치"},
                    "note": {"type": "string", "title": "메모"},
                },
            }

        @classmethod
        def from_options(cls, options: Any, *, environ: Any, base_dir: Any) -> "FakeProvider":
            if "reject" in options:
                raise ValueError("잘못됐습니다: reject")
            return cls(dict(options))


    def register(registries: Any) -> None:
        registry = getattr(registries, "secret_providers", None)
        if registry is None:
            registry = registries.extension("secret_providers")
        registry.register("fu19-fake", FakeProvider(), source="test")
    """
)


@pytest.fixture
def plugin_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    folder = tmp_path / "plug"
    folder.mkdir()
    (folder / "fu19_fake_provider.py").write_text(MODULE_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(folder))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    yield_name = "fu19_fake_provider"
    sys.modules.pop(yield_name, None)
    return f"{yield_name}:register"


def _settings(
    tmp_path: Path, plugin: str, options: Mapping[str, object], *, expose_paths: bool
) -> object:
    return make_settings(
        tmp_path,
        plugins={"modules": [plugin]},
        secrets={"providers": {KEY: options}},
        security={"expose_paths": expose_paths},
    )


def _client(
    tmp_path: Path, plugin: str, options: Mapping[str, object], *, expose_paths: bool
) -> Iterator[TestClient]:
    settings = _settings(tmp_path, plugin, options, expose_paths=expose_paths)
    app = create_app(settings, environ=default_environ(), token=TEST_TOKEN)  # type: ignore[arg-type]
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TEST_TOKEN
        yield client


OPTIONS = {"token": SECRET_X, "pw": SECRET_PW, "where": PATH_VALUE, "note": PLAIN}


@pytest.mark.parametrize("expose_paths", [True, False])
def test_option_values_are_masked_in_server_info_and_logs(
    tmp_path: Path, plugin_module: str, caplog: pytest.LogCaptureFixture, expose_paths: bool
) -> None:
    with caplog.at_level(logging.DEBUG):
        for client in _client(tmp_path, plugin_module, OPTIONS, expose_paths=expose_paths):
            info = client.get(f"{API}/server-info")
            assert info.status_code == 200, info.text
            (view,) = [v for v in info.json()["plugin_options"] if v["name"] == KEY]
            assert view["configured"] is True
            for field in ("token", "pw", "note"):
                assert view["values"][field] != OPTIONS[field], field  # 가려졌다
            text = info.text + client.get(f"{API}/health").text + client.get(f"{API}/modules").text
            for value in (SECRET_X, SECRET_PW, PLAIN):
                assert value not in text
            assert SECRET_X not in view["yaml_snippet"]
            assert SECRET_PW not in view["yaml_snippet"]
            assert PLAIN not in view["yaml_snippet"]
            if expose_paths:
                assert view["values"]["where"] == PATH_VALUE
            else:
                assert view["values"]["where"] != PATH_VALUE
                assert PATH_VALUE not in text
                assert PATH_VALUE not in view["yaml_snippet"]
    logs = "\n".join(r.getMessage() for r in caplog.records)
    for value in (SECRET_X, SECRET_PW, PLAIN):
        assert value not in logs


def test_rejected_hook_refuses_start_without_values(tmp_path: Path, plugin_module: str) -> None:
    options = {**OPTIONS, "reject": True}
    with pytest.raises(ConfigError) as caught:
        create_app(
            _settings(tmp_path, plugin_module, options, expose_paths=True),  # type: ignore[arg-type]
            environ=default_environ(),
            token=TEST_TOKEN,
        )
    text = str(caught.value)
    assert f"secrets.providers.{KEY}" in text
    for value in (SECRET_X, SECRET_PW, PLAIN):
        assert value not in text
    assert json.dumps(OPTIONS) not in text
