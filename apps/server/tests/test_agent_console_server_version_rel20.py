"""표시 버전: health·bootstrap·server-info·OpenAPI가 모두 설치 메타데이터의 서버 버전이다.

값을 테스트에 박지 않는다. 설치 메타데이터가 `pyproject.toml`의 `project.version`과 같은지도 본다
(버전을 올리고 `uv sync`를 잊으면 여기서 걸린다).
"""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

from agent_console_contracts import CONTRACTS_VERSION
from agent_console_server import server_version
from agent_console_server.testing import API, make_settings, server

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_server_version_is_installed_metadata() -> None:
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert server_version() == version("agent-console-server") == declared


def test_every_surface_shows_server_version(tmp_path: Path) -> None:
    expected = version("agent-console-server")
    with server(make_settings(tmp_path)) as client:
        health = client.get(f"{API}/health").json()
        bootstrap = client.get(f"{API}/bootstrap").json()
        info = client.get(f"{API}/server-info").json()
        openapi = client.get(f"{API}/openapi.json").json()
    assert health["server_version"] == expected
    assert bootstrap["server_version"] == expected
    assert info["server_version"] == expected
    assert openapi["info"]["version"] == expected
    # 계약 버전은 서버 버전과 따로 간다.
    assert {health["contracts_version"], bootstrap["contracts_version"]} == {CONTRACTS_VERSION}
    assert info["contracts_version"] == CONTRACTS_VERSION
