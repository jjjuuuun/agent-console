"""link-runs-sdd 흐름(6R.15 완료 기준, 가짜 실행 모듈): 동작·관문·실행 라벨·결과 반영(줄 하나)·
``status_on`` 비움·실행 중 줄 바뀜·``task_status`` 관문·검증 결과·한꺼번에 시작·프로필 검사·비밀."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

API = "/api/v1"


def _diff(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def test_actions_follow_when_and_run_gate(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        info = env.client.get(env.q("/sdd/info")).json()
        assert info["capabilities"]["runs"] is True
        assert info["capabilities"]["verification"] is True
        actions = env.client.get(env.q("/sdd/specs/s/tasks/1.1/actions")).json()
        assert [(a["integration"], a["id"]) for a in actions] == [
            ("runs", "impl"),
            ("runs", "verify"),
        ]
        assert all(a["disabled"]["code"] == "sdd.gate_blocked" for a in actions)
        # when(owner 있음)이 맞지 않는 작업에는 구현 프로필이 없다
        actions = env.client.get(env.q("/sdd/specs/s/tasks/1.2/actions")).json()
        assert [a["id"] for a in actions] == ["verify"]
        # 관문 막힘 = 422 sdd.gate_blocked(문서 id 포함), 실행 없음
        blocked = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={})
        assert blocked.status_code == 422, blocked.text
        err = blocked.json()["error"]
        assert err["code"] == "sdd.gate_blocked"
        assert err["details"]["gate_id"] == "design-approved"
        assert err["details"]["document_ids"] == ["design"]
        assert env.runs.started == []
        env.approve()
        actions = env.client.get(env.q("/sdd/specs/s/tasks/1.1/actions")).json()
        assert all(a["disabled"] is None for a in actions)
        # when이 맞지 않는 작업에 그 동작 = 409 sdd.action_unavailable
        wrong = env.client.post(env.q("/sdd/specs/s/tasks/1.2/actions/runs/impl"), json={})
        assert wrong.status_code == 409
        assert wrong.json()["error"]["code"] == "sdd.action_unavailable"


def test_run_labels_and_status_on_change_only_task_line(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        before = env.tasks_text()
        started = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={})
        assert started.status_code == 200, started.text
        body = started.json()
        assert body["status"] == "started"
        run_id = body["run_id"]
        [call] = env.runs.started
        assert call["graph_id"] == "team-x"
        assert call["origin"] == "sdd"
        assert call["project_id"] == kit.SPACE
        assert call["input"] == {"request": "작업 1.1 뼈대 담당 be"}
        assert call["labels"] == {
            "sdd.spec": "s",
            "sdd.task": "1.1",
            "sdd.profile": "impl",
            "sdd.purpose": "implement",
        }
        # 시작 이벤트(시작 요청 중에 온 것)로 status_on.started → doing
        after_start = env.tasks_text()
        assert _diff(before, after_start) == [
            "-- [ ] 1.1 뼈대 [req: R1] [owner: be]",
            "+- [~] 1.1 뼈대 [req: R1] [owner: be]",
        ]
        env.runs.finish(run_id, "completed")
        after = env.tasks_text()
        assert _diff(before, after) == [
            "-- [ ] 1.1 뼈대 [req: R1] [owner: be]",
            "+- [?] 1.1 뼈대 [req: R1] [owner: be]",
        ]
        task = env.task("1.1")
        assert task["status"] == "review"
        [link] = task["links"]
        assert (link["integration"], link["kind"], link["ref"]) == ("runs", "run", run_id)
        assert (link["status"], link["profile"], link["purpose"]) == (
            "completed",
            "impl",
            "implement",
        )
        assert task["issues"] == []
        # 같은 이벤트가 다시 와도 한 번만 반영
        env.runs.finish(run_id, "completed")
        assert env.tasks_text() == after


def test_empty_status_on_keeps_file_and_shows_chip(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        before = env.tasks_text()
        run_id = env.client.post(
            env.q("/sdd/specs/s/tasks/1.2/actions/runs/verify"), json={}
        ).json()["run_id"]
        env.runs.finish(run_id, "completed")
        assert env.tasks_text() == before
        task = env.task("1.2")
        assert [link["ref"] for link in task["links"]] == [run_id]
        assert task["issues"] == []


def test_line_changed_during_run_is_not_applied(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        run_id = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={}).json()[
            "run_id"
        ]
        task = env.task("1.1")
        assert task["status"] == "doing"
        # 실행 중에 사람이 그 줄을 고친다(필드 하나)
        patched = env.client.patch(
            env.q("/sdd/specs/s/tasks/1.1"),
            json={"fields": {"owner": "fe"}, "expected_line_hash": task["line_hash"]},
        )
        assert patched.status_code == 200, patched.text
        before = env.tasks_text()
        env.runs.finish(run_id, "completed")
        assert env.tasks_text() == before  # 반영 안 함
        task = env.task("1.1")
        assert task["status"] == "doing"
        [issue] = [i for i in task["issues"] if i["code"] == "sdd.status_not_applied"]
        assert issue["severity"] == "info"
        assert issue["details"]["reason"] == "task_changed"
        assert issue["details"]["run_id"] == run_id
        assert issue["details"]["status"] == "review"


def test_task_status_gate_blocks_status_on_with_info_issue(tmp_path: Path, kit: Any) -> None:
    template = {
        **kit.TEMPLATE,
        "rules": {
            **kit.TEMPLATE["rules"],
            "gates": [
                *kit.TEMPLATE["rules"]["gates"],
                {
                    "id": "no-review-by-run",
                    "applies_to": ["task_status"],
                    "message": "검토 대기로는 사람만",
                    "require": {
                        "any": [
                            {"path": "/change/to", "op": "ne", "value": "review"},
                            {"path": "/change/by", "op": "eq", "value": "human"},
                        ]
                    },
                },
            ],
        },
    }
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        run_id = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={}).json()[
            "run_id"
        ]
        assert env.task("1.1")["status"] == "doing"  # started → doing은 통과
        before = env.tasks_text()
        env.runs.finish(run_id, "completed")
        assert env.tasks_text() == before
        [issue] = [i for i in env.task("1.1")["issues"] if i["code"] == "sdd.status_not_applied"]
        assert issue["details"]["reason"] == "gate_blocked"
        assert issue["details"]["gate_id"] == "no-review-by-run"


def test_verification_results_feed_trace(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        run_id = env.client.post(
            env.q("/sdd/specs/s/tasks/1.1/actions/runs/verify"), json={}
        ).json()["run_id"]
        env.runs.finish(run_id, "completed")
        failing = env.client.post(
            env.q("/sdd/specs/s/tasks/1.2/actions/runs/verify"), json={}
        ).json()["run_id"]
        env.runs.finish(failing, "failed")
        rows = {r["id"]: r for r in env.client.get(env.q("/sdd/specs/s/trace")).json()["rows"]}
        assert rows["R1"]["verification"]["status"] == "pass"
        assert rows["R1"]["verification"]["source"] == "runs"
        assert [r["ref"]["run_id"] for r in rows["R1"]["results"]] == [run_id]
        assert rows["R2"]["verification"]["status"] == "fail"
        assert "verification_failed" in rows["R2"]["gaps"]
        assert {link["ref"] for link in rows["R1"]["runs"]} == {run_id}


def test_bulk_actions_union_and_bulk_start(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        bulk = env.client.post(
            env.q("/sdd/specs/s/bulk-actions"), json={"task_keys": ["1.1", "1.2", "2.1"]}
        ).json()
        assert [(a["integration"], a["id"]) for a in bulk["actions"]] == [
            ("runs", "impl"),
            ("runs", "verify"),
        ]
        ids = {k: [a["id"] for a in v] for k, v in bulk["per_task"].items()}
        assert ids == {"1.1": ["impl", "verify"], "1.2": ["verify"], "2.1": ["impl", "verify"]}
        started = env.client.post(
            env.q("/sdd/specs/s/bulk-start"),
            json={
                "task_keys": ["1.1", "1.2", "9.9"],
                "action": {"integration": "runs", "id": "impl"},
            },
        ).json()
        items = {i["task_key"]: i for i in started["items"]}
        assert items["1.1"]["status"] == "started"
        assert items["1.2"]["status"] == "failed"
        assert items["1.2"]["issue"]["code"] == "sdd.action_unavailable"
        assert items["9.9"]["issue"]["code"] == "sdd.not_found"
        assert len(env.runs.started) == 1


def test_bulk_start_reports_blocked_per_task(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        # 관문이 막으면 작업별 blocked(sdd.gate_blocked), 실행 없음
        started = env.client.post(
            env.q("/sdd/specs/s/bulk-start"),
            json={"task_keys": ["1.1"], "action": {"integration": "runs", "id": "impl"}},
        ).json()
        [item] = started["items"]
        assert item["status"] == "blocked"
        assert item["issue"]["code"] == "sdd.gate_blocked"
        assert item["issue"]["details"]["gate_id"] == "design-approved"
        assert env.runs.started == []


def test_profile_graph_check_and_not_imported(tmp_path: Path, kit: Any) -> None:
    from agent_console_link_runs_sdd.testing import FakeRuns

    runs = FakeRuns(graphs={kit.SPACE: {"team-x"}}, library={"qa"})
    with kit.open_env(tmp_path, runs=runs) as env:
        view = env.client.get(env.q("/sdd/specs/s")).json()
        missing = [i for i in view["issues"] if i["code"] == "sdd.profile_graph_missing"]
        assert [(i["details"]["graph"], i["details"]["in_library"]) for i in missing] == [
            ("qa", True)
        ]
        assert missing[0]["path"] == "/run_profiles/1/graph"
        env.approve()
        refused = env.client.post(env.q("/sdd/specs/s/tasks/1.2/actions/runs/verify"), json={})
        assert refused.status_code == 422, refused.text
        err = refused.json()["error"]
        assert err["code"] == "project.not_imported"
        assert err["details"]["in_library"] is True


def test_secret_in_run_input_reject_and_warn(tmp_path: Path, kit: Any) -> None:
    secret = "sk-ant-api03-" + "a" * 40
    template = {
        **kit.TEMPLATE,
        "rules": {
            **kit.TEMPLATE["rules"],
            "run_profiles": [
                {
                    "id": "impl",
                    "title": "구현",
                    "graph": "team-x",
                    "input": {"request": f"키 {secret} 작업 {{task_id}}"},
                }
            ],
        },
    }
    with kit.open_env(
        tmp_path / "r", template=template, settings={"sdd": {"secret_scan": "reject"}}
    ) as env:
        env.approve()
        refused = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={})
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "sdd.secret_rejected"
        assert secret not in refused.text
        assert env.runs.started == []
    with kit.open_env(tmp_path / "w", template=template) as env:
        env.approve()
        ok = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={})
        assert ok.status_code == 200
        assert ok.json()["issue"]["code"] == "sdd.secret_suspect"
        assert secret not in ok.text


def test_without_runs_module_link_is_off(tmp_path: Path, kit: Any) -> None:
    assembly, _, _ = kit.build_env(tmp_path, with_runs=False)
    assert "link-runs-sdd" not in assembly.parts  # 필수 포트(runs.*)가 없어 꺼짐
    with kit.client_for(assembly) as client:
        q = f"?project={kit.SPACE}"
        made = client.post(f"{API}/sdd/specs{q}", json={"name": "S", "template": "flow"})
        assert made.status_code == 201
        info = client.get(f"{API}/sdd/info{q}").json()
        assert info["capabilities"]["runs"] is False
        assert client.get(f"{API}/sdd/specs/s/tasks/1.1/actions{q}").json() == []
        tasks = client.get(f"{API}/sdd/specs/s/tasks{q}").json()
        assert all(t["links"] == [] for t in tasks)
        assert client.get(f"{API}/sdd/specs/s/trace{q}").status_code == 200


def test_standalone_spec_runs_have_no_project(tmp_path: Path, kit: Any) -> None:
    assembly, runs, _ = kit.build_env(tmp_path)
    with kit.client_for(assembly) as client:
        from agent_console_sdd import definition_kinds
        from agent_console_store import FileDefinitionStore

        root = FileDefinitionStore(
            tmp_path / "ws" / "sdd",
            definition_kinds(
                spec_kind="spec",
                spec_directory="specs",
                template_kind="spec-template",
                template_directory="spec-templates",
            ),
        )
        created = root.create("spec-template", kit.TEMPLATE)
        root.write_files(
            "spec-template",
            "flow",
            {"tasks.md": kit.TASKS.encode(), "design.md": b"# d\n", "req.md": b"**R1** a\n"},
            expected_version=created.version_hash,
        )
        assert (
            client.post(f"{API}/sdd/specs", json={"name": "S", "template": "flow"}).status_code
            == 201
        )
        state = client.post(f"{API}/sdd/specs/s/documents/design/state", json={"to": "approved"})
        assert state.status_code == 200, state.text
        r = client.post(f"{API}/sdd/specs/s/tasks/1.1/actions/runs/impl", json={})
        assert r.status_code == 200, r.text
        assert runs.started[0]["project_id"] is None
        tasks = client.get(f"{API}/sdd/specs/s/tasks").json()
        assert [link["ref"] for t in tasks for link in t["links"]] == [r.json()["run_id"]]
