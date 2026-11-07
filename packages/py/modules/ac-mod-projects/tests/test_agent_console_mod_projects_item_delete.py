"""요청 11/07 후속: 종류 공통 항목 삭제 ``DELETE /projects/copy/items/{kind}/{id}?project=``.

- 기본 종류(라이브러리 저장소 종류)는 공간 저장소에서 바로 지운다(``deletable`` true).
- 기여 종류는 기여의 ``delete`` 콜백을 부른다(있으면 ``deletable`` true, 없으면 false·400).
- 없는 항목·종류·공간은 404, ``If-Match`` 불일치는 412.

라이브러리 저장소·기여 모듈은 이 테스트 안의 가짜다(프로젝트 모듈은 포트 이름으로만 받는다).
"""

from __future__ import annotations

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
ITEMS = f"{API}/projects/copy/items"

NOTE_TEMPLATE = DefinitionKind(name="note-template", directory="note-templates")
NOTE = DefinitionKind(name="note", directory="notes", library=False)


def _contributor(calls: list[tuple[str | None, str, str | None]], built: list[Assembly]) -> Any:
    """노트(삭제 콜백 있음) + 노트 틀(삭제 수단 없음)을 기여한다.

    콜백은 조립이 끝난 뒤의 프로젝트 공간에서 지운다(실제 모듈은 자기 서비스 경로를 부른다).
    """

    def build(ctx: ModuleContext) -> None:
        def delete_note(space: str | None, item_id: str, expected: str | None) -> None:
            calls.append((space, item_id, expected))
            spaces: Any = built[0].port(PROJECTS_SPACES)
            assert spaces is not None
            assert space is not None
            spaces.open(space).definitions.delete("note", item_id, expected_version=expected)

        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(NOTE, title="노트", delete=delete_note))
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(NOTE_TEMPLATE))

    return fake_module(
        "kinds",
        kind="testing",
        provides=[KIND_CONTRIBUTIONS],
        on_build=build,
    )


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


def _assembly(tmp_path: Path, calls: list[tuple[str | None, str, str | None]]) -> Assembly:
    built: list[Assembly] = []
    mods: list[Any] = [
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
        _library_module(tmp_path / "ws"),
        _contributor(calls, built),
    ]
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    opts = {"mod-projects": {"folder_dialog": {"include_default_providers": False}}}
    built.append(assemble(mods, ModulesConfig(options=opts), base=base))
    return built[0]


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


def test_kinds_report_deletable(tmp_path: Path) -> None:
    """기본 종류와 삭제 콜백을 준 기여 종류는 true, 콜백이 없는 기여 종류는 false."""
    with _client(_assembly(tmp_path, [])) as client:
        pid = _register(client, tmp_path / "work" / "pa")
        library = {
            k["kind"]: k["deletable"] for k in client.get(f"{API}/projects/copy/kinds").json()
        }
        assert library["agent"] is True
        assert library["graph"] is True
        assert library["resource"] is True
        assert library["note-template"] is False
        project = {
            k["kind"]: k["deletable"]
            for k in client.get(f"{API}/projects/copy/kinds", params={"project": pid}).json()
        }
        assert project["note"] is True
        assert project["agent"] is True
        assert project["note-template"] is False


def test_delete_base_kind_in_library(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, [])
    lib: Any = assembly.port(DEFINITIONS_STORE)
    stored = lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    lib.create("agent", {"id": "b", "name": "비", "backend": "fake-agent"})
    with _client(assembly) as client:
        stale = client.delete(f"{ITEMS}/agent/a", headers={"If-Match": '"nope"'})
        assert stale.status_code == 412, stale.text
        assert (
            client.delete(f"{ITEMS}/agent/a", headers={"If-Match": stored.version_hash}).status_code
            == 204
        )
        assert [i["id"] for i in client.get(ITEMS, params={"kind": "agent"}).json()] == ["b"]
        assert client.delete(f"{ITEMS}/agent/b").status_code == 204
        assert client.get(ITEMS, params={"kind": "agent"}).json() == []


def test_delete_contributed_kind_calls_callback(tmp_path: Path) -> None:
    """기여 종류 항목: 기여의 ``delete``가 (공간, id, 기대 버전)으로 불리고 항목이 사라진다."""
    calls: list[tuple[str | None, str, str | None]] = []
    assembly = _assembly(tmp_path, calls)
    with _client(assembly) as client:
        pid = _register(client, tmp_path / "work" / "pa")
        spaces: Any = assembly.port(PROJECTS_SPACES)
        store = spaces.open(pid).definitions
        store.create("note", {"id": "n1", "name": "노트 하나"})
        store.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})

        gone = client.delete(f"{ITEMS}/note/n1", params={"project": pid})
        assert gone.status_code == 204, gone.text
        assert calls == [(pid, "n1", None)]
        assert client.get(ITEMS, params={"project": pid, "kind": "note"}).json() == []

        # 기본 종류는 그 프로젝트 공간 저장소에서 바로 지운다(콜백 없음).
        assert client.delete(f"{ITEMS}/agent/a", params={"project": pid}).status_code == 204
        assert client.get(ITEMS, params={"project": pid, "kind": "agent"}).json() == []
        assert calls == [(pid, "n1", None)]


def test_delete_errors(tmp_path: Path) -> None:
    """없는 항목·종류·공간 404, 지울 수 없는 종류 400(``not_deletable``), 콜백은 불리지 않는다."""
    calls: list[tuple[str | None, str, str | None]] = []
    assembly = _assembly(tmp_path, calls)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("note-template", {"id": "t1", "name": "틀"})
    with _client(assembly) as client:
        pid = _register(client, tmp_path / "work" / "pa")

        missing = client.delete(f"{ITEMS}/note/zz", params={"project": pid})
        assert missing.status_code == 404, missing.text
        assert client.delete(f"{ITEMS}/agent/zz").status_code == 404
        unknown_kind = client.delete(f"{ITEMS}/nope/x")
        assert unknown_kind.status_code == 404
        assert unknown_kind.json()["error"]["code"] == "not_found"
        # note는 library=False라 라이브러리 공간에는 없는 종류다.
        assert client.delete(f"{ITEMS}/note/x").status_code == 404
        unknown_project = client.delete(f"{ITEMS}/agent/a", params={"project": "zz"})
        assert unknown_project.status_code == 404
        assert unknown_project.json()["error"]["code"] == "project.not_found"

        refused = client.delete(f"{ITEMS}/note-template/t1")
        assert refused.status_code == 400, refused.text
        assert refused.json()["error"]["details"] == {
            "kind": "note-template",
            "reason": "not_deletable",
        }
        assert [i["id"] for i in client.get(ITEMS, params={"kind": "note-template"}).json()] == [
            "t1"
        ]
        assert calls == []
