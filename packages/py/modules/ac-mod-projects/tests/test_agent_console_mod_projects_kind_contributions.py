"""6R.5: 정의 종류 기여(X44)를 받은 프로젝트 공간 종류·복사 계획(참조 닫힘).

라이브러리 저장소는 이 테스트 안의 작은 정의 모듈이다(정의 모듈처럼 ``library=True`` 기여 종류를
더한다). 기여 모듈도 가짜다. 프로젝트 모듈은 둘 다 import하지 않고 포트 이름으로만 받는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    library_kinds,
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

NOTE_TEMPLATE = DefinitionKind(name="note-template", directory="note-templates")
NOTE = DefinitionKind(name="note", directory="notes", library=False)
PRIVATE = DefinitionKind(name="private", directory="private", portable=False)


def _template_refs(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [("agent", str(doc["agent"]))] if "agent" in doc else []


def _note_refs(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [("note-template", str(doc["template"]))] if "template" in doc else []


CONTRIBUTIONS = (
    KindContribution(NOTE_TEMPLATE, references=_template_refs),
    KindContribution(NOTE, references=_note_refs),
    KindContribution(PRIVATE),
)


def _contributor() -> Any:
    def build(ctx: ModuleContext) -> None:
        for item in CONTRIBUTIONS:
            ctx.provide(KIND_CONTRIBUTIONS, item)

    return fake_module("kinds", kind="testing", provides=[KIND_CONTRIBUTIONS], on_build=build)


def _library_module(root: Path) -> Any:
    """라이브러리 정의 저장소(기본 종류 + ``library=True`` 기여 종류)."""

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


def _assembly(tmp_path: Path, *, contributions: bool) -> Assembly:
    mods: list[Any] = [
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
        _library_module(tmp_path / "ws"),
    ]
    if contributions:
        mods.append(_contributor())
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


def _register(client: TestClient, folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    response = client.post(f"{API}/projects", json={"folder": str(folder)})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _plan(
    client: TestClient, source: str | None, target: str | None, items: Sequence[tuple[str, str]]
) -> dict[str, Any]:
    response = client.post(
        f"{API}/projects/copy/plan",
        json={
            "source": {"project_id": source},
            "target": {"project_id": target},
            "items": [{"kind": k, "id": i} for k, i in items],
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _apply(
    client: TestClient, source: str | None, target: str | None, plan: Mapping[str, Any]
) -> dict[str, Any]:
    items = [
        {
            "kind": i["kind"],
            "id": i["id"],
            "action": i["default_action"] or "overwrite",
            "source_version": i["source_version"],
            "target_version": i["target_version"],
        }
        for i in plan["items"]
    ]
    response = client.post(
        f"{API}/projects/copy/apply",
        json={"source": {"project_id": source}, "target": {"project_id": target}, "items": items},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _rows(plan: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    return [(i["kind"], i["id"], i["reason"]) for i in plan["items"]]


def test_library_kinds_diff_without_contributions() -> None:
    """차등: 기여가 없으면 6R.5 전 계산과 같다(저장소 없음 = 기본 종류)."""
    assert library_kinds(None) == list(DEFAULT_KINDS)
    assert library_kinds(None, []) == list(DEFAULT_KINDS)
    store = FileDefinitionStore("unused", DEFAULT_KINDS)
    assert [k.name for k in library_kinds(store)] == [k.name for k in DEFAULT_KINDS]


def test_library_kinds_adds_contributions_once() -> None:
    lib = FileDefinitionStore("unused", [*DEFAULT_KINDS, NOTE_TEMPLATE])
    names = [k.name for k in library_kinds(lib, CONTRIBUTIONS)]
    assert names == [*(k.name for k in DEFAULT_KINDS), "note-template", "note", "private"]
    assert [k.name for k in library_kinds(None, CONTRIBUTIONS)][-3:] == [
        "note-template",
        "note",
        "private",
    ]


def test_project_view_kinds(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path, contributions=False)) as client:
        before = _register(client, tmp_path / "work" / "app")["kinds"]
    assert before == ["graph", "agent", "resource"]
    with _client(_assembly(tmp_path / "2", contributions=True)) as client:
        after = _register(client, tmp_path / "2" / "work" / "app")["kinds"]
    # 옮길 수 있는 것만(portable=False 기여는 빠짐), library=False 종류도 공간에는 있다.
    assert after == [*before, "note-template", "note"]


def test_copy_with_contributed_kinds(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, contributions=True)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    assert lib is not None
    assert "note" not in lib.kinds()
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    lib.create("note-template", {"id": "t1", "name": "틀", "agent": "a"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        _register(client, tmp_path / "work" / "pb")

        # 라이브러리 → 프로젝트: 기여 종류의 참조 추출로 참조 닫힘(에이전트).
        plan = _plan(client, None, "pa", [("note-template", "t1")])
        assert _rows(plan) == [
            ("note-template", "t1", "requested"),
            ("agent", "a", "referenced"),
        ]
        result = _apply(client, None, "pa", plan)
        assert [i["status"] for i in result["items"]] == ["copied", "copied"]

        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        pa = spaces.open("pa").definitions
        assert (tmp_path / "work" / "pa" / ".agent-console" / "note-templates" / "t1.yaml").exists()
        assert pa.list_versions("note-template", "t1")[-1].message.startswith("가져옴: library ")

        # library=False 종류는 프로젝트 공간에 저장·버전이 된다.
        pa.create("note", {"id": "n1", "name": "노트", "template": "t1"})
        assert (tmp_path / "work" / "pa" / ".agent-console" / "notes" / "n1.yaml").exists()
        assert len(pa.list_versions("note", "n1")) == 1

        # 프로젝트 → 프로젝트: 노트 → 틀 → 에이전트(전이 닫힘).
        plan = _plan(client, "pa", "pb", [("note", "n1")])
        assert _rows(plan) == [
            ("note", "n1", "requested"),
            ("note-template", "t1", "referenced"),
            ("agent", "a", "referenced"),
        ]
        result = _apply(client, "pa", "pb", plan)
        assert {i["status"] for i in result["items"]} == {"copied"}
        pb = spaces.open("pb").definitions
        assert pb.get("note", "n1").version_hash == pa.get("note", "n1").version_hash

        # 프로젝트 → 라이브러리: library=False 종류는 뺀다(경고), 참조된 틀은 남는다.
        back = _plan(client, "pa", None, [("note", "n1")])
        assert back["items"] == []
        assert [w["code"] for w in back["warnings"]] == ["project.copy_kind_not_portable"]
        assert not (tmp_path / "ws" / "notes").exists()


def test_contribution_references_without_reference_providers(tmp_path: Path) -> None:
    """``definitions.references`` 제공자가 없어도 기여 참조만으로 닫힌다(정보 이슈 없음)."""
    assembly = _assembly(tmp_path, contributions=True)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    assert lib is not None
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        plan = _plan(client, None, "pa", [("agent", "a")])
        assert "project.references_unavailable" not in [w["code"] for w in plan["warnings"]]
    plain = _assembly(tmp_path / "2", contributions=False)
    lib2: Any = plain.port(DEFINITIONS_STORE)
    assert lib2 is not None
    lib2.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    with _client(plain) as client:
        _register(client, tmp_path / "2" / "work" / "pa")
        plan = _plan(client, None, "pa", [("agent", "a")])
        assert "project.references_unavailable" in [w["code"] for w in plan["warnings"]]


def test_copy_kinds_and_items_follow_contributions(tmp_path: Path) -> None:
    """6R.20a(6R.20c 입력): 복사 대화상자 메타데이터 — 기여한 임의 이름 종류가 표 없이 나온다."""
    assembly = _assembly(tmp_path, contributions=True)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    assert lib is not None
    lib.create("agent", {"id": "a", "name": "에이", "description": "설명", "backend": "fake-agent"})
    lib.create("note-template", {"id": "t1", "name": "틀"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        kinds = client.get(f"{API}/projects/copy/kinds").json()
        by_kind = {k["kind"]: k for k in kinds}
        assert by_kind["note-template"] == {
            "kind": "note-template",
            "library": True,
            "portable": True,
        }
        assert "note" not in by_kind  # library=False 종류는 라이브러리에 없다
        assert "settings" not in by_kind  # 싱글턴은 복사 대상이 아니다
        assert by_kind["agent"]["portable"] is True

        items = client.get(f"{API}/projects/copy/items").json()
        assert {(i["kind"], i["id"]) for i in items} >= {("agent", "a"), ("note-template", "t1")}
        only = client.get(f"{API}/projects/copy/items", params={"kind": "note-template"}).json()
        assert [(i["kind"], i["id"], i["name"]) for i in only] == [("note-template", "t1", "틀")]
        agent = client.get(f"{API}/projects/copy/items", params={"kind": "agent"}).json()
        assert agent[0]["description"] == "설명"
        assert isinstance(agent[0]["saved_at"], float)
        missing = client.get(f"{API}/projects/copy/items", params={"kind": "nope"})
        assert missing.status_code == 404

        project = {k["kind"]: k for k in client.get(f"{API}/projects/copy/kinds?project=pa").json()}
        assert project["note"] == {"kind": "note", "library": False, "portable": True}
        assert "private" not in project  # portable=False 기여는 프로젝트 공간에 없다
        assert client.get(f"{API}/projects/copy/items?project=pa&kind=note").json() == []
        assert client.get(f"{API}/projects/copy/kinds?project=zz").status_code == 404
        assert client.get(f"{API}/projects/copy/kinds?project=..").status_code == 404
