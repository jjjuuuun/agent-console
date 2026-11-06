"""설치한 조립(테스트 호스트 + mod-wiki): 설치자 `search.backend`·사용자 `wiki.search_backend`로
이 색인을 고르면 검색이 동작하고, 고르지 않으면 mod-wiki 기본 방식을 쓴다.
없는 방식 이름이면 대체 방식 + 경고.

entry point는 설치 대신 `importlib.metadata.EntryPoint`를 만들어 로더에 주입한다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_wiki_search import BACKEND_ID
from agent_console_mod_wiki import SECTION_KEY, module
from agent_console_mod_wiki.plugins import SEARCH_EXTENSION, search_registry
from agent_console_mod_wiki.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ExtensionRegistries,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_wiki import SEARCH_INDEX_GROUP, load_search_plugins

API = "/api/v1"
TOKEN = "k" * 32


def _installed_registries() -> ExtensionRegistries:
    """설치한 서버처럼 entry point 그룹을 묶음의 검색 색인 확장에 로드한다."""
    bundle = ExtensionRegistries()
    registry = search_registry(bundle)
    ep = importlib.metadata.EntryPoint(
        name=BACKEND_ID,
        value="agent_console_example_wiki_search:index_factory",
        group=SEARCH_INDEX_GROUP,
    )
    reports = load_search_plugins(registry, entry_points=[ep])
    assert [r.status for r in reports] == ["loaded"], reports
    assert registry is bundle.extension(SEARCH_EXTENSION)
    return bundle


def _assembly(
    root: Path, *, user: Mapping[str, Any] | None = None, installer: Mapping[str, Any] | None = None
) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"),
        registries=_installed_registries(),
    )
    settings = {SECTION_KEY: dict(user)} if user else {}
    config = ModulesConfig(options={"mod-wiki": dict(installer)}) if installer else None
    return assemble([module, static_settings_module(settings)], config, base=base)


@pytest.fixture
def client_of() -> Iterator[Any]:
    opened: list[TestClient] = []

    def make(assembly: Assembly) -> TestClient:
        policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
        app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
        client = TestClient(app)
        client.headers["X-Console-Token"] = TOKEN
        client.__enter__()
        opened.append(client)
        assert client.post(f"{API}/wiki/wikis", json={"name": "w"}).status_code == 201
        for path, content in (
            ("a", "# 소개\n\n이 위키는 역색인으로 찾는다.\n"),
            ("b", "# 둘째\n본문\n"),
        ):
            res = client.put(
                f"{API}/wiki/wikis/w/pages/{path}",
                json={"content": content},
                headers={"If-None-Match": "*"},
            )
            assert res.status_code == 201, res.text
        return client

    yield make
    for client in opened:
        client.__exit__(None, None, None)


def _search(client: TestClient, q: str) -> Any:
    res = client.get(f"{API}/wiki/wikis/w/search", params={"q": q})
    assert res.status_code == 200, res.text
    return res.json()


def test_user_setting_picks_the_example_backend(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path, user={"search_backend": BACKEND_ID}))
    found = _search(client, "역색인")
    assert found["backend"] == BACKEND_ID
    assert found["degraded"] is False
    assert [h["path"] for h in found["items"]] == ["a"]
    assert found["items"][0]["marks"]
    info = client.get(f"{API}/wiki/info").json()
    assert "wiki.search_degraded" not in {i["code"] for i in info["issues"]}


def test_installer_backend_option_picks_it_too(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path, installer={"search": {"backend": BACKEND_ID}}))
    assert _search(client, "역색인")["backend"] == BACKEND_ID


def test_newly_written_page_is_searchable(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path, user={"search_backend": BACKEND_ID}))
    assert _search(client, "새낱말")["items"] == []
    res = client.put(
        f"{API}/wiki/wikis/w/pages/c",
        json={"content": "# 셋째\n새낱말 포함\n"},
        headers={"If-None-Match": "*"},
    )
    assert res.status_code == 201
    assert [h["path"] for h in _search(client, "새낱말")["items"]] == ["c"]


def test_not_chosen_uses_the_default_backend(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path))  # 설치만 하고 고르지 않음
    found = _search(client, "역색인")
    assert found["backend"] != BACKEND_ID
    assert [h["path"] for h in found["items"]] == ["a"]


def test_unknown_backend_falls_back_with_warning(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path, user={"search_backend": "example-removed"}))
    found = _search(client, "역색인")
    assert found["backend"] != BACKEND_ID
    assert found["backend"] != "example-removed"
    info = client.get(f"{API}/wiki/info").json()
    assert "wiki.search_degraded" in {i["code"] for i in info["issues"]}
