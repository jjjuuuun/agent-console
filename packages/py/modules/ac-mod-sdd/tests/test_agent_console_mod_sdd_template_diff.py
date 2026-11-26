"""P1.17 문서 틀 버전 비교 REST(design §1.1 B-4).

``GET /sdd/templates/{id}/versions/{a}/diff[/{b}]`` → 계약 ``DefinitionDiff``. 정의 모듈이 꺼진
조립(단독 루트 틀)·공간 이름(``?project=``)·라이브러리 저장소, 뼈대 파일 변경, 비밀 위치 가림,
OpenAPI 경로.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import DefinitionDiff
from agent_console_mod_sdd.testing import SimpleSpace, library_module, spaces_module
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS
from agent_console_sdd import LocalSpecFiles
from agent_console_store import InMemoryDefinitionStore

API = "/api/v1"
T = f"{API}/sdd/templates"
SECRET = "sk-ant-api03-" + "a" * 40


def _edit(client: TestClient, tid: str, query: str = "") -> tuple[str, str]:
    """만들기 → 설명 고치기 → 파일 쓰기. (첫 버전, 마지막 버전)."""
    made = client.post(f"{T}{query}", json={"name": "틀", "id": tid, "description": "처음"})
    assert made.status_code == 201, made.text
    first = made.headers["etag"].strip('"')
    doc = {**made.json(), "description": "둘째"}
    saved = client.put(f"{T}/{tid}{query}", json=doc, headers={"If-Match": made.headers["etag"]})
    assert saved.status_code == 200, saved.text
    wrote = client.put(
        f"{T}/{tid}/files/req.md{query}",
        content=b"# req\n",
        headers={"If-Match": saved.headers["etag"]},
    )
    assert wrote.status_code == 200, wrote.text
    return first, wrote.headers["etag"].strip('"')


def _diff(client: TestClient, path: str) -> DefinitionDiff:
    res = client.get(path)
    assert res.status_code == 200, res.text
    return DefinitionDiff.model_validate(res.json())


def test_diff_on_standalone_root(standalone: tuple[TestClient, Path]) -> None:
    """정의 모듈이 꺼진 조립: 단독 루트 틀의 버전 → 현재·두 버전 비교, 뼈대 파일 변경."""
    client, _root = standalone
    first, last = _edit(client, "plan")
    now = _diff(client, f"{T}/plan/versions/{first}/diff")
    assert (now.kind, now.id, now.from_hash, now.to_hash) == ("spec-template", "plan", first, last)
    changes = {(c.op, c.path): (c.before, c.after) for c in now.changes}
    assert changes[("replace", "/description")] == ("처음", "둘째")
    assert [(c.path, c.before_hash is None) for c in now.content_changes] == [("req.md", True)]

    both = _diff(client, f"{T}/plan/versions/{first}/diff/{last}")
    assert both == now
    same = _diff(client, f"{T}/plan/versions/{last}/diff")
    assert same.changes == []
    assert same.content_changes == []

    versions = [v["version_hash"] for v in client.get(f"{T}/plan/versions").json()]
    middle = versions[1]  # 설명만 바뀐 버전 → 파일 쓰기
    files_only = _diff(client, f"{T}/plan/versions/{middle}/diff/{last}")
    assert files_only.changes == []
    assert [c.path for c in files_only.content_changes] == ["req.md"]

    assert client.get(f"{T}/plan/versions/nope/diff").status_code == 404
    assert client.get(f"{T}/none/versions/{first}/diff").status_code == 404
    assert client.delete(f"{T}/plan").status_code == 204
    assert client.get(f"{T}/plan/versions/{first}/diff").status_code == 404  # 현재가 없다
    assert _diff(client, f"{T}/plan/versions/{first}/diff/{last}") == both  # 이력은 남는다


def test_diff_in_project_space(tmp_path: Path, kit: Any) -> None:
    """공간 이름이 있으면 그 공간 저장소의 버전 기록을 비교한다(단독 루트와 섞이지 않음)."""
    folder = tmp_path / "proj"
    folder.mkdir()
    store = kit.spec_store(folder / ".cfg")
    space = SimpleSpace(store=store, files=LocalSpecFiles(folder), config_dir=".cfg")
    assembly = kit.make_assembly(tmp_path, spaces_module({"a": space}))
    with kit.client_for(assembly) as client:
        first, last = _edit(client, "pt", "?project=a")
        diff = _diff(client, f"{T}/pt/versions/{first}/diff/{last}?project=a")
        assert diff.to_hash == last
        assert [c.path for c in diff.content_changes] == ["req.md"]
        assert _diff(client, f"{T}/pt/versions/{first}/diff?project=a") == diff
        assert client.get(f"{T}/pt/versions/{first}/diff").status_code == 404
        assert client.get(f"{T}/pt/versions/{first}/diff?project=zz").status_code == 404


def test_secret_locations_are_masked(tmp_path: Path, kit: Any) -> None:
    """비밀로 보이는 값(되돌리기 검사와 같은 규칙)은 응답에 나오지 않고 ``***``로 바뀐다."""
    kinds = [c.kind for c in kit.make_assembly(tmp_path / "k").ports(DEFINITION_KIND_CONTRIBUTIONS)]
    library = InMemoryDefinitionStore([k for k in kinds if k.library])
    base = {"kind": "spec-template", "id": "s", "name": "틀", "documents": []}
    first = library.create("spec-template", {**base, "description": f"key {SECRET}"}).version_hash
    last = library.save(
        "spec-template",
        {**base, "name": "새 이름", "description": f"key {SECRET[:-1]}b"},
        expected_version=first,
    ).version_hash
    with kit.client_for(kit.make_assembly(tmp_path / "lib", library_module(library))) as client:
        res = client.get(f"{T}/s/versions/{first}/diff/{last}")
        assert res.status_code == 200, res.text
        assert "sk-ant" not in res.text
        diff = DefinitionDiff.model_validate(res.json())
        by_path = {c.path: c for c in diff.changes}
        assert by_path["/description"].secret is True
        assert (by_path["/description"].before, by_path["/description"].after) == ("***", "***")
        assert by_path["/name"].secret is False
        assert by_path["/name"].after == "새 이름"


def test_openapi_lists_both_diff_paths(standalone: tuple[TestClient, Path]) -> None:
    client, _root = standalone
    paths = client.get(f"{API}/openapi.json").json()["paths"]
    for path in (
        "/api/v1/sdd/templates/{template_id}/versions/{version_hash}/diff",
        "/api/v1/sdd/templates/{template_id}/versions/{version_hash}/diff/{to_hash}",
    ):
        schema = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/DefinitionDiff")
