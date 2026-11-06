"""link-runs-sdd 테스트 도우미: mod-sdd + 가짜 실행 모듈 + 이 연동을 조립한 서버."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_runs_sdd import module as link_module
from agent_console_link_runs_sdd.testing import FakeRuns, fake_runs_module
from agent_console_mod_sdd import module as sdd_module
from agent_console_mod_sdd.testing import SimpleSpace, spaces_module, static_settings_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_sdd import definition_kinds
from agent_console_store import FileDefinitionStore

TOKEN = "t" * 32
API = "/api/v1"
SPACE = "p1"

TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "flow",
    "name": "흐름",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "design", "title": "설계", "file": "design.md"},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
    "rules": {
        "document_states": [{"id": "draft"}, {"id": "approved"}],
        "initial_document_state": "draft",
        "transitions": [
            {"from": "draft", "to": "approved", "by": ["human"]},
            {"from": "*", "to": "draft", "by": ["human"]},
        ],
        "task_statuses": [
            {"id": "todo", "marker": " "},
            {"id": "doing", "marker": "~"},
            {"id": "review", "marker": "?"},
            {"id": "done", "marker": ["x", "X"], "done": True},
        ],
        "gates": [
            {
                "id": "design-approved",
                "applies_to": ["run"],
                "message": "설계 승인 전에는 실행하지 않습니다",
                "require": {
                    "all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]
                },
            }
        ],
        "run_profiles": [
            {
                "id": "impl",
                "title": "구현",
                "graph": "team-x",
                "purpose": "implement",
                "when": {"all": [{"path": "/task/fields/owner", "op": "exists"}]},
                "input": {"request": "작업 {task_id} {task_title} 담당 {task_field_owner}"},
                "status_on": {"started": "doing", "succeeded": "review"},
            },
            {"id": "verify", "title": "검증", "graph": "qa", "purpose": "verify"},
        ],
        "verification": {
            "purposes": ["verify"],
            "result_map": {"succeeded": "pass", "failed": "fail"},
        },
    },
}
REQ = "# 요구\n\n**R1** 첫 요구\n\n**R2** 둘째 요구\n"
TASKS = (
    "# 작업\n\n## 1단계\n\n"
    "- [ ] 1.1 뼈대 [req: R1] [owner: be]\n"
    "- [ ] 1.2 화면 [req: R2]\n"
    "  본문 줄\n\n"
    "## 2단계\n\n"
    "- [ ] 2.1 마무리 [depends: 1.1] [owner: be]\n"
)


def kinds() -> Any:
    return definition_kinds(
        spec_kind="spec",
        spec_directory="specs",
        template_kind="spec-template",
        template_directory="spec-templates",
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


@dataclass
class Env:
    client: TestClient
    runs: FakeRuns
    store: FileDefinitionStore

    def q(self, path: str) -> str:
        sep = "&" if "?" in path else "?"
        return f"{API}{path}{sep}project={SPACE}"

    def tasks_text(self, spec: str = "s") -> str:
        body = self.client.get(self.q(f"/sdd/specs/{spec}/documents/tasks")).json()
        text: str = body["content"]
        return text

    def task(self, key: str, spec: str = "s") -> dict[str, Any]:
        tasks = self.client.get(self.q(f"/sdd/specs/{spec}/tasks")).json()
        found: dict[str, Any] = next(t for t in tasks if t["key"] == key)
        return found

    def approve(self, spec: str = "s") -> None:
        r = self.client.post(
            self.q(f"/sdd/specs/{spec}/documents/design/state"), json={"to": "approved"}
        )
        assert r.status_code == 200, r.text


def build_env(
    tmp_path: Path,
    *,
    runs: FakeRuns | None = None,
    template: Mapping[str, Any] | None = None,
    settings: Any = None,
    with_link: bool = True,
    with_runs: bool = True,
    options: Mapping[str, Any] | None = None,
    store: FileDefinitionStore | None = None,
) -> tuple[Any, FakeRuns, FileDefinitionStore]:
    """조립. ``store``를 주면 그 공간 저장소를 그대로 쓴다(틀을 다시 쓰지 않음 — 재시작 흉내)."""
    fake = runs or FakeRuns(graphs={SPACE: {"team-x", "qa"}, None: {"team-x", "qa"}})
    if store is None:
        store = FileDefinitionStore(tmp_path / SPACE, kinds())
        write_template(store, template)
    modules: list[Any] = [
        sdd_module,
        static_settings_module(settings if settings is not None else {}),
        spaces_module({SPACE: SimpleSpace(store=store, config_dir=".agent-console")}),
    ]
    if with_runs:
        modules.append(fake_runs_module(fake))
    if with_link:
        modules.append(link_module)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    cfg = ModulesConfig(options={"link-runs-sdd": dict(options)}) if options else None
    return assemble(modules, cfg, base=base), fake, store


def client_for(assembly: Any) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


@contextmanager
def open_env(tmp_path: Path, **kwargs: Any) -> Iterator[Env]:
    """조립 → 서버 → 스펙 ``s``(틀 ``flow``, 공간 ``p1``)를 만든 환경."""
    assembly, fake, store = build_env(tmp_path, **kwargs)
    with client_for(assembly) as client:
        env = Env(client=client, runs=fake, store=store)
        made = client.post(env.q("/sdd/specs"), json={"name": "S", "template": "flow"})
        assert made.status_code == 201, made.text
        yield env


class Kit:
    """테스트 도우미 묶음(픽스처 ``kit`` — importlib 모드라 conftest를 import하지 않는다)."""

    API = API
    SPACE = SPACE
    TEMPLATE = TEMPLATE
    TASKS = TASKS
    open_env = staticmethod(open_env)
    build_env = staticmethod(build_env)
    client_for = staticmethod(client_for)


@pytest.fixture
def kit() -> type[Kit]:
    return Kit
