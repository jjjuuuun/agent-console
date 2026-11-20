"""실행 결과로 문서 상태 바꾸기(6R.34, 프로필 ``document_state_on``, 가짜 실행 모듈).

성공(``by: run``·``run_id``·버전 기록 메시지), 사람만 할 수 있는 전환 → 바꾸지 않고 정보 이슈,
``document_state`` 관문 막힘 → 이슈(``gate_id``), 비움 → 스펙 파일 불변, 실행 상태별 매핑(결과
이름·실행 상태 이름), 작업 줄 반영과 독립, ``mod-runs`` 없음 → 동작 없음(R0).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

API = "/api/v1"
NOT_APPLIED = "sdd.document_state_not_applied"


def _template(
    kit: Any,
    *,
    document_state_on: dict[str, Any] | None = None,
    transitions: list[dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
    status_on: dict[str, str] | None = None,
    run_gate: bool = True,
) -> dict[str, Any]:
    rules = dict(kit.TEMPLATE["rules"])
    rules["document_states"] = [
        {"id": "draft"},
        {"id": "approved"},
        {"id": "review"},
        {"id": "rejected"},
    ]
    rules["transitions"] = (
        transitions
        if transitions is not None
        else [
            {"from": "draft", "to": "approved", "by": ["human"]},
            {"from": "approved", "to": "review", "by": ["human", "run"]},
            {"from": "*", "to": "rejected", "by": ["run"]},
            {"from": "*", "to": "draft", "by": ["human"]},
        ]
    )
    rules["gates"] = [*(kit.TEMPLATE["rules"]["gates"] if run_gate else []), *(gates or [])]
    impl = dict(rules["run_profiles"][0])
    if document_state_on is not None:
        impl["document_state_on"] = document_state_on
    if status_on is not None:
        impl["status_on"] = status_on
    rules["run_profiles"] = [impl, *rules["run_profiles"][1:]]
    return {**kit.TEMPLATE, "rules": rules}


def _start(env: Any, key: str = "1.1", profile: str = "impl") -> str:
    r = env.client.post(env.q(f"/sdd/specs/s/tasks/{key}/actions/runs/{profile}"), json={})
    assert r.status_code == 200, r.text
    run_id: str = r.json()["run_id"]
    return run_id


def _design(env: Any) -> dict[str, Any]:
    doc = env.store.get("spec", "s").document
    found: dict[str, Any] = next(d for d in doc["documents"] if d["id"] == "design")
    return found


def _spec_file(tmp_path: Path, kit: Any) -> Path:
    [path] = list((tmp_path / str(kit.SPACE)).rglob("s.yaml"))
    return path


def _doc_issues(env: Any, key: str = "1.1") -> list[dict[str, Any]]:
    return [i for i in env.task(key)["issues"] if i["code"] == NOT_APPLIED]


def test_succeeded_changes_document_state_by_run(tmp_path: Path, kit: Any) -> None:
    template = _template(
        kit, document_state_on={"succeeded": {"document": "design", "to": "review"}}
    )
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        run_id = _start(env)
        assert _design(env)["state"] == "approved"  # 시작(started)에는 항목이 없다
        env.runs.finish(run_id, "completed")
        design = _design(env)
        assert design["state"] == "review"
        assert design["state_changed"]["by"] == "run"
        assert design["state_changed"]["run_id"] == run_id
        text = _spec_file(tmp_path, kit).read_text(encoding="utf-8")
        assert "review" in text
        assert run_id in text
        latest = env.store.list_versions("spec", "s")[0]
        assert latest.message == "문서 상태: design → review (run)"
        # 작업 줄 반영(status_on)도 함께 — 서로 독립
        task = env.task("1.1")
        assert task["status"] == "review"
        assert _doc_issues(env) == []
        view = env.client.get(env.q("/sdd/specs/s")).json()
        assert {d["id"]: d.get("state") for d in view["spec"]["documents"]}["design"] == "review"
        assert not [i for i in view["issues"] if "document_state_on" in (i.get("path") or "")]


def test_human_only_transition_is_not_applied_with_info_issue(tmp_path: Path, kit: Any) -> None:
    template = _template(
        kit,
        document_state_on={"succeeded": {"document": "design", "to": "review"}},
        transitions=[
            {"from": "draft", "to": "approved", "by": ["human"]},
            {"from": "approved", "to": "review", "by": ["human"]},
        ],
    )
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        # 규칙 검사가 미리 알린다(warning)
        view = env.client.get(env.q("/sdd/specs/s")).json()
        [warn] = [i for i in view["issues"] if i["code"] == "sdd.transition_denied"]
        assert warn["severity"] == "warning"
        assert warn["path"] == "/run_profiles/0/document_state_on/succeeded/to"
        before = _spec_file(tmp_path, kit).read_bytes()
        run_id = _start(env)
        env.runs.finish(run_id, "completed")
        assert _design(env)["state"] == "approved"
        [issue] = _doc_issues(env)
        assert issue["severity"] == "info"
        assert issue["task_key"] == "1.1"
        assert issue["details"]["reason"] == "transition_denied"
        assert issue["details"]["document_id"] == "design"
        assert issue["details"]["to"] == "review"
        assert issue["details"]["run_id"] == run_id
        assert "gate_id" not in issue["details"]
        # 작업 줄은 그대로 반영됐다(하나가 막혀도 다른 하나는 시도)
        assert env.task("1.1")["status"] == "review"
        assert _spec_file(tmp_path, kit).read_bytes() == before  # 스펙 YAML 불변


def test_document_state_gate_blocks_with_gate_id(tmp_path: Path, kit: Any) -> None:
    gate = {
        "id": "review-by-human",
        "applies_to": ["document_state"],
        "message": "검토 중으로는 사람만",
        "require": {
            "any": [
                {"path": "/change/to", "op": "ne", "value": "review"},
                {"path": "/change/by", "op": "eq", "value": "human"},
            ]
        },
    }
    template = _template(
        kit,
        document_state_on={"succeeded": {"document": "design", "to": "review"}},
        gates=[gate],
    )
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        run_id = _start(env)
        env.runs.finish(run_id, "completed")
        assert _design(env)["state"] == "approved"
        [issue] = _doc_issues(env)
        assert issue["details"]["reason"] == "gate_blocked"
        assert issue["details"]["gate_id"] == "review-by-human"


def test_missing_document_is_not_applied(tmp_path: Path, kit: Any) -> None:
    template = _template(
        kit, document_state_on={"succeeded": {"document": "ghost", "to": "review"}}
    )
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        view = env.client.get(env.q("/sdd/specs/s")).json()
        assert any(
            i["code"] == "sdd.not_found"
            and i["path"] == "/run_profiles/0/document_state_on/succeeded/document"
            for i in view["issues"]
        )
        run_id = _start(env)
        env.runs.finish(run_id, "completed")
        [issue] = _doc_issues(env)
        assert issue["details"]["reason"] == "document_not_found"
        assert issue["details"]["document_id"] == "ghost"


def test_empty_document_state_on_keeps_spec_file(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path, template=_template(kit, status_on={})) as env:
        env.approve()
        before = _spec_file(tmp_path, kit).read_bytes()
        versions = len(env.store.list_versions("spec", "s"))
        run_id = _start(env)
        env.runs.finish(run_id, "completed")
        assert _spec_file(tmp_path, kit).read_bytes() == before
        assert len(env.store.list_versions("spec", "s")) == versions
        assert _doc_issues(env) == []


def test_mapping_by_run_status_and_outcome(tmp_path: Path, kit: Any) -> None:
    """결과 이름(failed)과 실행 상태 이름(cancelled — 결과 이름도 같음, completed — 결과 이름은
    succeeded)으로 찾는다. 그 실행 상태에 항목이 없으면 바꾸지 않는다."""
    template = _template(
        kit,
        document_state_on={
            "failed": {"document": "design", "to": "rejected"},
            "completed": {"document": "design", "to": "review"},
        },
        status_on={},
        run_gate=False,  # 설계가 승인 밖으로 나가도 다음 실행을 시작할 수 있게
    )
    with kit.open_env(tmp_path, template=template) as env:
        env.approve()
        cancelled = _start(env)
        env.runs.finish(cancelled, "cancelled")
        assert _design(env)["state"] == "approved"  # 항목 없음 = 그대로
        done = _start(env)
        env.runs.finish(done, "completed")  # 결과 이름 succeeded에 없으면 실행 상태 이름
        assert _design(env)["state"] == "review"
        failed = _start(env, "2.1")
        env.runs.finish(failed, "failed")
        design = _design(env)
        assert design["state"] == "rejected"
        assert design["state_changed"]["run_id"] == failed
        # 이미 그 상태면 아무것도 하지 않는다(같은 상태로의 전환 규칙이 없어도 이슈 없음)
        versions = len(env.store.list_versions("spec", "s"))
        again = _start(env, "2.1")
        env.runs.finish(again, "failed")
        assert len(env.store.list_versions("spec", "s")) == versions
        assert _doc_issues(env, "2.1") == []


def test_without_runs_module_nothing_happens(tmp_path: Path, kit: Any) -> None:
    template = _template(
        kit, document_state_on={"succeeded": {"document": "design", "to": "review"}}
    )
    assembly, _, _ = kit.build_env(tmp_path, with_runs=False, template=template)
    assert "link-runs-sdd" not in assembly.parts
    with kit.client_for(assembly) as client:
        q = f"?project={kit.SPACE}"
        made = client.post(f"{API}/sdd/specs{q}", json={"name": "S", "template": "flow"})
        assert made.status_code == 201, made.text
        assert client.get(f"{API}/sdd/info{q}").json()["capabilities"]["runs"] is False
        # 사람의 상태 전환·작업 목록은 그대로 동작한다
        moved = client.post(f"{API}/sdd/specs/s/documents/design/state{q}", json={"to": "approved"})
        assert moved.status_code == 200, moved.text
        moved = client.post(f"{API}/sdd/specs/s/documents/design/state{q}", json={"to": "review"})
        assert moved.status_code == 200, moved.text
        assert moved.json()["spec"]["documents"][1]["state_changed"]["by"] == "human"
        tasks = client.get(f"{API}/sdd/specs/s/tasks{q}").json()
        assert all(i["code"] != NOT_APPLIED for t in tasks for i in t["issues"])
