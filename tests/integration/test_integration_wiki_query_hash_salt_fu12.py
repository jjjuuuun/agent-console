"""FU.12: 검색어 해시 솔트 값은 서버 응답·로그에 나오지 않는다(환경변수 이름만 보인다)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agent_console_server.testing import API, make_settings, server

SALT_VALUE = "planted-salt-value-q7x9"
SALT_ENV = "AC_TEST_WIKI_QUERY_SALT"


def test_salt_value_not_in_server_responses_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    settings = make_settings(
        tmp_path,
        options={
            "mod-wiki": {"query_hash": "hmac", "query_hash_salt_env": SALT_ENV},
            "mod-memory": {"query_hash": "hmac", "query_hash_salt_env": SALT_ENV},
        },
    )
    environ = {SALT_ENV: SALT_VALUE}
    bodies: list[str] = []
    with server(settings, environ=environ) as client:
        modules = client.get(f"{API}/modules")
        assert modules.status_code == 200
        bodies.append(modules.text)
        for module in modules.json():
            if module["id"] in {"mod-wiki", "mod-memory"}:
                view = client.get(f"{API}/modules/{module['id']}/options")
                assert view.status_code == 200, view.text
                bodies.append(view.text)
        for path in ("/server-info", "/bootstrap", "/health"):
            response = client.get(f"{API}{path}")
            assert response.status_code == 200, response.text
            bodies.append(response.text)
    joined = "\n".join(bodies)
    assert SALT_ENV in joined  # 환경변수 이름은 보인다(보기가 비어 있지 않다)
    assert SALT_VALUE not in joined
    assert SALT_VALUE not in caplog.text
