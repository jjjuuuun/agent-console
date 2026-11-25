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
    KindContribution(NOTE, references=_note_refs, title="노트"),
    KindContribution(PRIVATE),
)


def _contributor(items: Sequence[KindContribution[Any]] = CONTRIBUTIONS) -> Any:
    def build(ctx: ModuleContext) -> None:
        for item in items:
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


def _assembly(
    tmp_path: Path,
    *,
    contributions: bool,
    items: Sequence[KindContribution[Any]] = CONTRIBUTIONS,
    options: Mapping[str, Any] | None = None,
) -> Assembly:
    mods: list[Any] = [
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
        _library_module(tmp_path / "ws"),
    ]
    if contributions:
        mods.append(_contributor(items))
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    opts = {
        "mod-projects": {"folder_dialog": {"include_default_providers": False}, **(options or {})}
    }
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
        # 방향 중립 문구: 대상(공용 구성)을 이름으로 말한다(묶음 4b V3).
        assert back["warnings"][0]["message"] == (
            "note/n1은(는) 공용 구성에 둘 수 없는 종류라 뺐습니다."
        )
        assert back["warnings"][0]["details"] == {"kind": "note", "id": "n1"}
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
            "title": None,  # 기여가 표시 이름을 주지 않으면 null(화면은 종류 이름)
            "deletable": False,  # 기여가 삭제 수단(``delete``)을 주지 않음
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
        assert project["note"] == {
            "kind": "note",
            "library": False,
            "portable": True,
            "title": "노트",  # 기여 ``title``(검증 11/07 B)
            "deletable": False,
        }
        assert "private" not in project  # portable=False 기여는 프로젝트 공간에 없다
        assert client.get(f"{API}/projects/copy/items?project=pa&kind=note").json() == []
        assert client.get(f"{API}/projects/copy/kinds?project=zz").status_code == 404
        assert client.get(f"{API}/projects/copy/kinds?project=..").status_code == 404


def test_copy_kinds_titles_for_builtin_kinds_fu18(tmp_path: Path) -> None:
    """FU.18: 기본 종류도 ``CopyKindInfo.title``을 채운다(종류 데이터 ``DefinitionKind.title``).

    기여의 ``title``이 종류 데이터보다 먼저이고, 둘 다 없으면 null이다. 프로젝트 모듈은 종류
    이름·문구를 모른다(기대값도 종류 데이터에서 읽는다).
    """
    titled = DefinitionKind(name="memo", directory="memos", title="메모")
    both = DefinitionKind(name="memo2", directory="memos2", title="종류 이름")
    items = (*CONTRIBUTIONS, KindContribution(titled), KindContribution(both, title="기여 이름"))
    assembly = _assembly(tmp_path, contributions=True, items=items)
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        for query in ("", "?project=pa"):
            got = {
                k["kind"]: k["title"]
                for k in client.get(f"{API}/projects/copy/kinds{query}").json()
            }
            builtin = {k.name: k.title for k in DEFAULT_KINDS if not k.is_singleton}
            assert builtin
            assert all(builtin.values())
            assert {name: got[name] for name in builtin} == builtin
            assert got["memo"] == "메모"  # 기여 title 없음 → 종류 데이터
            assert got["memo2"] == "기여 이름"  # 기여 title이 먼저
            assert got["note-template"] is None  # 둘 다 없음 → null


