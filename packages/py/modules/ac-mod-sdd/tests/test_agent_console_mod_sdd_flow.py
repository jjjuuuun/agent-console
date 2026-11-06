"""모듈 혼자 켠 서버(단독 루트)에서 틀 → 스펙 → 문서 편집 → 상태 전환 → 작업 고치기 → 계획·추적
(6R.13 완료 기준, design §6R.0·§6R.7, §6R.18 Q2·Q4·Q9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

API = "/api/v1"


def test_empty_workspace_has_no_templates_or_specs(standalone: tuple[TestClient, Path]) -> None:
    client, root = standalone
    assert client.get(f"{API}/sdd/templates").json() == []
    assert client.get(f"{API}/sdd/specs").json() == []
    info = client.get(f"{API}/sdd/info").json()
    assert info["spec_root"] == "specs"
    assert info["writable"] is True
    assert info["capabilities"] == {
        "runs": False,
        "templates": False,
        "verification": False,
        "automation": False,
        "import_export": True,
    }
    assert info["limits"]["max_bulk_start"] == 10
    assert [d["key"] for d in info["label_display"]] == [
        "sdd.spec",
        "sdd.task",
        "sdd.profile",
        "sdd.purpose",
    ]
    assert not root.exists()  # 읽기만으로 폴더를 만들지 않는다


def test_template_to_spec_to_trace(standalone: tuple[TestClient, Path], kit: Any) -> None:
    client, root = standalone
    kit.write_template(kit.spec_store(root))
    templates = client.get(f"{API}/sdd/templates").json()
    assert [t["id"] for t in templates] == ["flow"]
    assert templates[0]["run_profiles"][0]["graph"] == "team-x"
    names = [v["name"] for v in client.get(f"{API}/sdd/templates/variables?template=flow").json()]
    assert "doc_tasks_file" in names
    assert "task_field_owner" in names
    fresh = [v["name"] for v in client.get(f"{API}/sdd/templates/variables").json()]
    assert "task_id" in fresh
    assert not any(n.startswith("doc_") for n in fresh)

    created = client.post(f"{API}/sdd/specs", json={"name": "Payments v2", "template": "flow"})
    assert created.status_code == 201, created.text
    view = created.json()
    assert view["spec"]["id"] == "payments-v2"
    assert view["directory"] == "specs/payments-v2"
    assert created.headers["etag"] == f'"{view["version_hash"]}"'
    assert [t["key"] for t in view["index"]["tasks"]] == ["1.1", "1.2", "2.1"]
    assert {s["id"]: s["label"] for s in view["document_states"]} == {
        "draft": "draft",
        "approved": "승인",
    }
    assert (root / "specs" / "payments-v2" / "tasks.md").read_text(encoding="utf-8") == kit.TASKS

    listed = client.get(f"{API}/sdd/specs").json()
    assert [(s["id"], s["tasks_total"], s["ready"]) for s in listed] == [("payments-v2", 3, 1)]
    assert listed[0]["current_stage"]["id"] == "1단계"

    # 문서 편집(If-Match = 본문 해시)
    doc = client.get(f"{API}/sdd/specs/payments-v2/documents/design")
    assert doc.status_code == 200
    stale = client.put(
        f"{API}/sdd/specs/payments-v2/documents/design",
        json={"content": "# 설계\n새 내용\n"},
        headers={"If-Match": '"nope"'},
    )
    assert stale.status_code == 412
    saved = client.put(
        f"{API}/sdd/specs/payments-v2/documents/design",
        json={"content": "# 설계\n새 내용\n"},
        headers={"If-Match": doc.headers["etag"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["content"] == "# 설계\n새 내용\n"

    # 관문: 설계 승인 전에는 작업 상태를 바꾸지 못한다
    task = client.get(f"{API}/sdd/specs/payments-v2/tasks?ready=true").json()
    assert [t["key"] for t in task] == ["1.1"]
    patch = {"status": "done", "expected_line_hash": task[0]["line_hash"]}
    blocked = client.patch(f"{API}/sdd/specs/payments-v2/tasks/1.1", json=patch)
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "sdd.gate_blocked"
    assert blocked.json()["error"]["details"]["document_ids"] == ["design"]

    # 상태 전환(규칙에 없는 전환은 403)
    denied = client.post(
        f"{API}/sdd/specs/payments-v2/documents/design/state", json={"to": "review"}
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "sdd.transition_denied"
    approved = client.post(
        f"{API}/sdd/specs/payments-v2/documents/design/state", json={"to": "approved"}
    )
    assert approved.status_code == 200, approved.text
    states = {d["id"]: d.get("state") for d in approved.json()["spec"]["documents"]}
    assert states["design"] == "approved"

    # 작업 고치기 = 줄 하나
    before = (root / "specs/payments-v2/tasks.md").read_text(encoding="utf-8")
    done = client.patch(f"{API}/sdd/specs/payments-v2/tasks/1.1", json=patch)
    assert done.status_code == 200, done.text
    assert done.json()["task"]["status"] == "done"
    after = (root / "specs/payments-v2/tasks.md").read_text(encoding="utf-8")
    changed = [
        (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b
    ]
    assert changed == [
        ("- [ ] 1.1 뼈대 [req: R1] [owner: be]", "- [x] 1.1 뼈대 [req: R1] [owner: be]")
    ]
    again = client.patch(f"{API}/sdd/specs/payments-v2/tasks/1.1", json=patch)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "sdd.task_changed"

    # 거르기
    filtered = client.get(
        f"{API}/sdd/specs/payments-v2/tasks", params={"status": "todo", "field": "req=R1"}
    ).json()
    assert [t["key"] for t in filtered] == ["1.2"]
    assert client.get(f"{API}/sdd/specs/payments-v2/tasks?q=검증").json()[0]["key"] == "2.1"
    assert client.get(f"{API}/sdd/specs/payments-v2/tasks?field=bad").status_code == 400

    # 계획·추적·변수·문법
    plan = client.get(f"{API}/sdd/specs/payments-v2/plan").json()
    assert plan["layers"] == [["1.2"], ["2.1"]]
    assert plan["critical_path"] == ["1.2", "2.1"]
    trace = client.get(f"{API}/sdd/specs/payments-v2/trace").json()
    rows = {r["id"]: r for r in trace["rows"]}
    assert rows["R1"]["tasks"] == ["1.1", "1.2"]
    assert "no_task" in rows["R2"]["gaps"]
    variables = client.get(f"{API}/sdd/specs/payments-v2/variables").json()
    assert "doc_design_file" in [v["name"] for v in variables]
    syntax = client.get(f"{API}/sdd/specs/payments-v2/syntax").json()
    assert syntax["empty"] is False

    # 규칙 저장(If-Match 필수)
    spec = approved.json()["spec"]
    spec["rules"]["gates"] = []
    assert client.put(f"{API}/sdd/specs/payments-v2", json=spec).status_code == 428
    current = client.get(f"{API}/sdd/specs/payments-v2")
    put = client.put(
        f"{API}/sdd/specs/payments-v2", json=spec, headers={"If-Match": current.headers["etag"]}
    )
    assert put.status_code == 200, put.text
    assert put.json()["spec"]["rules"]["gates"] == []

    # 삭제: 파일만, 404 뒤
    assert client.delete(f"{API}/sdd/specs/payments-v2").status_code == 204
    assert client.get(f"{API}/sdd/specs/payments-v2").status_code == 404
    assert client.get(f"{API}/sdd/specs").json() == []


def test_document_missing_is_not_created_by_read(standalone: tuple[TestClient, Path]) -> None:
    client, root = standalone
    made = client.post(f"{API}/sdd/specs", json={"name": "Blank"})
    assert made.status_code == 201, made.text
    view = made.json()
    doc = view["spec"]["documents"][0]
    path = root / "specs" / "blank" / doc["file"]
    path.unlink()
    missing = client.get(f"{API}/sdd/specs/blank/documents/{doc['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "sdd.document_missing"
    assert missing.json()["error"]["details"] == {"document_id": doc["id"], "file": doc["file"]}
    assert not path.exists()
    created = client.put(
        f"{API}/sdd/specs/blank/documents/{doc['id']}",
        json={"content": ""},
        headers={"If-None-Match": "*"},
    )
    assert created.status_code == 200, created.text
    assert path.exists()
    exists = client.put(
        f"{API}/sdd/specs/blank/documents/{doc['id']}",
        json={"content": "x"},
        headers={"If-None-Match": "*"},
    )
    assert exists.status_code == 409


def test_template_check_reports_broken_rules(standalone: tuple[TestClient, Path]) -> None:
    client, _root = standalone
    body = {
        "rules": {"task_statuses": [{"id": "a", "marker": "x"}, {"id": "b", "marker": "x"}]},
        "documents": [],
    }
    result = client.post(f"{API}/sdd/templates/check", json=body)
    assert result.status_code == 200, result.text
    codes = {i["code"] for i in result.json()["issues"]}
    assert "sdd.duplicate_status_marker" in codes
    broken = client.post(f"{API}/sdd/templates/check", json={"rules": {"gates": "nope"}})
    assert broken.status_code == 200
    assert broken.json()["issues"]
