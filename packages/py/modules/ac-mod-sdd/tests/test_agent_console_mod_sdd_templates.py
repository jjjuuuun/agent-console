"""6R.20a 문서 틀 단건 REST(screen-sdd §11.1)와 6R.20d 가져오기 하위 폴더.

만들기 → 저장 충돌 412·428 → 뼈대 파일 쓰기·읽기·지우기 → 버전·되돌리기 → 삭제, 경로 공격 거부,
정의 모듈 없음(단독 루트) / 라이브러리 / 프로젝트 공간, 경로 예약어, 비밀 검사.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_mod_sdd.testing import SimpleSpace, library_module, spaces_module
from agent_console_modkit import DEFINITION_KIND_CONTRIBUTIONS
from agent_console_sdd import LocalSpecFiles
from agent_console_store import InMemoryDefinitionStore

API = "/api/v1"
T = f"{API}/sdd/templates"


def _create(client: TestClient, query: str = "", **body: Any) -> Any:
    res = client.post(f"{T}{query}", json={"name": "새 틀", **body})
    assert res.status_code == 201, res.text
    return res


def test_template_lifecycle_on_standalone_root(standalone: tuple[TestClient, Path]) -> None:
    """정의 모듈이 없는 조립: 단독 루트에 만들고 고친다(목록과 같은 저장소)."""
    client, root = standalone
    made = _create(client, id="plan", description="설명")
    body = made.json()
    assert body["documents"] == []
    assert body["description"] == "설명"
    tag = made.headers["etag"]
    assert [t["id"] for t in client.get(T).json()] == ["plan"]
    assert (root / "spec-templates" / "plan.yaml").is_file()
    assert client.post(T, json={"name": "x", "id": "plan"}).status_code == 409

    got = client.get(f"{T}/plan")
    assert got.status_code == 200
    assert got.headers["etag"] == tag

    # 규칙·문서 목록 저장: If-Match 없음 428, 낡음 412, 맞으면 새 ETag
    doc = {**body, "documents": [{"id": "req", "title": "요구", "file": "req.md"}]}
    assert client.put(f"{T}/plan", json=doc).status_code == 428
    stale = client.put(f"{T}/plan", json=doc, headers={"If-Match": '"nope"'})
    assert stale.status_code == 412
    mismatch = client.put(f"{T}/other", json=doc, headers={"If-Match": tag})
    assert mismatch.status_code == 400
    saved = client.put(f"{T}/plan", json=doc, headers={"If-Match": tag})
    assert saved.status_code == 200, saved.text
    tag = saved.headers["etag"]
    assert tag != got.headers["etag"]

    # 뼈대 파일: 쓰기(If-Match = 정의 버전) → 목록·읽기 → 지우기
    assert client.put(f"{T}/plan/files/req.md", content=b"# req\n").status_code == 428
    wrote = client.put(f"{T}/plan/files/req.md", content=b"# req\n", headers={"If-Match": tag})
    assert wrote.status_code == 200, wrote.text
    tag = wrote.headers["etag"]
    wrote2 = client.put(f"{T}/plan/files/sub/extra.md", content=b"x", headers={"If-Match": tag})
    tag = wrote2.headers["etag"]
    files = client.get(f"{T}/plan/files").json()
    assert [f["path"] for f in files] == ["req.md", "sub/extra.md"]
    read = client.get(f"{T}/plan/files/req.md")
    assert read.content == b"# req\n"
    assert read.headers["etag"] == tag
    assert client.get(f"{T}/plan/files/none.md").status_code == 404
    gone = client.delete(f"{T}/plan/files/sub/extra.md", headers={"If-Match": tag})
    assert gone.status_code == 200, gone.text
    tag = gone.headers["etag"]
    assert [f["path"] for f in client.get(f"{T}/plan/files").json()] == ["req.md"]
    names = [v["name"] for v in client.get(f"{T}/plan/variables").json()]
    assert "doc_req_file" in names

    # 버전: 목록 → 첫 버전으로 되돌리기(새 버전, 파일도 그 버전대로)
    versions = client.get(f"{T}/plan/versions").json()
    assert len(versions) >= 4
    first = versions[-1]["version_hash"]
    one = client.get(f"{T}/plan/versions/{first}").json()
    assert one["content"]["documents"] == []
    assert client.post(f"{T}/plan/versions/{first}/restore").status_code == 428
    restored = client.post(
        f"{T}/plan/versions/{first}/restore", headers={"If-Match": tag}, json={"message": "처음"}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["message"] == "처음"
    tag = restored.headers["etag"]
    assert client.get(f"{T}/plan").json()["documents"] == []
    assert client.get(f"{T}/plan/files").json() == []

    # 삭제(If-Match 선택), 없으면 404
    assert client.delete(f"{T}/plan", headers={"If-Match": '"nope"'}).status_code == 412
    assert client.delete(f"{T}/plan", headers={"If-Match": tag}).status_code == 204
    assert client.get(f"{T}/plan").status_code == 404
    assert client.delete(f"{T}/plan").status_code == 404
    assert client.get(T).json() == []


def test_file_path_attacks_are_refused(standalone: tuple[TestClient, Path]) -> None:
    client, root = standalone
    tag = _create(client, id="p").headers["etag"]
    for bad in ("..%2Fx.md", "a/..%2F..%2Fx.md", "%2Fetc%2Fpasswd", "a%5Cb.md", "a//b.md"):
        res = client.put(f"{T}/p/files/{bad}", content=b"x", headers={"If-Match": tag})
        assert res.status_code in (400, 404, 422), (bad, res.status_code)
        assert client.get(f"{T}/p/files/{bad}").status_code in (400, 404, 422), bad
    assert not (root / "x.md").exists()
    assert not (root / "spec-templates" / "x.md").exists()
    assert client.get(f"{T}/p/files").json() == []


def test_route_words_are_not_template_ids(standalone: tuple[TestClient, Path]) -> None:
    client, _root = standalone
    refused = client.post(T, json={"name": "x", "id": "variables"})
    assert refused.status_code == 422
    assert refused.json()["error"]["details"]["reserved"] == ["variables", "check"]
    auto = _create(client, name="variables").json()
    assert auto["id"] == "variables-2"
    assert isinstance(client.get(f"{T}/variables").json(), list)  # 고정 경로 그대로


def test_secret_scan_reject_blocks_file_and_warn_reports(tmp_path: Path, kit: Any) -> None:
    secret = b"token sk-ant-api03-" + b"a" * 40 + b"\n"
    reject = kit.make_assembly(tmp_path / "r", settings={"sdd": {"secret_scan": "reject"}})
    with kit.client_for(reject) as client:
        tag = _create(client, id="s").headers["etag"]
        res = client.put(f"{T}/s/files/a.md", content=secret, headers={"If-Match": tag})
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "sdd.secret_rejected"
        assert "sk-ant" not in res.text
        assert client.get(f"{T}/s/files").json() == []
    with kit.client_for(kit.make_assembly(tmp_path / "w")) as client:
        tag = _create(client, id="s").headers["etag"]
        res = client.put(f"{T}/s/files/a.md", content=secret, headers={"If-Match": tag})
        assert res.status_code == 200
        assert "sdd.secret_suspect" in res.headers["x-console-issues"]
        assert "sk-ant" not in res.headers["x-console-issues"]


def test_library_store_is_used_when_present(tmp_path: Path, kit: Any) -> None:
    kinds = [c.kind for c in kit.make_assembly(tmp_path / "k").ports(DEFINITION_KIND_CONTRIBUTIONS)]
    library = InMemoryDefinitionStore([k for k in kinds if k.library])
    with kit.client_for(kit.make_assembly(tmp_path / "lib", library_module(library))) as client:
        tag = _create(client, id="lib").headers["etag"]
        assert library.list_ids("spec-template") == ["lib"]
        res = client.put(f"{T}/lib/files/a.md", content=b"# a", headers={"If-Match": tag})
        assert res.status_code == 200
        assert library.read_file("spec-template", "lib", "a.md") == b"# a"
        # 라이브러리 틀로 스펙을 만들 수 있다(단독 루트 스펙)
        doc = {**client.get(f"{T}/lib").json()}
        doc["documents"] = [{"id": "a", "title": "A", "file": "a.md"}]
        put = client.put(f"{T}/lib", json=doc, headers={"If-Match": res.headers["etag"]})
        assert put.status_code == 200, put.text
        spec = client.post(f"{API}/sdd/specs", json={"name": "S", "template": "lib"})
        assert spec.status_code == 201, spec.text
    assert not (tmp_path / "lib" / "ws" / "sdd" / "spec-templates").exists()


def test_project_space_templates(tmp_path: Path, kit: Any) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    store = kit.spec_store(folder / ".cfg")
    space = SimpleSpace(store=store, files=LocalSpecFiles(folder), config_dir=".cfg")
    assembly = kit.make_assembly(tmp_path, spaces_module({"a": space}))
    with kit.client_for(assembly) as client:
        tag = _create(client, "?project=a", id="pt").headers["etag"]
        assert store.list_ids("spec-template") == ["pt"]
        assert client.get(f"{T}/pt").status_code == 404  # 단독 루트와 섞이지 않는다
        res = client.put(f"{T}/pt/files/r.md?project=a", content=b"# r", headers={"If-Match": tag})
        assert res.status_code == 200, res.text
        assert (folder / ".cfg" / "spec-templates" / "pt" / "r.md").read_bytes() == b"# r"
        assert [t["id"] for t in client.get(f"{T}?project=a").json()] == ["pt"]
        assert client.get(f"{T}/pt/versions?project=a").status_code == 200
        assert client.get(f"{T}/pt?project=zz").status_code == 404
        assert client.delete(f"{T}/pt?project=a").status_code == 204
    no_spaces = kit.make_assembly(tmp_path / "n")
    with kit.client_for(no_spaces) as client:
        res = client.post(f"{T}?project=a", json={"name": "x"})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "sdd.spaces_unavailable"


def test_import_files_lists_subfolders(standalone: tuple[TestClient, Path]) -> None:
    """6R.20d: 단독 루트 — 스펙·틀 폴더(예약)·숨김은 하위 폴더 목록에 없다, 폴더 밖은 거부."""
    client, root = standalone
    (root / "docs" / "nested").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("# a", encoding="utf-8")
    (root / ".hidden").mkdir()
    (root / "specs").mkdir()
    (root / "spec-templates").mkdir()
    listing = client.get(f"{API}/sdd/import/files").json()
    assert [d["name"] for d in listing["dirs"]] == ["docs"]
    docs = client.get(f"{API}/sdd/import/files?path=docs").json()
    assert [d["name"] for d in docs["dirs"]] == ["nested"]
    assert [f["name"] for f in docs["files"]] == ["a.md"]
    assert client.get(f"{API}/sdd/import/files?path=../x").status_code == 422
    assert client.get(f"{API}/sdd/import/files?path=specs").status_code == 422