def test_copy_plan_suggests_rename_for_reserved_ids(tmp_path: Path) -> None:
    """FU.6: 기여 종류 데이터의 예약어 id(``reserved_ids``)로 들어오는 항목은 새 id를 제안한다."""
    guarded = DefinitionKind(
        name="guarded", directory="guarded", reserved_ids=("check", "variables")
    )
    assembly = _assembly(
        tmp_path, contributions=True, items=(*CONTRIBUTIONS, KindContribution(guarded))
    )
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("guarded", {"id": "check", "name": "체크"})
    lib.create("guarded", {"id": "plain", "name": "보통"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        plan = _plan(client, None, "pa", [("guarded", "check"), ("guarded", "plain")])
        actions = {i["id"]: i["default_action"] for i in plan["items"]}
        assert actions == {"check": "rename", "plain": "copy"}
        found = [w for w in plan["warnings"] if w["code"] == "project.copy_reserved_id"]
        assert [w["details"] for w in found] == [
            {
                "kind": "guarded",
                "id": "check",
                "reserved": ["check", "variables"],
                "suggested_id": "check-2",
            }
        ]
        assert "check-2" in found[0]["message"]
        assert "프로젝트" in found[0]["message"]
        items = [
            {
                "kind": i["kind"],
                "id": i["id"],
                "action": i["default_action"],
                "source_version": i["source_version"],
                "target_version": i["target_version"],
                **({"new_id": "check-2"} if i["default_action"] == "rename" else {}),
            }
            for i in plan["items"]
        ]
        response = client.post(
            f"{API}/projects/copy/apply",
            json={"source": {"project_id": None}, "target": {"project_id": "pa"}, "items": items},
        )
        assert response.status_code == 200, response.text
        assert [i["status"] for i in response.json()["items"]] == ["renamed", "copied"]
        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        pa = spaces.open("pa").definitions
        assert sorted(pa.list_ids("guarded")) == ["check-2", "plain"]


def _rename_request(
    target: str | None, plan: Mapping[str, Any], new_ids: Mapping[tuple[str, str], str]
) -> dict[str, Any]:
    return {
        "source": {"project_id": None},
        "target": {"project_id": target},
        "items": [
            {
                "kind": i["kind"],
                "id": i["id"],
                "action": "rename",
                "new_id": new_ids[(i["kind"], i["id"])],
                "source_version": i["source_version"],
                "target_version": i["target_version"],
            }
            for i in plan["items"]
        ],
    }


# 예약어는 종류 데이터(``DefinitionKind.reserved_ids``)에서 온다 — 코드 상수에 없는 말을 쓴다.
GUARDED = DefinitionKind(name="guarded", directory="guarded", reserved_ids=("check", "variables"))
MEMO = DefinitionKind(name="memo", directory="memos", reserved_ids=("zeta-route",))
OPEN = DefinitionKind(name="open", directory="open")
RESERVED_ITEMS = (*CONTRIBUTIONS, *(KindContribution(k) for k in (GUARDED, MEMO, OPEN)))


def test_copy_apply_rejects_reserved_rename_ids(tmp_path: Path) -> None:
    """REL.6: 사용자가 넣은 rename 새 id가 그 종류의 예약어면 422, 아무것도 쓰지 않는다."""
    assembly = _assembly(tmp_path, contributions=True, items=RESERVED_ITEMS)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("guarded", {"id": "plain", "name": "보통"})
    lib.create("memo", {"id": "m", "name": "메모"})
    lib.create("open", {"id": "o", "name": "열림"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        plan = _plan(client, None, "pa", [("guarded", "plain"), ("memo", "m"), ("open", "o")])
        assert not [w for w in plan["warnings"] if w["code"] == "project.copy_reserved_id"]
        new_ids = {("guarded", "plain"): "Check", ("memo", "m"): "zeta-route", ("open", "o"): "o2"}
        response = client.post(
            f"{API}/projects/copy/apply", json=_rename_request("pa", plan, new_ids)
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_failed"
        issues = error["details"]["issues"]
        assert [(i["code"], i["severity"], i["path"]) for i in issues] == [
            ("project.copy_reserved_id", "error", "/items/0/new_id"),
            ("project.copy_reserved_id", "error", "/items/1/new_id"),
        ]
        assert [i["details"] for i in issues] == [
            {
                "kind": "guarded",
                "id": "plain",
                "action": "rename",
                "target_id": "Check",
                "new_id": "Check",
                "reserved": ["check", "variables"],
                "suggested_id": "Check-2",
            },
            {
                "kind": "memo",
                "id": "m",
                "action": "rename",
                "target_id": "zeta-route",
                "new_id": "zeta-route",
                "reserved": ["zeta-route"],
                "suggested_id": "zeta-route-2",
            },
        ]
        assert "Check-2" in issues[0]["message"]
        assert "프로젝트" in issues[0]["message"]
        assert issues[0]["message"] in error["message"]
        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        pa = spaces.open("pa").definitions
        for kind in ("guarded", "memo", "open"):
            assert pa.list_ids(kind) == []  # 하나라도 걸리면 아무것도 쓰지 않는다

        # 예약어가 없는 종류는 같은 말도 받는다(목록은 종류 데이터에서 온다)
        only_open = {**plan, "items": [i for i in plan["items"] if i["kind"] == "open"]}
        ok = _rename_request("pa", only_open, {("open", "o"): "check"})
        response = client.post(f"{API}/projects/copy/apply", json=ok)
        assert response.status_code == 200, response.text
        assert [i["status"] for i in response.json()["items"]] == ["renamed"]
        assert pa.list_ids("open") == ["check"]


def test_copy_apply_reserved_rename_message_is_configurable(tmp_path: Path) -> None:
    """REL.6: 문구는 ``modules.options.mod-projects.messages``의 키로 바꾼다(코드는 그대로)."""
    assembly = _assembly(
        tmp_path,
        contributions=True,
        items=RESERVED_ITEMS,
        options={"messages": {"project.copy_reserved_id.rename": "${id} 금지 → ${suggested}"}},
    )
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("guarded", {"id": "plain", "name": "보통"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        plan = _plan(client, None, "pa", [("guarded", "plain")])
        response = client.post(
            f"{API}/projects/copy/apply",
            json=_rename_request("pa", plan, {("guarded", "plain"): "variables"}),
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["message"] == "variables 금지 → variables-2"
        assert error["details"]["issues"][0]["code"] == "project.copy_reserved_id"


def test_copy_apply_rejects_reserved_source_id_kept_as_is(tmp_path: Path) -> None:
    """REL.6: 계획 경고를 두고 예약어 원본 id를 copy로 그대로 쓰면 422, 아무것도 쓰지 않는다."""
    assembly = _assembly(tmp_path, contributions=True, items=RESERVED_ITEMS)
    lib: Any = assembly.port(DEFINITIONS_STORE)
    lib.create("guarded", {"id": "check", "name": "체크"})
    lib.create("open", {"id": "check", "name": "열림"})
    with _client(assembly) as client:
        _register(client, tmp_path / "work" / "pa")
        plan = _plan(client, None, "pa", [("guarded", "check"), ("open", "check")])
        items = [
            {
                "kind": i["kind"],
                "id": i["id"],
                "action": "copy",
                "source_version": i["source_version"],
                "target_version": i["target_version"],
            }
            for i in plan["items"]
        ]
        response = client.post(
            f"{API}/projects/copy/apply",
            json={"source": {"project_id": None}, "target": {"project_id": "pa"}, "items": items},
        )
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        [issue] = error["details"]["issues"]  # 예약어가 없는 종류(open)는 같은 말도 통과
        assert issue["code"] == "project.copy_reserved_id"
        assert issue["path"] == "/items/0/id"
        assert issue["details"]["action"] == "copy"
        assert issue["details"]["target_id"] == "check"
        assert issue["details"]["suggested_id"] == "check-2"
        assert error["message"] == issue["message"]
        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        pa = spaces.open("pa").definitions
        assert pa.list_ids("guarded") == []
        assert pa.list_ids("open") == []
