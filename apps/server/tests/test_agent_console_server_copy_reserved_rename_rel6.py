"""REL.6(통합 서버): 공용 문서 틀을 프로젝트로 복사할 때 대상에 쓸 id(rename 새 id, copy 원본
id)가 그 종류의 경로 예약어(mod-sdd가 종류 데이터 ``reserved_ids``로 준 말)면 422로 거절하고
아무것도 쓰지 않는다.
서버·이 테스트는 틀 종류 이름·예약어 목록을 모른다(복사 종류 목록과 오류 상세에서 읽는다)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server


def _template_kind(client: Any, item_id: str) -> str:
    kinds = client.get(f"{API}/projects/copy/kinds").json()
    return str(
        next(
            k["kind"]
            for k in kinds
            if k["library"]
            and k["portable"]
            and any(
                i["id"] == item_id
                for i in client.get(f"{API}/projects/copy/items", params={"kind": k["kind"]}).json()
            )
        )
    )


def _apply(client: Any, project: str, plan: dict[str, Any], new_id: str | None) -> Any:
    items = [
        {
            "kind": i["kind"],
            "id": i["id"],
            "action": "rename" if new_id is not None else "copy",
            **({"new_id": new_id} if new_id is not None else {}),
            "source_version": i["source_version"],
            "target_version": i["target_version"],
        }
        for i in plan["items"]
    ]
    return client.post(
        f"{API}/projects/copy/apply",
        json={"source": {"project_id": None}, "target": {"project_id": project}, "items": items},
    )


def test_rename_to_reserved_template_id_is_rejected(tmp_path: Path) -> None:
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path)) as client:
        made = client.post(f"{API}/sdd/templates", json={"name": "공용 틀", "id": "shared"})
        assert made.status_code == 201, made.text
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        assert registered.status_code == 201, registered.text
        project = registered.json()["project"]["id"]
        kind = _template_kind(client, "shared")
        plan = client.post(
            f"{API}/projects/copy/plan",
            json={
                "source": {"project_id": None},
                "target": {"project_id": project},
                "items": [{"kind": kind, "id": "shared"}],
            },
        ).json()

        # 만들기가 거절하는 예약어를 종류 데이터에서 얻는다(만들기 422 상세의 reserved).
        refused = client.post(f"{API}/sdd/templates", json={"name": "x", "id": "variables"})
        assert refused.status_code == 422, refused.text
        words = refused.json()["error"]["details"]["reserved"]
        assert words

        for word in words:
            response = _apply(client, project, plan, word.upper())
            assert response.status_code == 422, response.text
            error = response.json()["error"]
            assert error["code"] == "validation_failed"
            [issue] = error["details"]["issues"]
            assert issue["code"] == "project.copy_reserved_id"
            assert issue["details"]["new_id"] == word.upper()
            assert issue["details"]["suggested_id"].casefold() not in words
            assert error["message"] == issue["message"]
        listed = client.get(f"{API}/sdd/templates?project={project}").json()
        assert listed == []  # 아무것도 쓰지 않았다

        # 예약어가 아니면 그대로 이름을 바꿔 복사한다.
        response = _apply(client, project, plan, "shared-copy")
        assert response.status_code == 200, response.text
        assert [i["status"] for i in response.json()["items"]] == ["renamed"]
        listed = client.get(f"{API}/sdd/templates?project={project}").json()
        assert [t["id"] for t in listed] == ["shared-copy"]


def test_copy_of_reserved_template_id_is_rejected(tmp_path: Path) -> None:
    """예약어 id로 이미 있는 공용 틀(예: 직접 파일로 둔 것)을 copy로 그대로 쓰면 422."""
    folder = tmp_path / "work" / "app"
    folder.mkdir(parents=True)
    with server(make_settings(tmp_path)) as client:
        made = client.post(f"{API}/sdd/templates", json={"name": "공용 틀", "id": "shared"})
        assert made.status_code == 201, made.text
        kind = _template_kind(client, "shared")
        refused = client.post(f"{API}/sdd/templates", json={"name": "x", "id": "variables"})
        word = refused.json()["error"]["details"]["reserved"][0]
        registered = client.post(f"{API}/projects", json={"folder": str(folder)})
        project = registered.json()["project"]["id"]
        # 계획 항목을 예약어 id로 바꿔 copy로 보낸다(원본에 그 id가 있는지는 판정 전에 거절된다).
        plan = client.post(
            f"{API}/projects/copy/plan",
            json={
                "source": {"project_id": None},
                "target": {"project_id": project},
                "items": [{"kind": kind, "id": "shared"}],
            },
        ).json()
        plan["items"][0]["id"] = word
        response = _apply(client, project, plan, None)
        assert response.status_code == 422, response.text
        [issue] = response.json()["error"]["details"]["issues"]
        assert issue["code"] == "project.copy_reserved_id"
        assert issue["details"]["action"] == "copy"
        assert issue["details"]["target_id"] == word
        assert client.get(f"{API}/sdd/templates?project={project}").json() == []


def test_copy_kinds_and_sdd_info_expose_same_reserved_words_p1_5(tmp_path: Path) -> None:
    """P1.5: 화면이 적용 전에 아는 예약어 — 복사 종류 목록(`CopyKindInfo.reserved_ids`)과 SDD 화면
    정보(`SddInfo.reserved_template_ids`)가 같은 말을 주고, 그 말은 만들기가 거절하는 말이다."""
    with server(make_settings(tmp_path)) as client:
        made = client.post(f"{API}/sdd/templates", json={"name": "공용 틀", "id": "shared"})
        assert made.status_code == 201, made.text
        kind = _template_kind(client, "shared")
        kinds = {k["kind"]: k for k in client.get(f"{API}/projects/copy/kinds").json()}
        words = kinds[kind]["reserved_ids"]
        assert words
        assert client.get(f"{API}/sdd/info").json()["reserved_template_ids"] == words
        refused = client.post(f"{API}/sdd/templates", json={"name": "x", "id": words[-1]})
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["details"]["reserved"] == words
        others = [k for name, k in kinds.items() if name != kind]
        assert others
        assert all(isinstance(k["reserved_ids"], list) for k in others)
