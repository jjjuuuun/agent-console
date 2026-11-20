"""6R.24 R0 통합: 이름을 모두 바꾼 틀·아무 규칙도 없는 틀로 스펙 작업 실행까지 한 바퀴(fake 백엔드).

- C-1: 문서 id·파일·필드 이름·상태 id·표시 문자·단계 제목 수준·프로필 id·목적·구분자를 전부
  기본과 다르게 준 규칙으로 작업 실행 → 라벨·`status_on`·추적 검증이 같은 모양으로 동작.
- C-2: 관문·전환·문서 상태·`status_on`·검증 설정이 모두 빈 규칙에서도 실행이 막히지 않고
  작업 줄이 그대로이며, 문서 상태 전환 요청은 거부된다(A-7 "목록 없는 스펙에서 전환 거부").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    make_settings,
    seed,
    server,
    wait_for,
    wait_run,
)

NO_PROJECT_GATE: dict[str, dict[str, Any]] = {"link-projects-runs": {"require_project": False}}

DOCS = [
    {"id": "rfc", "title": "제안서", "file": "rfc.txt.md", "roles": ["requirements"]},
    {"id": "plan", "title": "계획", "file": "plan.md", "roles": ["tasks"]},
]
FILES = {
    "rfc": "**Q1** 첫째\n\n**Q2** 둘째\n",
    "plan": (
        "#### 라운드 A\n\n- [.] t-1 뼈대 [needs: Q1]\n- [.] t-2 화면 [needs: Q2; Q1] [after: t-1]\n"
    ),
}
RENAMED_SYNTAX: dict[str, Any] = {
    "task": {
        "list_item": "checkbox",
        "statuses": [
            {"id": "open", "marker": "."},
            {"id": "wip", "marker": "~"},
            {"id": "closed", "marker": ["v", "V"], "done": True},
        ],
        "list_separator": ";",
        "range_separator": "..",
        "none_values": ["nothing", ""],
        "roles": {"after": "dependencies", "needs": "requirements", "who": "assignee"},
        "body": "nested",
    },
    "requirement": {"patterns": [r"^\*\*(?P<id>Q\d[\w.]*)\*\*"]},
    "stage": {"heading_levels": [4], "pattern": r"^(?P<id>.+)$"},
}
RENAMED_RULES: dict[str, Any] = {
    "syntax": RENAMED_SYNTAX,
    "run_profiles": [
        {
            "id": "build-it",
            "title": "만들기",
            "graph": "flow",
            "purpose": "ship",
            "input": {"request": "{task_id}: {task_title}"},
            "status_on": {"started": "wip", "succeeded": "closed"},
        },
        {"id": "audit-it", "title": "점검", "graph": "flow", "purpose": "audit"},
    ],
    "verification": {"purposes": ["audit"], "result_map": {"succeeded": "pass"}},
}
# 관문·전환·문서 상태·status_on·검증이 전부 없는 규칙(문법은 기본 문법 그대로)
EMPTY_RULES: dict[str, Any] = {
    "run_profiles": [{"id": "go", "title": "실행", "graph": "flow", "purpose": "any"}],
}
BASIC_FILES = {
    "rfc": "**Q1** 첫째\n\n**Q2** 둘째\n",
    "plan": "# 작업\n\n## 1\n\n- [ ] 1.1 뼈대 [req: Q1]\n- [ ] 1.2 화면 [req: Q2]\n",
}


def _make(client: TestClient, rules: dict[str, Any], files: dict[str, str]) -> None:
    made = client.post(f"{API}/sdd/specs", json={"name": "R"})
    assert made.status_code == 201, made.text
    body = {"kind": "spec", "id": "r", "name": "R", "documents": DOCS, "rules": rules}
    saved = client.put(f"{API}/sdd/specs/r", json=body, headers={"If-Match": made.headers["etag"]})
    assert saved.status_code == 200, saved.text
    for doc, text in files.items():
        put = client.put(
            f"{API}/sdd/specs/r/documents/{doc}",
            json={"content": text},
            headers={"If-None-Match": "*"},
        )
        assert put.status_code == 200, put.text


def _task(client: TestClient, key: str) -> dict[str, Any]:
    tasks = client.get(f"{API}/sdd/specs/r/tasks").json()
    found: dict[str, Any] = next(t for t in tasks if t["key"] == key)
    return found


def _run(client: TestClient, key: str, profile: str) -> str:
    started = client.post(f"{API}/sdd/specs/r/tasks/{key}/actions/runs/{profile}")
    assert started.status_code == 200, started.text
    run_id: str = started.json()["run_id"]
    snap = wait_run(client, run_id, timeout=30)
    assert snap["run"]["status"] == "completed", snap["run"]
    return run_id


def test_everything_renamed_spec_runs_a_full_round(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=NO_PROJECT_GATE)) as client:
        seed(client)
        _make(client, RENAMED_RULES, FILES)
        view = client.get(f"{API}/sdd/specs/r").json()
        assert [i for i in view["issues"] if i["severity"] != "info"] == [], view["issues"]
        tasks = client.get(f"{API}/sdd/specs/r/tasks").json()
        assert [(t["key"], t["status"]) for t in tasks] == [("t-1", "open"), ("t-2", "open")]
        assert tasks[1]["dependencies"] == ["t-1"]
        assert tasks[1]["requirements"] == ["Q2", "Q1"]
        assert tasks[0]["stage"]["title"] == "라운드 A"

        run_id = _run(client, "t-1", "build-it")
        wait_for(lambda: _task(client, "t-1")["status"] == "closed", timeout=10)
        text = client.get(f"{API}/sdd/specs/r/documents/plan").json()["content"]
        assert "- [v] t-1 뼈대 [needs: Q1]" in text
        assert "- [.] t-2 화면" in text  # 다른 줄은 그대로
        page = client.get(f"{API}/runs/page?label=sdd.task=t-1&label=sdd.spec=r").json()
        [run] = page["items"]
        assert run["id"] == run_id
        assert run["labels"]["sdd.profile"] == "build-it"
        assert run["labels"]["sdd.purpose"] == "ship"
        assert run["input"] == {"request": "t-1: 뼈대"}

        audit = _run(client, "t-2", "audit-it")
        wait_for(lambda: client.get(f"{API}/sdd/specs/r/trace").json()["rows"][1]["verification"])
        rows = {r["id"]: r for r in client.get(f"{API}/sdd/specs/r/trace").json()["rows"]}
        assert rows["Q2"]["verification"]["status"] == "pass"
        assert rows["Q2"]["results"][0]["ref"]["run_id"] == audit
        assert _task(client, "t-2")["status"] == "open"  # status_on 없음


def test_empty_gates_transitions_and_status_on_still_run(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, options=NO_PROJECT_GATE)) as client:
        seed(client)
        _make(client, EMPTY_RULES, BASIC_FILES)
        view = client.get(f"{API}/sdd/specs/r").json()
        assert view["document_states"] == []
        assert all(d.get("state") is None for d in view["spec"]["documents"])
        before = client.get(f"{API}/sdd/specs/r/documents/plan").json()["content"]

        run_id = _run(client, "1.1", "go")  # 관문이 없으니 막히지 않는다
        page = client.get(f"{API}/runs/page?label=sdd.task=1.1").json()
        assert [r["id"] for r in page["items"]] == [run_id]
        # status_on이 비어 있으면 작업 줄·문서가 그대로
        assert client.get(f"{API}/sdd/specs/r/documents/plan").json()["content"] == before
        assert _task(client, "1.1")["status"] == "todo"
        # 전환이 없으니 어느 문서든 상태 전환은 거부(상태가 생기지 않음)
        for doc in ("rfc", "plan"):
            denied = client.post(
                f"{API}/sdd/specs/r/documents/{doc}/state", json={"to": "approved"}
            )
            assert denied.status_code == 403, denied.text
            assert denied.json()["error"]["code"] == "sdd.transition_denied"
        after = client.get(f"{API}/sdd/specs/r").json()
        assert all(d.get("state") is None for d in after["spec"]["documents"])
        assert after["version_hash"] == view["version_hash"]
