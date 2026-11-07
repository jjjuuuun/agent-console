"""묶음 4b V1: 공용 저장은 허용하고 평문 비밀 경고를 저장 응답 ``X-Console-Issues``에 싣는다.

판정은 프로젝트 공간 쓰기 검사와 같은 ``SecretRules.find_suspected``(문서 전체)이고, 값은 어디에도
담지 않는다. 같은 계산을 포트 ``definitions.save_warnings``로 리소스 모듈에 준다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, KnownIssueCodes
from agent_console_mod_definitions import (
    DEFINITION_SAVE_WARNINGS,
    SAVE_SECRET_MESSAGE,
    DefinitionModuleSettings,
    module,
    save_secret_warnings,
)
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_secret_rules import default_rules

TOKEN = "t" * 32
API = "/api/v1"
PLAIN = "ghp" + "_" + "PlainToken1234567890"
LEAKY_AGENT = {
    "id": "leaky",
    "name": "새는",
    "backend": "fake-agent",
    "backend_options": {"default": {"response": f"응답 {PLAIN}"}},
}
CLEAN_AGENT = {"id": "clean", "name": "깨끗", "backend": "fake-agent"}


def _assembly(tmp_path: Path, **options: Any) -> Assembly:
    config = ModulesConfig(options={"mod-definitions": options}) if options else None
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _issues(response: Any) -> list[dict[str, Any]]:
    raw = response.headers.get("x-console-issues")
    return [] if raw is None else list(json.loads(raw))


def test_function_reports_paths_without_values() -> None:
    found = save_secret_warnings("agent", "leaky", LEAKY_AGENT, default_rules())
    assert [(i.severity, i.code) for i in found] == [
        ("warning", KnownIssueCodes.SECRET_PLAIN_FOUND)
    ]
    [issue] = found
    assert issue.path == "/backend_options/default/response"
    assert issue.details == {
        "kind": "agent",
        "id": "leaky",
        "path": "/backend_options/default/response",
        "reason": issue.details["reason"],
    }
    assert issue.message == SAVE_SECRET_MESSAGE
    assert PLAIN not in issue.model_dump_json()
    assert save_secret_warnings("agent", "clean", CLEAN_AGENT, default_rules()) == []


def test_agent_save_is_allowed_with_warning_header(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/agents", json=LEAKY_AGENT)
        assert created.status_code == 201
        [issue] = _issues(created)
        assert issue["severity"] == "warning"
        assert issue["code"] == "secret.plain_found"
        assert issue["path"] == "/backend_options/default/response"
        assert issue["details"]["kind"] == "agent"
        assert issue["details"]["id"] == "leaky"
        assert PLAIN not in created.headers["x-console-issues"]
        # 저장은 됐다(원문 GET은 가리지 않는다 — 기존 규칙)
        assert client.get(f"{API}/agents/leaky").status_code == 200

        etag = created.headers["ETag"]
        saved = client.put(
            f"{API}/agents/leaky", json={**LEAKY_AGENT, "name": "새는2"}, headers={"If-Match": etag}
        )
        assert saved.status_code == 200
        assert [i["code"] for i in _issues(saved)] == ["secret.plain_found"]

        clean = client.post(f"{API}/agents", json=CLEAN_AGENT)
        assert clean.status_code == 201
        assert "x-console-issues" not in clean.headers


def test_graph_save_and_duplicate_carry_warning(tmp_path: Path) -> None:
    graph = {"id": "g", "name": "팀", "nodes": [], "edges": [], "description": f"--token {PLAIN}"}
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/graphs", json=graph)
        assert created.status_code == 201
        assert [i["path"] for i in _issues(created)] == ["/description"]
        etag = created.headers["ETag"]
        saved = client.put(f"{API}/graphs/g", json=graph, headers={"If-Match": etag})
        assert saved.status_code == 200
        assert [i["code"] for i in _issues(saved)] == ["secret.plain_found"]
        copied = client.post(f"{API}/graphs/g/duplicate", json={"id": "g2", "name": "복제"})
        assert copied.status_code == 201
        assert [i["code"] for i in _issues(copied)] == ["secret.plain_found"]
        for response in (created, saved, copied):
            assert PLAIN not in response.headers.get("x-console-issues", "")


def test_message_is_a_setting_and_port_is_provided(tmp_path: Path) -> None:
    assert DefinitionModuleSettings().plain_secret_save_message == SAVE_SECRET_MESSAGE
    assembly = _assembly(tmp_path, plain_secret_save_message="바꾼 문구")
    port = assembly.port(DEFINITION_SAVE_WARNINGS)
    assert port is not None
    [issue] = port("agent", "leaky", LEAKY_AGENT)
    assert issue.message == "바꾼 문구"
    with _client(assembly) as client:
        created = client.post(f"{API}/agents", json=LEAKY_AGENT)
        assert [i["message"] for i in _issues(created)] == ["바꾼 문구"]


def test_user_weak_key_names_apply_to_save_warnings(tmp_path: Path) -> None:
    """D3: 약한 이름 판정도 같은 규칙(설정 secrets.weak_key_names)을 쓴다."""
    agent = {**CLEAN_AGENT, "id": "k", "attributes": {"input_key": "question"}}
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/agents", json=agent)
        assert created.status_code == 201
        assert "x-console-issues" not in created.headers
