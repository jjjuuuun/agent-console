"""6R.15 통합: 설치된 모듈 전부 + fake 백엔드(SDK 호출 없음)에서 스펙 작업 실행.

- 단독 루트 스펙(공간 이름 없음): 작업 실행 → Run 라벨(``GET /runs/page?label=``) → 끝나면
  ``status_on``대로 작업 줄 하나만 바뀜 → 실행 칩·추적 검증 열.
- 프로젝트 공간 스펙(``link-projects-sdd``가 켜진 조립에서만): Run이 프로젝트 기록 DB에(``source``
  ``project``), 공용 구성에만 있는 팀 구성 → 422 ``project.not_imported``(``in_library``) + 프로필
  검사 ``sdd.profile_graph_missing``.
- ``mod-runs``를 끄면 연동이 꺼지고(``capabilities.runs=false``·동작 없음) 스펙 기능은 그대로.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    make_settings,
    register_project,
    seed,
    server,
    wait_for,
    wait_run,
)

RULES: dict[str, Any] = {
    "document_states": [{"id": "draft"}, {"id": "approved"}],
    "initial_document_state": "draft",
    "transitions": [{"from": "*", "to": "approved", "by": ["human"]}],
    "task_statuses": [
        {"id": "todo", "marker": " "},
        {"id": "doing", "marker": "~"},
        {"id": "done", "marker": ["x", "X"], "done": True},
    ],
    "gates": [
        {
            "id": "design-approved",
            "applies_to": ["run"],
            "message": "설계 승인 전",
            "require": {
                "all": [{"path": "/documents/design/state", "op": "eq", "value": "approved"}]
            },
        }
    ],
    "run_profiles": [
        {
            "id": "impl",
            "title": "구현",
            "graph": "flow",
            "purpose": "implement",
            "input": {"request": "작업 {task_id} {task_title}"},
            "status_on": {"started": "doing", "succeeded": "done"},
        },
        {"id": "verify", "title": "검증", "graph": "flow", "purpose": "verify"},
        {"id": "shared", "title": "공용 팀", "graph": "lib-only", "purpose": "implement"},
    ],
    "verification": {"purposes": ["verify"], "result_map": {"succeeded": "pass"}},
}
DOCUMENTS = [
    {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
    {"id": "design", "title": "설계", "file": "design.md"},
    {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
]
TASKS = "# 작업\n\n## 1\n\n- [ ] 1.1 뼈대 [req: R1]\n- [ ] 1.2 화면 [req: R2]\n"
FILES = {"req": "**R1** 하나\n\n**R2** 둘\n", "design": "# 설계\n", "tasks": TASKS}


def _q(space: str | None) -> str:
    return f"?project={space}" if space else ""


def _make_spec(client: TestClient, space: str | None) -> None:
    q = _q(space)
    made = client.post(f"{API}/sdd/specs{q}", json={"name": "S"})
    assert made.status_code == 201, made.text
    etag = made.headers["etag"]
    body = {"kind": "spec", "id": "s", "name": "S", "documents": DOCUMENTS, "rules": RULES}
    saved = client.put(f"{API}/sdd/specs/s{q}", json=body, headers={"If-Match": etag})
    assert saved.status_code == 200, saved.text
    for doc, text in FILES.items():
        put = client.put(
            f"{API}/sdd/specs/s/documents/{doc}{q}",
            json={"content": text},
            headers={"If-None-Match": "*"},
        )
        assert put.status_code == 200, put.text
    state = client.post(f"{API}/sdd/specs/s/documents/design/state{q}", json={"to": "approved"})
    assert state.status_code == 200, state.text


def _tasks_text(client: TestClient, space: str | None) -> str:
    text: str = client.get(f"{API}/sdd/specs/s/documents/tasks{_q(space)}").json()["content"]
    return text


def _task(client: TestClient, space: str | None, key: str) -> dict[str, Any]:
    tasks = client.get(f"{API}/sdd/specs/s/tasks{_q(space)}").json()
    found: dict[str, Any] = next(t for t in tasks if t["key"] == key)
    return found


def _rows(client: TestClient) -> dict[str, Any]:
    trace = client.get(f"{API}/sdd/specs/s/trace").json()
    return {r["id"]: r for r in trace["rows"]}


def _changed_lines(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def _run_task(client: TestClient, space: str | None, key: str, profile: str) -> dict[str, Any]:
    started = client.post(f"{API}/sdd/specs/s/tasks/{key}/actions/runs/{profile}{_q(space)}")
    assert started.status_code == 200, started.text
    body: dict[str, Any] = started.json()
    assert body["status"] == "started"
    snap = wait_run(client, body["run_id"], timeout=30) if not space else None
    if space:
        run_id = body["run_id"]
        snap = wait_for(
            lambda: (
                s
                if (s := client.get(f"{API}/runs/{run_id}?project={space}").json())["run"]["status"]
                in {"completed", "failed", "cancelled", "interrupted"}
                else None
            ),
            timeout=30,
        )
    assert snap is not None
    assert snap["run"]["status"] == "completed", snap["run"]
    return body


def test_standalone_spec_task_run_with_fake_backend(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed(client)  # 팀 구성 flow(fake 백엔드 에이전트 2개)
        _make_spec(client, None)
        info = client.get(f"{API}/sdd/info").json()
        assert info["capabilities"]["runs"] is True
        before = _tasks_text(client, None)
        body = _run_task(client, None, "1.1", "impl")
        run_id = body["run_id"]
        wait_for(lambda: _task(client, None, "1.1")["status"] == "done", timeout=10)
        assert _changed_lines(before, _tasks_text(client, None)) == [
            "-- [ ] 1.1 뼈대 [req: R1]",
            "+- [x] 1.1 뼈대 [req: R1]",
        ]
        page = client.get(f"{API}/runs/page?label=sdd.task=1.1&label=sdd.spec=s").json()
        [run] = page["items"]
        assert run["id"] == run_id
        assert run["origin"] == "sdd"
        assert run["labels"] == {
            "sdd.spec": "s",
            "sdd.task": "1.1",
            "sdd.profile": "impl",
            "sdd.purpose": "implement",
        }
        assert run["input"] == {"request": "작업 1.1 뼈대"}
        chips = _task(client, None, "1.1")["links"]
        assert [(c["ref"], c["status"]) for c in chips] == [(run_id, "completed")]

        verify = _run_task(client, None, "1.2", "verify")
        wait_for(lambda: _rows(client)["R2"]["verification"], timeout=10)
        rows = _rows(client)
        assert rows["R2"]["verification"]["status"] == "pass"
        assert rows["R2"]["results"][0]["ref"]["run_id"] == verify["run_id"]
        # 검증 프로필은 status_on이 비어 작업 줄이 그대로
        assert _task(client, None, "1.2")["status"] == "todo"


def test_project_spec_runs_go_to_project_records(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        modules = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        if modules.get("link-projects-sdd", {}).get("status") != "active":
            pytest.skip("link-projects-sdd(6R.14)가 켜지지 않은 조립")
        folder = tmp_path / "proj"
        folder.mkdir()
        register_project(client, "p1", folder)
        seed(client, graph_id="lib-only")  # 공용 구성에만
        for agent in ("fast", "slow"):
            doc = client.get(f"{API}/agents/{agent}").json()
            body = doc.get("agent", doc)
            r = client.post(f"{API}/agents?project=p1", json=body)
            assert r.status_code == 201, r.text
        graph = client.get(f"{API}/graphs/lib-only").json()
        graph = {**graph.get("graph", graph), "id": "flow"}
        r = client.post(f"{API}/graphs?project=p1", json=graph)
        assert r.status_code == 201, r.text
        _make_spec(client, "p1")

        view = client.get(f"{API}/sdd/specs/s?project=p1").json()
        missing = [i for i in view["issues"] if i["code"] == "sdd.profile_graph_missing"]
        assert [(i["details"]["graph"], i["details"]["in_library"]) for i in missing] == [
            ("lib-only", True)
        ]
        refused = client.post(f"{API}/sdd/specs/s/tasks/1.2/actions/runs/shared?project=p1")
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "project.not_imported"
        assert refused.json()["error"]["details"]["in_library"] is True

        before = _tasks_text(client, "p1")
        body = _run_task(client, "p1", "1.1", "impl")
        wait_for(lambda: _task(client, "p1", "1.1")["status"] == "done", timeout=10)
        assert len(_changed_lines(before, _tasks_text(client, "p1"))) == 2
        page = client.get(f"{API}/runs/page?project=p1&label=sdd.task=1.1").json()
        assert page["source"] == "project"
        assert [r["id"] for r in page["items"]] == [body["run_id"]]
        assert (folder / ".agent-console" / "records.sqlite3").is_file()
        # 앱 DB에는 없다
        app_page = client.get(f"{API}/runs/page?label=sdd.task=1.1").json()
        assert body["run_id"] not in [r["id"] for r in app_page["items"]]


def test_runs_module_off_turns_link_off(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["mod-runs"]})
    with server(settings) as client:
        modules = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert modules["link-runs-sdd"]["status"] != "active"
        made = client.post(f"{API}/sdd/specs", json={"name": "S"})
        assert made.status_code == 201, made.text
        info = client.get(f"{API}/sdd/info").json()
        assert info["capabilities"]["runs"] is False
        assert info["capabilities"]["verification"] is False
        tasks = client.get(f"{API}/sdd/specs/s/tasks").json()
        assert all(t["links"] == [] for t in tasks)
