"""6R.5 통합: 정의 종류 기여(X44) + 정의·버전·프로젝트 모듈.

기여 모듈은 이 테스트 안의 작은 모듈이다(6R.13 ``mod-sdd``가 같은 길로 종류 둘을 기여한다).
라이브러리 경로에서 ``library=False`` 종류는 404, 프로젝트 공간(``?project=``)에서는
저장·버전·복사가 된다. 기여가 없으면 종류 목록·복사 결과가 전과 같다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_definitions import DEFINITIONS_STORE, KIND_CONTRIBUTIONS, definition_kinds
from agent_console_mod_definitions import module as definitions
from agent_console_mod_projects import PROJECTS_SPACES, ProjectsModule
from agent_console_mod_versions import module as versions
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
from agent_console_store import DefinitionKind

TOKEN = "t" * 32
API = "/api/v1"

TEMPLATE = DefinitionKind(
    name="doc-template", directory="doc-templates", content_field="content", require_version=True
)
DOC = DefinitionKind(name="doc", directory="docs", library=False)


def _template_refs(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [("agent", str(a)) for a in doc.get("agents", [])]


def _contributor() -> Any:
    def build(ctx: ModuleContext) -> None:
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(TEMPLATE, references=_template_refs))
        ctx.provide(KIND_CONTRIBUTIONS, KindContribution(DOC, summary_fields=("state",)))

    return fake_module("doc-kinds", kind="testing", provides=[KIND_CONTRIBUTIONS], on_build=build)


COLLECTIONS = [
    {"path": "/agents", "kind": "agent", "id_param": "agent_id"},
    {"path": "/doc-templates", "kind": "doc-template", "id_param": "template_id"},
    {"path": "/docs", "kind": "doc", "id_param": "doc_id"},
]


def _assembly(tmp_path: Path, *, contributions: bool = True) -> Assembly:
    mods: list[Any] = [
        definitions,
        versions,
        ProjectsModule(dialog_providers=[], platform="linux", which=lambda _n: None),
    ]
    if contributions:
        mods.append(_contributor())
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    options: dict[str, dict[str, Any]] = {
        "mod-versions": {"collections": COLLECTIONS},
        "mod-projects": {"folder_dialog": {"include_default_providers": False}},
    }
    return assemble(mods, ModulesConfig(options=options), base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    client = TestClient(
        create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    )
    client.headers["X-Console-Token"] = TOKEN
    return client


def _register(client: TestClient, folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    response = client.post(f"{API}/projects", json={"folder": str(folder)})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _copy(
    client: TestClient, source: str | None, target: str | None, items: list[tuple[str, str]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    spaces = {"source": {"project_id": source}, "target": {"project_id": target}}
    plan = client.post(
        f"{API}/projects/copy/plan",
        json={**spaces, "items": [{"kind": k, "id": i} for k, i in items]},
    ).json()
    apply = [
        {
            "kind": i["kind"],
            "id": i["id"],
            "action": i["default_action"] or "overwrite",
            "source_version": i["source_version"],
            "target_version": i["target_version"],
        }
        for i in plan["items"]
    ]
    result = client.post(f"{API}/projects/copy/apply", json={**spaces, "items": apply}).json()
    return plan, result


def test_no_contributions_is_unchanged(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, contributions=False)
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    assert store.kinds() == [k.name for k in definition_kinds()]
    with _client(assembly) as client:
        view = _register(client, tmp_path / "work" / "p")
        assert view["kinds"] == ["graph", "agent", "resource"]
        assert client.get(f"{API}/doc-templates/x/versions").status_code == 404


def test_contributed_kinds_end_to_end(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    lib = assembly.port(DEFINITIONS_STORE)
    assert lib is not None
    with _client(assembly) as client:
        assert _register(client, tmp_path / "work" / "pa")["kinds"][-2:] == ["doc-template", "doc"]
        _register(client, tmp_path / "work" / "pb")

        # 라이브러리: 틀 저장·본문·버전.
        assert client.post(f"{API}/agents", json={"id": "rev", "name": "리뷰어"}).status_code == 201
        made = lib.create(
            "doc-template",
            {"id": "t1", "name": "틀", "agents": ["rev"], "content": {"file": "a.md"}},
        )
        lib.write_content("doc-template", "t1", b"# A", expected_version=made.version_hash)
        assert (tmp_path / "ws" / "doc-templates" / "t1" / "a.md").read_bytes() == b"# A"
        listed = client.get(f"{API}/doc-templates/t1/versions")
        assert listed.status_code == 200
        assert len(listed.json()) == 2

        # 라이브러리 경로의 library=False 종류 → 404(모르는 종류).
        missing = client.get(f"{API}/docs/d1/versions")
        assert missing.status_code == 404, missing.text

        # 라이브러리 → 프로젝트 복사(참조 닫힘: 기여 종류의 참조 추출).
        plan, result = _copy(client, None, "pa", [("doc-template", "t1")])
        assert [(i["kind"], i["id"], i["reason"]) for i in plan["items"]] == [
            ("doc-template", "t1", "requested"),
            ("agent", "rev", "referenced"),
        ]
        assert [i["status"] for i in result["items"]] == ["copied", "copied"]
        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        pa = spaces.open("pa").definitions
        assert pa.read_content("doc-template", "t1") == b"# A"

        # 프로젝트 공간: library=False 종류 저장·버전·요약 필드.
        pa.create("doc", {"id": "d1", "name": "문서", "state": "draft"})
        assert (tmp_path / "work" / "pa" / ".agent-console" / "docs" / "d1.yaml").exists()
        versions_pa = client.get(f"{API}/docs/d1/versions?project=pa")
        assert versions_pa.status_code == 200
        assert len(versions_pa.json()) == 1
        assert pa.summaries("doc")[0].extra == {"state": "draft"}

        # 프로젝트 → 프로젝트 복사 / 프로젝트 → 라이브러리는 뺀다.
        _, result = _copy(client, "pa", "pb", [("doc", "d1")])
        assert [i["status"] for i in result["items"]] == ["copied"]
        back, _ = _copy(client, "pa", None, [("doc", "d1")])
        assert back["items"] == []
        assert not (tmp_path / "ws" / "docs").exists()
        assert "doc" not in lib.kinds()
