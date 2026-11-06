"""mod-wiki 테스트 도우미: 조립·TestClient·임시 규칙·위키 데이터(예시는 테스트 안에서만)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_wiki import WIKI_SERVICE, WikiService, module
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
from agent_console_store import SqliteDatabase

TOKEN = "w" * 32
API = "/api/v1"
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
"""``ac-secret-rules`` 기본 규칙이 비밀로 보는 값(테스트 표본)."""

RULES: dict[str, Any] = {
    "name": "테스트 규칙",
    "instructions": {"file": "instructions.md"},
    "page_templates": [
        {"id": "note", "title": "메모", "file": "templates/note.md", "path": "notes/{slug}"}
    ],
    "write_rules": [
        {
            "id": "no-temp",
            "applies_to": ["**"],
            "deny_patterns": ["(?i)\\bTEMPNOTE\\b"],
            "action": "reject",
            "message": "임시 메모 금지",
        },
        {
            "id": "agents-no-delete",
            "when": {
                "all": [
                    {"path": "/change/op", "op": "eq", "value": "delete"},
                    {"path": "/author/kind", "op": "eq", "value": "agent"},
                ]
            },
            "action": "reject",
            "message": "에이전트는 지울 수 없음",
        },
    ],
    "lint_rules": [
        {
            "id": "stale",
            "when": {"all": [{"path": "/idle_days", "op": "gte", "value": 90}]},
            "severity": "info",
            "message": "오래됨",
        }
    ],
}
"""테스트 규칙 문서(사용자 데이터 예 — 저장소 데이터에 두지 않는다)."""


def make_assembly(
    tmp_path: Path,
    *extra: Any,
    options: Mapping[str, Any] | None = None,
    settings: Any = None,
    config: ModulesConfig | None = None,
    database: Any = None,
) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=database,
        registries=ExtensionRegistries(),
    )
    modules = [module, static_settings_module(settings if settings is not None else {}), *extra]
    cfg = config or (ModulesConfig(options={"mod-wiki": dict(options)}) if options else None)
    return assemble(modules, cfg, base=base)


def client_for(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def service_of(assembly: Assembly) -> WikiService:
    found = assembly.port(WIKI_SERVICE)
    assert isinstance(found, WikiService)
    return found


def make_rules(client: TestClient, rule_id: str = "team-rules", **query: str) -> str:
    """테스트 규칙 + 본문 파일 두 개를 만들고 규칙 id를 돌려준다."""
    created = client.post(f"{API}/wiki/rules", json={**RULES, "id": rule_id}, params=query)
    assert created.status_code == 201, created.text
    version = created.headers["etag"]
    for path, text in (
        ("instructions.md", "결정만 기록하세요.\n"),
        ("templates/note.md", "# {title}\n\n작성일 {date}\n"),
    ):
        res = client.put(
            f"{API}/wiki/rules/{rule_id}/files/{path}",
            content=text.encode(),
            headers={"If-Match": version},
            params=query,
        )
        assert res.status_code == 200, res.text
        version = res.headers["etag"]
    return rule_id


def write_page(
    client: TestClient, wiki: str, path: str, content: str, **query: str
) -> dict[str, Any]:
    """새 페이지 또는 덮어쓰기(지금 해시로 ``If-Match``)."""
    current = client.get(f"{API}/wiki/wikis/{wiki}/pages/{path}", params=query)
    headers = (
        {"If-Match": current.headers["etag"]}
        if current.status_code == 200
        else {"If-None-Match": "*"}
    )
    res = client.put(
        f"{API}/wiki/wikis/{wiki}/pages/{path}",
        json={"content": content},
        headers=headers,
        params=query,
    )
    assert res.status_code in (200, 201), res.text
    body: dict[str, Any] = res.json()
    return body


class Kit:
    """테스트 도우미 묶음(픽스처 ``kit``로 받는다 — importlib 모드라 conftest를 import하지
    않는다)."""

    API = API
    SECRET = SECRET
    RULES = RULES
    make_assembly = staticmethod(make_assembly)
    client_for = staticmethod(client_for)
    service_of = staticmethod(service_of)
    make_rules = staticmethod(make_rules)
    write_page = staticmethod(write_page)


@pytest.fixture
def kit() -> type[Kit]:
    return Kit


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    db = SqliteDatabase.open(tmp_path / "state" / "console.sqlite3")
    yield db
    db.close()


@pytest.fixture
def standalone(tmp_path: Path, database: SqliteDatabase) -> Iterator[tuple[TestClient, Assembly]]:
    """모듈 혼자(+ 설정, 호스트 DB) 켠 서버."""
    assembly = make_assembly(tmp_path, database=database)
    with client_for(assembly) as client:
        yield client, assembly
