"""예제 구조도 프로필 플러그인(X23): entry point 선언·데이터 검사·설치/제거에 따른 목록 변화.

설치 없이 실행한다(pytest 설정 ``pythonpath = ["src"]``). "설치"는 임시 폴더에 이 패키지의
``*.dist-info``(METADATA·entry_points.txt)를 만드는 것으로 흉내 낸다.
"제거"는 그 dist-info를 지우는 것이다.

X23 그룹(``agent_console.architecture_profiles``)의 메타데이터 발견은 그 임시 폴더로만 격리한다
(``importlib.metadata.entry_points``를 그 그룹에 한해 바꾼다). 그래서 이 예제를 venv에 실제로 설치한
상태에서도, 설치하지 않은 상태에서도 결과가 같다. 다른 그룹(조건 연산자 등)은 설치된 대로 찾는다.
호스트 플러그인 로더(``mod-architecture``의 ``load_plugins``)는 설치된 패키지와 똑같이 entry point와
배포 이름(``plugin:<배포 이름>``)을 얻는다.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_architecture import ARCHITECTURE_PROFILES_GROUP, profile_issues
from agent_console_conditions import default_operators
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_architecture import PROFILE_ID, profiles
from agent_console_mod_architecture import module
from agent_console_mod_architecture.plugins import load_plugins, profile_registry
from agent_console_modkit import BaseServices, ExtensionRegistries, PluginLoadContext, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
DIST_NAME = "agent-console-example-architecture"
EP_NAME = "example.architecture"
EP_VALUE = "agent_console_example_architecture:profiles"
ORIGIN = f"plugin:{DIST_NAME}"
TOKEN = "t" * 32
API = "/api/v1"


@pytest.fixture(autouse=True)
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """빈 설치 위치. X23 그룹의 entry point는 이 폴더에서만 찾는다(실제 venv 설치와 무관)."""
    root = tmp_path / "site"
    root.mkdir()
    original = importlib.metadata.entry_points

    def isolated(**params: Any) -> importlib.metadata.EntryPoints:
        if params.get("group") != ARCHITECTURE_PROFILES_GROUP:
            return original(**params)
        found = [
            ep
            for dist in importlib.metadata.distributions(path=[str(root)])
            for ep in dist.entry_points.select(**params)
        ]
        return importlib.metadata.EntryPoints(found)

    monkeypatch.setattr(importlib.metadata, "entry_points", isolated)
    return root


def _install(site: Path) -> Path:
    dist_info = site / "agent_console_example_architecture-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {DIST_NAME}\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{ARCHITECTURE_PROFILES_GROUP}]\n{EP_NAME} = {EP_VALUE}\n", encoding="utf-8"
    )
    importlib.invalidate_caches()
    return dist_info


def _uninstall(dist_info: Path) -> None:
    shutil.rmtree(dist_info)
    importlib.invalidate_caches()


@contextmanager
def _server(*, enabled: frozenset[str] | None = None) -> Iterator[TestClient]:
    """서버 시작과 같은 순서: 호스트 플러그인 로더 → 모듈 조립 → 앱."""
    registries = ExtensionRegistries()
    load_plugins(PluginLoadContext(registries=registries, enabled=enabled))
    assembly = assemble([module], None, base=BaseServices(registries=registries))
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _listed(client: TestClient) -> dict[str, Any]:
    response = client.get(f"{API}/architecture/profiles")
    assert response.status_code == 200
    return {row["id"]: row for row in response.json()["profiles"]}


def test_entry_point_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[ARCHITECTURE_PROFILES_GROUP] == {EP_NAME: EP_VALUE}


def test_profile_data_is_clean() -> None:
    found = profiles()
    assert list(found) == [PROFILE_ID]
    operators, _reports = default_operators()
    assert profile_issues(found[PROFILE_ID], operators=operators, profile_id=PROFILE_ID) == []


def test_install_shows_plugin_profile_and_uninstall_removes_it(site: Path) -> None:
    with _server() as client:
        assert PROFILE_ID not in _listed(client)  # 설치 전

    dist_info = _install(site)
    with _server() as client:
        row = _listed(client)[PROFILE_ID]
        assert row["origin"] == ORIGIN
        assert row["cells"] == 2
        assert row.get("disabled") is not True
        detail = client.get(f"{API}/architecture/profiles/{PROFILE_ID}")
        assert detail.status_code == 200

    _uninstall(dist_info)
    with _server() as client:
        assert PROFILE_ID not in _listed(client)  # 제거 후(재시작)


def test_plugins_enabled_list_turns_it_off_while_installed(site: Path) -> None:
    _install(site)
    with _server(enabled=frozenset({"something-else"})) as client:
        assert PROFILE_ID not in _listed(client)
    registries = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=registries, enabled=frozenset({EP_NAME})))
    assert [r.status for _group, r in reports if r.key == EP_NAME] == ["loaded"]
    assert profile_registry(registries).get(EP_NAME).origin == ORIGIN
