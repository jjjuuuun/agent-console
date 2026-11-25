"""FU.13: 종류 공통 거꾸로 참조 ``GET /projects/copy/items/{kind}/{id}/references?project=``.

삭제 확인 창의 "이 구성을 쓰는 구성" 목록이다. 프로젝트 모듈은 종류 이름·참조 필드를 모르고,
``definitions.references``(X25) 제공자와 종류 기여(X44)의 ``references``로 찾는다. 저장소·제공자·
기여는 이 테스트 안의 가짜이고 종류 이름도 시험용 이름이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, CopyItemReferences
from agent_console_mod_projects import (
    DEFINITIONS_LOOKUP,
    DEFINITIONS_REFERENCES,
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
ITEMS = f"{API}/projects/copy/items"

NOTE = DefinitionKind(name="zz-note", directory="zz-notes")


def _note_refs(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    """기여 종류의 참조: 노트가 쓰는 에이전트(``agent`` 필드)."""
    return [("agent", str(doc["agent"]))] if "agent" in doc else []


def _uses(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``definitions.references`` 가짜: 문서의 ``zz_uses`` = ``[[종류, id], ...]``(종류 무관)."""
    return [(str(k), str(i)) for k, i in document.get("zz_uses", [])]


def _modules(root: Path, *, references: bool, contributions: bool) -> list[Any]:
    def library(ctx: ModuleContext) -> None:
        extra = contributed_kinds(
            ctx.ports(KIND_CONTRIBUTIONS),
            reserved=[k.name for k in DEFAULT_KINDS],
            library_only=True,
        )
        store = FileDefinitionStore(root, [*DEFAULT_KINDS, *extra])
        ctx.provide(DEFINITIONS_STORE, store)
        ctx.provide(DEFINITIONS_LOOKUP, store)

    mods: list[Any] = [
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
        fake_module(
            "library",
            kind="testing",
            provides=[DEFINITIONS_STORE, DEFINITIONS_LOOKUP],
            optional=[KIND_CONTRIBUTIONS],
            on_build=library,
        ),
    ]
    if references:

        def provide_refs(ctx: ModuleContext) -> None:
            ctx.provide(DEFINITIONS_REFERENCES, _uses)

        mods.append(
            fake_module(
                "refs", kind="testing", provides=[DEFINITIONS_REFERENCES], on_build=provide_refs
            )
        )
    if contributions:

        def provide_kind(ctx: ModuleContext) -> None:
            ctx.provide(KIND_CONTRIBUTIONS, KindContribution(NOTE, references=_note_refs))

        mods.append(
            fake_module(
                "kinds", kind="testing", provides=[KIND_CONTRIBUTIONS], on_build=provide_kind
            )
        )
    return mods


def _assembly(tmp_path: Path, *, references: bool = True, contributions: bool = True) -> Assembly:
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    opts = {"mod-projects": {"folder_dialog": {"include_default_providers": False}}}
    mods = _modules(tmp_path / "ws", references=references, contributions=contributions)
    return assemble(mods, ModulesConfig(options=opts), base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _register(client: TestClient, folder: Path) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    response = client.post(f"{API}/projects", json={"folder": str(folder)})
    assert response.status_code == 201, response.text
    project_id: str = response.json()["project"]["id"]
    return project_id


def _refs(client: TestClient, kind: str, item_id: str, project: str | None = None) -> Any:
    params = {} if project is None else {"project": project}
    return client.get(f"{ITEMS}/{kind}/{item_id}/references", params=params)


def test_referrers_from_provider_and_contribution_in_library(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    team = lib.create(
        "graph",
        {
            "schema_version": 1,
            "id": "t",
            "name": "팀",
            "description": "설명",
            "nodes": [],
            "edges": [],
            "zz_uses": [["agent", "a"]],
        },
    )
    lib.create("zz-note", {"id": "n", "name": "노트", "agent": "a"})
    lib.create("zz-note", {"id": "other", "name": "다른 노트", "agent": "b"})
    with _client(assembly) as client:
        response = _refs(client, "agent", "a")
        assert response.status_code == 200, response.text
        body = CopyItemReferences.model_validate(response.json())
        assert body.checked is True
        assert body.warnings == []
        keys = {(i.kind, i.id) for i in body.items}
        assert keys == {("graph", "t"), ("zz-note", "n")}
        graph = next(i for i in body.items if i.kind == "graph")
        assert graph.name == "팀"
        assert graph.description == "설명"
        assert graph.version == team.version_hash

        nobody = _refs(client, "agent", "zz-unused-but-missing")
        assert nobody.status_code == 404, nobody.text
        lib.create("agent", {"id": "lonely", "name": "혼자", "backend": "fake-agent"})
        lonely = _refs(client, "agent", "lonely").json()
        assert lonely == {"items": [], "checked": True, "warnings": []}


def test_project_space_sees_only_its_own_definitions(tmp_path: Path) -> None:
    """프로젝트 공간의 사본만 본다(공용 구성의 같은 id 팀은 쓰는 곳이 아니다)."""
    assembly = _assembly(tmp_path)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    lib.create("zz-note", {"id": "lib-note", "name": "공용 노트", "agent": "a"})
    with _client(assembly) as client:
        pid = _register(client, tmp_path / "work" / "pa")
        spaces: Any = assembly.port(PROJECTS_SPACES)
        store = spaces.open(pid).definitions
        store.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
        store.create("zz-note", {"id": "p-note", "name": "프로젝트 노트", "agent": "a"})

        body = _refs(client, "agent", "a", pid).json()
        assert [(i["kind"], i["id"]) for i in body["items"]] == [("zz-note", "p-note")]
        library = _refs(client, "agent", "a").json()
        assert [(i["kind"], i["id"]) for i in library["items"]] == [("zz-note", "lib-note")]


def test_without_any_extractor_reports_unchecked(tmp_path: Path) -> None:
    """참조 추출이 하나도 없으면 ``checked`` false + info ``project.references_unavailable``."""
    assembly = _assembly(tmp_path, references=False, contributions=False)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    with _client(assembly) as client:
        body = _refs(client, "agent", "a").json()
        assert body["items"] == []
        assert body["checked"] is False
        [warning] = body["warnings"]
        assert warning["code"] == "project.references_unavailable"
        assert warning["severity"] == "info"
        assert warning["details"] == {"kind": "agent", "id": "a"}


def test_contribution_references_alone_are_enough(tmp_path: Path) -> None:
    """``definitions.references`` 제공자가 없어도 기여의 ``references``로 검사한다."""
    assembly = _assembly(tmp_path, references=False, contributions=True)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    lib.create("zz-note", {"id": "n", "name": "노트", "agent": "a"})
    with _client(assembly) as client:
        body = _refs(client, "agent", "a").json()
        assert body["checked"] is True
        assert [(i["kind"], i["id"]) for i in body["items"]] == [("zz-note", "n")]


def test_errors_unknown_kind_item_and_project(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        unknown_kind = _refs(client, "zz-nope", "x")
        assert unknown_kind.status_code == 404
        assert unknown_kind.json()["error"]["code"] == "not_found"
        assert _refs(client, "agent", "missing").status_code == 404
        unknown_project = _refs(client, "agent", "a", "zz")
        assert unknown_project.status_code == 404
        assert unknown_project.json()["error"]["code"] == "project.not_found"
