"""``GET /projects/copy/items``의 ``saved_at``: 기본 종류(팀 구성·에이전트·리소스)와 기여 종류 모두.

라이브러리와 프로젝트 공간 두 곳, 저장소로 저장한 항목과 바깥에서 파일로 넣은 항목(저장 기록 없음 →
파일 수정 시각) 모두 채워지는지 본다. 라이브러리 저장소·기여 모듈은 이 테스트 안의 가짜다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_projects import (
    DEFINITIONS_LOOKUP,
    DEFINITIONS_STORE,
    KIND_CONTRIBUTIONS,
    PROJECTS_SPACES,
    ProjectsModule,
)
from agent_console_modkit import (
    Assembly,
    BaseServices,
    KindContribution,
    ModuleContext,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    DEFAULT_KINDS,
    DefinitionKind,
    FileDefinitionStore,
    contributed_kinds,
)

TOKEN = "t" * 32
API = "/api/v1"
SPACE_FOLDER = ".agent-console"
"""프로젝트 공간 정의가 놓이는 폴더(프로젝트 폴더 기준)."""

NOTE_TEMPLATE = DefinitionKind(name="note-template", directory="note-templates")
NOTE = DefinitionKind(name="note", directory="notes", library=False)

DOCS: dict[str, dict[str, Any]] = {
    "graph": {"id": "g", "name": "팀", "nodes": [], "edges": []},
    "agent": {"id": "a", "name": "에이", "backend": "fake-agent"},
    "resource": {"id": "r", "name": "지침", "type": "instructions", "config": {}},
    "note-template": {"id": "t", "name": "틀"},
}
"""저장소로 저장할 항목(종류 → 문서). 기본 종류 셋 + 라이브러리 기여 종류 하나."""

BUILTIN = ("graph", "agent", "resource")


def _contributor() -> Any:
    def build(ctx: ModuleContext) -> None:
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(NOTE_TEMPLATE))
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(NOTE))

    return fake_module("kinds", kind="testing", provides=[KIND_CONTRIBUTIONS], on_build=build)


def _library_module(root: Path) -> Any:
    def build(ctx: ModuleContext) -> None:
        extra = contributed_kinds(
            ctx.ports(KIND_CONTRIBUTIONS),
            reserved=[k.name for k in DEFAULT_KINDS],
            library_only=True,
        )
        store = FileDefinitionStore(root, [*DEFAULT_KINDS, *extra])
        ctx.provide(DEFINITIONS_STORE, store)
        ctx.provide(DEFINITIONS_LOOKUP, store)

    return fake_module(
        "library",
        kind="testing",
        provides=[DEFINITIONS_STORE, DEFINITIONS_LOOKUP],
        optional=[KIND_CONTRIBUTIONS],
        on_build=build,
    )


def _assembly(tmp_path: Path) -> Assembly:
    mods = [
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
        _library_module(tmp_path / "ws"),
        _contributor(),
    ]
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    opts = {"mod-projects": {"folder_dialog": {"include_default_providers": False}}}
    return assemble(mods, ModulesConfig(options=opts), base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _items(client: TestClient, **params: str) -> dict[tuple[str, str], dict[str, Any]]:
    response = client.get(f"{API}/projects/copy/items", params=params)
    assert response.status_code == 200, response.text
    return {(i["kind"], i["id"]): i for i in response.json()}


def _assert_saved_at(items: Mapping[tuple[str, str], Mapping[str, Any]], *, after: float) -> None:
    for key, item in items.items():
        saved_at = item["saved_at"]
        assert isinstance(saved_at, float), (key, item)
        assert saved_at >= after - 1, (key, saved_at, after)  # 파일 시각 해상도 여유 1초


def _write_external(folder: Path, directory: str, item_id: str, body: str) -> Path:
    """저장소를 거치지 않고 파일을 넣는다(사람이 편집기로 만든 것처럼)."""
    path = folder / directory / f"{item_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_library_items_fill_saved_at_for_builtin_and_contributed_kinds(tmp_path: Path) -> None:
    started = _now(tmp_path)
    assembly = _assembly(tmp_path)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    assert lib is not None
    for kind, doc in DOCS.items():
        lib.create(kind, doc)
    # 바깥에서 넣은 기본 종류 파일(저장 기록 없음)
    _write_external(tmp_path / "ws", "agents", "outside", "id: outside\nname: 밖\nbackend: x\n")
    with _client(assembly) as client:
        items = _items(client)
        assert set(items) == {
            ("graph", "g"),
            ("agent", "a"),
            ("agent", "outside"),
            ("resource", "r"),
            ("note-template", "t"),
        }
        _assert_saved_at(items, after=started)
        for kind in (*BUILTIN, "note-template"):  # 종류를 골라도 같다
            only = _items(client, kind=kind)
            assert only
            assert {k for k, _ in only} == {kind}
            _assert_saved_at(only, after=started)


def test_project_items_fill_saved_at_for_builtin_and_contributed_kinds(tmp_path: Path) -> None:
    started = _now(tmp_path)
    assembly = _assembly(tmp_path)
    folder = tmp_path / "work" / "pa"
    folder.mkdir(parents=True)
    with _client(assembly) as client:
        response = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert response.status_code == 201, response.text
        spaces: Any = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        space = spaces.open("pa").definitions
        for kind, doc in DOCS.items():
            space.create(kind, doc)
        # 프로젝트 전용 기여 종류(library=False)
        space.create("note", {"id": "n", "name": "노트", "template": "t"})
        root = folder / SPACE_FOLDER
        _write_external(root, "graphs", "hand", "id: hand\nname: 손\nnodes: []\nedges: []\n")
        _write_external(root, "notes", "hand-note", "id: hand-note\nname: 손 노트\n")
        items = _items(client, project="pa")
        assert set(items) == {
            ("graph", "g"),
            ("graph", "hand"),
            ("agent", "a"),
            ("resource", "r"),
            ("note-template", "t"),
            ("note", "n"),
            ("note", "hand-note"),
        }
        _assert_saved_at(items, after=started)
        for kind in (*BUILTIN, "note-template", "note"):
            only = _items(client, project="pa", kind=kind)
            assert only
            assert {k for k, _ in only} == {kind}
            _assert_saved_at(only, after=started)


def _now(tmp_path: Path) -> float:
    """파일 시스템 기준 지금 시각(저장 시각과 파일 수정 시각을 같은 시계로 비교)."""
    probe = tmp_path / ".clock"
    probe.write_text("", encoding="utf-8")
    return os.stat(probe).st_mtime
