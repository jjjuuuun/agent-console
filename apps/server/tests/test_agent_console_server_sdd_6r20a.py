"""6R.20a(통합 서버): 공용(라이브러리) 문서 틀 만들기 → 뼈대 파일 → 복사 종류 메타데이터에
틀 종류가 보임 → 프로젝트로 복사 → 그 프로젝트 공간의 틀 목록·뼈대 파일, 6R.20d 하위 폴더.
서버·웹은 틀 종류 이름을 모른다(종류 이름은 mod-sdd 설치자 데이터)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

T = f"{API}/sdd/templates"


def _copy(client: Any, kind: str, item: str, project: str) -> list[str]:
    plan = client.post(
        f"{API}/projects/copy/plan",
        json={
            "source": {"project_id": None},
            "target": {"project_id": project},
            "items": [{"kind": kind, "id": item}],
        },
    )
    assert plan.status_code == 200, plan.text
    items = [
        {
            "kind": i["kind"],
            "id": i["id"],
            "action": i["default_action"] or "overwrite",
            "source_version": i["source_version"],
            "target_version": i["target_version"],
        }
        for i in plan.json()["items"]
    ]
    applied = client.post(
        f"{API}/projects/copy/apply",
        json={"source": {"project_id": None}, "target": {"project_id": project}, "items": items},
    )
    assert applied.status_code == 200, applied.text
    return [i["status"] for i in applied.json()["items"]]


def test_library_template_copies_to_project(tmp_path: Path) -> None:
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path)) as client:
        made = client.post(T, json={"name": "공용 틀", "id": "shared"})
        assert made.status_code == 201, made.text
        tag = made.headers["etag"]
        wrote = client.put(
            f"{T}/shared/files/req.md", content=b"# req\n", headers={"If-Match": tag}
        )
        assert wrote.status_code == 200, wrote.text
        doc = {**wrote.json(), "documents": [{"id": "req", "title": "요구", "file": "req.md"}]}
        saved = client.put(f"{T}/shared", json=doc, headers={"If-Match": wrote.headers["etag"]})
        assert saved.status_code == 200, saved.text
        assert len(client.get(f"{T}/shared/versions").json()) >= 3

        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]

        # 복사 종류 메타데이터: 틀 종류가 기여 메타데이터(library·portable)로 들어온다.
        kinds = {k["kind"]: k for k in client.get(f"{API}/projects/copy/kinds").json()}
        template_kind = next(
            k
            for k, v in kinds.items()
            if v["library"]
            and v["portable"]
            and any(
                i["id"] == "shared"
                for i in client.get(f"{API}/projects/copy/items", params={"kind": k}).json()
            )
        )
        spec_kinds = {
            k["kind"]: k for k in client.get(f"{API}/projects/copy/kinds?project={project}").json()
        }
        assert template_kind in spec_kinds
        assert any(not v["library"] for v in spec_kinds.values())  # 스펙 종류(library=False)

        assert _copy(client, template_kind, "shared", project) == ["copied"]
        listed = client.get(f"{T}?project={project}").json()
        assert [t["id"] for t in listed] == ["shared"]
        files = client.get(f"{T}/shared/files?project={project}").json()
        assert [f["path"] for f in files] == ["req.md"]
        assert client.get(f"{T}/shared/files/req.md?project={project}").content == b"# req\n"
        spec = client.post(
            f"{API}/sdd/specs?project={project}", json={"name": "S", "template": "shared"}
        )
        assert spec.status_code == 201, spec.text

        # 6R.20d: 프로젝트 폴더 하위 폴더 — 구성 폴더(.agent-console)는 보이지 않는다
        (folder / "docs" / "sub").mkdir(parents=True)
        listing = client.get(f"{API}/sdd/import/files?project={project}").json()
        assert [d["name"] for d in listing["dirs"]] == ["docs"]
        sub = client.get(f"{API}/sdd/import/files?project={project}&path=docs").json()
        assert [d["name"] for d in sub["dirs"]] == ["sub"]


def test_templates_work_without_definitions_module(tmp_path: Path) -> None:
    """정의 모듈을 끄면 단독 루트 틀로 동작한다(공용 복사 메타데이터는 409)."""
    settings = make_settings(tmp_path, modules={"disabled": ["mod-definitions"]})
    with server(settings) as client:
        info = client.get(f"{API}/sdd/info").json()
        assert info["capabilities"]["templates"] is False
        made = client.post(T, json={"name": "단독 틀", "id": "solo"})
        assert made.status_code == 201, made.text
        assert [t["id"] for t in client.get(T).json()] == ["solo"]
        assert client.delete(f"{T}/solo").status_code == 204
        kinds = client.get(f"{API}/projects/copy/kinds")
        assert kinds.status_code in (404, 409)
