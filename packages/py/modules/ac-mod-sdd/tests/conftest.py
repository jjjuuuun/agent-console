"""mod-sdd 테스트 도우미: 조립·TestClient·단독 루트에 문서 틀 쓰기."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_sdd import module
from agent_console_mod_sdd.testing import static_settings_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_sdd import definition_kinds
from agent_console_store import FileDefinitionStore

TOKEN = "t" * 32
API = "/api/v1"

TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "flow",
    "name": "테스트 흐름",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "design", "title": "설계", "file": "design.md"},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
    "rules": {
        "document_states": [{"id": "draft"}, {"id": "approved", "label": "승인"}],
        "initial_document_state": "draft",
        "transitions": [
            {"from": "draft", "to": "approved", "by": ["human"]},
            {"from": "*", "to": "draft", "by": ["human"]},
        ],
        "gates": [
            {
                "id": "design-first",
                "applies_to": ["task_status"],
                "message": "설계 승인 전",
                "require": {
                    "all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]
                },
            }
        ],
        "run_profiles": [
            {"id": "impl", "title": "구현", "graph": "team-x", "purpose": "implement"}
        ],
    },
}
REQ = "# 요구\n\n**R1** 첫 요구\n\n**R2** 둘째 요구\n"
TASKS = (
    "# 작업\n\n## 1단계\n\n"
    "- [ ] 1.1 뼈대 [req: R1] [owner: be]\n"
    "- [ ] 1.2 화면 [req: R1] [depends: 1.1]\n\n"
    "## 2단계\n\n"
    "- [ ] 2.1 검증 [depends: 1.2]\n"
)


def spec_store(root: Path) -> FileDefinitionStore:
    """단독 루트 저장소(모듈 기본 종류 이름·폴더)."""
    return FileDefinitionStore(
        root,
        definition_kinds(
            spec_kind="spec",
            spec_directory="specs",
            template_kind="spec-template",
            template_directory="spec-templates",
        ),
    )


def write_template(store: Any, document: Mapping[str, Any] | None = None) -> None:
    doc = dict(document or TEMPLATE)
    created = store.create(doc["kind"], doc)
    store.write_files(
        doc["kind"],
        doc["id"],
        {"req.md": REQ.encode(), "tasks.md": TASKS.encode(), "design.md": b"# design\n"},
        expected_version=created.version_hash,
    )


def make_assembly(
    tmp_path: Path,
    *extra: Any,
    options: Mapping[str, Any] | None = None,
    settings: Any = None,
    config: ModulesConfig | None = None,
) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    modules = [module, static_settings_module(settings if settings is not None else {}), *extra]
    cfg = config or (ModulesConfig(options={"mod-sdd": dict(options)}) if options else None)
    return assemble(modules, cfg, base=base)


def client_for(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


class Kit:
    """테스트 도우미 묶음(픽스처 ``kit``로 받는다 — importlib 모드라 conftest를 import하지
    않는다)."""

    API = API
    TEMPLATE = TEMPLATE
    REQ = REQ
    TASKS = TASKS
    spec_store = staticmethod(spec_store)
    write_template = staticmethod(write_template)
    make_assembly = staticmethod(make_assembly)
    client_for = staticmethod(client_for)


@pytest.fixture
def kit() -> type[Kit]:
    return Kit


@pytest.fixture
def standalone(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """모듈 혼자(+ 설정) 켠 서버와 단독 루트 폴더."""
    with client_for(make_assembly(tmp_path)) as client:
        yield client, tmp_path / "ws" / "sdd"
