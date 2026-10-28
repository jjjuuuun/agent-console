"""테스트 공용: 조립·클라이언트·DB.

범위 종류 이름은 테스트 데이터다(패키지 기본에 기대지 않음).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_memory import SERVER_WARNINGS, module
from agent_console_mod_memory.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ExtensionRegistries,
    Module,
    ModulesConfig,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "m" * 32
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
"""``ac-secret-rules`` 기본 규칙이 비밀로 보는 값(테스트 표본)."""

NOTES = {"kind": "notes", "id": "p1"}
"""테스트 범위(사용자 데이터 이름)."""


def _make_assembly(
    *,
    database: Any | None = None,
    settings: Any = None,
    options: dict[str, Any] | None = None,
    extra: Sequence[Module] = (),
    registries: Any | None = None,
) -> Assembly:
    """mod-memory(+ 설정 제공 모듈) 조립."""
    modules: list[Module] = [module, *extra]
    if settings is not None:
        modules.append(static_settings_module(settings))
    cfg = ModulesConfig(options={"mod-memory": options} if options else {})
    return assemble(
        modules,
        cfg,
        base=BaseServices(
            database=database,
            registries=registries if registries is not None else ExtensionRegistries(),
        ),
    )


def _client_of(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _warning_codes(assembly: Assembly) -> list[str]:
    return [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "console.sqlite3")
    yield db
    db.close()


@pytest.fixture
def make_assembly() -> Callable[..., Assembly]:
    """조립 함수(``database``·``settings``·``options``·``extra``·``registries``)."""
    return _make_assembly


@pytest.fixture
def client_of() -> Callable[[Assembly], TestClient]:
    """조립 → 토큰을 단 TestClient."""
    return _client_of


@pytest.fixture
def warning_codes() -> Callable[[Assembly], list[str]]:
    """조립의 ``server.warnings`` 코드 목록."""
    return _warning_codes
