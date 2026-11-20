"""프로젝트 공간 ``sdd.changed`` 수용(6R.30, design §6R.7).

실제 ``mod-projects`` 버전 기록 감싸개(폴더 기록 DB, 저장마다 ``definitions.saved``)를 거쳐 만들기
한 번 = 한 건(정의 + 본문 두 버전이어도), 다시 읽기 0건, 밖에서 고친 뒤 다음 읽기 한 건."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_contracts.sdd import SddChanged
from agent_console_link_projects_sdd import module
from agent_console_mod_projects import RECORDS_SPACES, ProjectsModule
from agent_console_mod_sdd import SDD_TOPIC
from agent_console_mod_sdd import module as sdd_module
from agent_console_mod_sdd.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    Module,
    ModuleContext,
    ModuleParts,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_sdd import definition_kinds
from agent_console_store import FileDefinitionStore, RecordsDb, open_records_db

API = "/api/v1"
TOKEN = "c" * 32
CFG = ".agent-console"

TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "flow",
    "name": "흐름",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
}
"""테스트 데이터(패키지 기본에 기대지 않음)."""


class _Records:
    """``records.spaces`` 가짜: 공간 이름 → 그 폴더 기록 DB(legacy 버전 표만)."""

    def __init__(self, roots: dict[str, Path]) -> None:
        self.dbs: dict[str, RecordsDb] = {
            name: open_records_db(
                root / CFG / "records.sqlite3", backup_dir=root / CFG / ".state" / "backups"
            )
            for name, root in roots.items()
        }

    def open(self, space: str) -> RecordsDb:
        return self.dbs[space]

    def state(self, space: str) -> Any:
        return self.dbs[space].state

    def close(self, space: str) -> None:
        self.dbs[space].close()


def _assembly(root: Path, records: _Records) -> Assembly:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RECORDS_SPACES, records)
        return ModuleParts()

    mods: list[Module] = [
        ProjectsModule(),  # 기본 버전 기록소 = 기록 DB + 저장 알림 감싸개
        sdd_module,
        static_settings_module({}),
        module,
        fake_module("test-records", kind="testing", provides=[RECORDS_SPACES], on_build=build),
    ]
    base = BaseServices(paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"))
    return assemble(mods, base=base)


def _host(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _spy(assembly: Assembly) -> list[SddChanged]:
    hub: Any = assembly.services.ws_hub
    seen: list[SddChanged] = []
    original: Callable[..., Any] = hub.publish

    def publish(topic: str, message: Any) -> Any:
        if topic == SDD_TOPIC:
            seen.append(message.payload)
        return original(topic, message)

    hub.publish = publish
    return seen


def _write_template(config_root: Path) -> None:
    store = FileDefinitionStore(
        config_root,
        definition_kinds(
            spec_kind="spec",
            spec_directory="specs",
            template_kind="spec-template",
            template_directory="spec-templates",
        ),
    )
    created = store.create("spec-template", TEMPLATE)
    store.write_files(
        "spec-template",
        "flow",
        {"req.md": b"# req\n\n**R1** one\n", "tasks.md": b"# tasks\n\n- [ ] 1 first [req: R1]\n"},
        expected_version=created.version_hash,
    )


def test_project_space_create_once_reread_zero_external_once(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    records = _Records({"project:p1": folder})
    assembly = _assembly(tmp_path / "app", records)
    seen = _spy(assembly)
    q = "?project=p1"
    try:
        with _host(assembly) as client:
            reg = client.post(f"{API}/projects", json={"folder": str(folder), "id": "p1"})
            assert reg.status_code == 201, reg.text
            _write_template(folder / CFG)
            assert client.get(f"{API}/sdd/templates{q}").is_success
            seen.clear()

            made = client.post(f"{API}/sdd/specs{q}", json={"name": "Pay", "template": "flow"})
            assert made.status_code == 201, made.text
            assert [(p.space.project_id, p.spec_id) for p in seen] == [("p1", "pay")]
            assert seen[0].version_hash == made.json()["version_hash"]

            seen.clear()
            for read in ("/sdd/specs", "/sdd/specs/pay", "/sdd/specs/pay/tasks"):
                assert client.get(f"{API}{read}{q}").is_success
            assert seen == []  # 같은 상태로 다시 읽으면 0건

            tasks = folder / CFG / "specs" / "pay" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8") + "- [ ] 2 밖에서 더함\n", encoding="utf-8"
            )
            view = client.get(f"{API}/sdd/specs/pay{q}")
            assert view.is_success
            assert [(p.space.project_id, p.spec_id) for p in seen] == [("p1", "pay")]
            assert seen[0].version_hash == view.json()["version_hash"]

            seen.clear()
            for read in ("/sdd/specs", "/sdd/specs/pay", "/sdd/specs/pay/tasks"):
                assert client.get(f"{API}{read}{q}").is_success
            assert seen == []
    finally:
        for db in records.dbs.values():
            db.close()
