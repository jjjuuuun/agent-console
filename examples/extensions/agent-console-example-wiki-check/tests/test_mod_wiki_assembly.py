"""예제를 설치한 조립(테스트 호스트 + mod-wiki): entry point로 로드 → 사용자 설정에서 켬 → 쓰기에
거부(error)·경고(warning)가 걸린다. 설정에 켜지 않으면 아무 영향이 없고, 옵션이 틀리면 검사는 쓰이지
않고 서버 경고(`wiki.settings_invalid`)만 남는다.

entry point는 설치 대신 `importlib.metadata.EntryPoint`를 만들어 mod-wiki 로더에 주입한다
(설치한 서버의 호스트 플러그인 로더가 하는 일과 같다).
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_example_wiki_check import CHECK_ID
from agent_console_mod_wiki import SECTION_KEY, module
from agent_console_mod_wiki.plugins import (
    WRITE_CHECKS_EXTENSION,
    WRITE_CHECKS_GROUP,
    as_write_check_factory,
    load_write_check_plugins,
)
from agent_console_mod_wiki.ports import SERVER_WARNINGS
from agent_console_mod_wiki.testing import static_settings_module
from agent_console_modkit import Assembly, BaseServices, ExtensionRegistries, Paths, assemble
from agent_console_modkit.host import ISSUES_HEADER, SecurityPolicy, create_host_app

API = "/api/v1"
TOKEN = "k" * 32
PLAIN = "# 메모\n\n본문\n"
WITH_SOURCE = "---\nsource: 회의록\n---\n# 메모\n"


def _installed_registries() -> ExtensionRegistries:
    """설치한 서버처럼 entry point 그룹을 묶음의 확장 레지스트리에 로드한다."""
    bundle = ExtensionRegistries()
    registry = bundle.extension(WRITE_CHECKS_EXTENSION, validator=as_write_check_factory)
    ep = importlib.metadata.EntryPoint(
        name=CHECK_ID,
        value="agent_console_example_wiki_check:FrontMatterKeysCheck",
        group=WRITE_CHECKS_GROUP,
    )
    reports = load_write_check_plugins(registry, entry_points=[ep])
    assert [r.status for r in reports] == ["loaded"], reports
    return bundle


def _assembly(root: Path, checks: Sequence[Mapping[str, Any]]) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"),
        registries=_installed_registries(),
    )
    settings = {SECTION_KEY: {"write_checks": list(checks)}} if checks else {}
    return assemble([module, static_settings_module(settings)], None, base=base)


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
        made = client.post(f"{API}/wiki/wikis", json={"name": "w"})
        assert made.status_code == 201, made.text
        return client

    yield make
    for client in opened:
        client.__exit__(None, None, None)


def _create(client: TestClient, path: str, content: str) -> Any:
    return client.put(
        f"{API}/wiki/wikis/w/pages/{path}",
        json={"content": content},
        headers={"If-None-Match": "*"},
    )


def _enabled(**options: Any) -> list[dict[str, Any]]:
    return [{"id": CHECK_ID, "enabled": True, "options": options}]


def test_enabled_error_rejects_the_write(tmp_path: Path, client_of: Any) -> None:
    client = client_of(_assembly(tmp_path, _enabled(keys=["source"])))
    res = _create(client, "notes/a", PLAIN)
    assert res.status_code == 422, res.text
    error = res.json()["error"]
    assert error["code"] == "wiki.rule_rejected"
    assert error["details"]["rule_id"] == CHECK_ID
    assert error["details"]["issues"][0]["code"] == "example.front_matter_missing"
    assert client.get(f"{API}/wiki/wikis/w/pages/notes/a").status_code == 404
    assert _create(client, "notes/a", WITH_SOURCE).status_code == 201


def test_enabled_warning_saves_and_reports(tmp_path: Path, client_of: Any) -> None:
    checks = _enabled(keys=["source"], severity="warning", paths=["notes/**"])
    client = client_of(_assembly(tmp_path, checks))
    res = _create(client, "notes/a", PLAIN)
    assert res.status_code == 201, res.text
    issues = json.loads(res.headers[ISSUES_HEADER])
    assert [(i["code"], i["severity"], i["rule_id"]) for i in issues] == [
        ("example.front_matter_missing", "warning", CHECK_ID)
    ]
    # 글롭 밖 페이지는 검사하지 않는다
    other = _create(client, "inbox/b", PLAIN)
    assert other.status_code == 201
    assert ISSUES_HEADER.lower() not in {k.lower() for k in other.headers}


def test_installed_but_not_enabled_changes_nothing(tmp_path: Path, client_of: Any) -> None:
    assembly = _assembly(tmp_path, [])
    client = client_of(assembly)
    res = _create(client, "notes/a", PLAIN)
    assert res.status_code == 201, res.text
    assert ISSUES_HEADER.lower() not in {k.lower() for k in res.headers}
    codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
    assert "wiki.settings_invalid" not in codes


def test_enabled_false_changes_nothing(tmp_path: Path, client_of: Any) -> None:
    checks = [{"id": CHECK_ID, "enabled": False, "options": {"keys": ["source"]}}]
    client = client_of(_assembly(tmp_path, checks))
    assert _create(client, "notes/a", PLAIN).status_code == 201


def test_bad_options_disable_the_check_with_a_server_warning(
    tmp_path: Path, client_of: Any
) -> None:
    assembly = _assembly(tmp_path, _enabled(keys=["source"], severity="fatal"))
    client = client_of(assembly)
    assert _create(client, "notes/a", PLAIN).status_code == 201
    codes = [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]
    assert codes.count("wiki.settings_invalid") == 1
