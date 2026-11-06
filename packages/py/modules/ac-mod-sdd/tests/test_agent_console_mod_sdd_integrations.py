"""작업 연동(X43)·검증 출처(X42)·자동 진행(§6R.18 Q6·Q7): 연동이 없으면 빈 목록·능력 false·404,
있으면 동작·한꺼번에 시작(상한)·실행 칩·추적 검증 열."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_console_contracts import Issue
from agent_console_contracts.sdd import (
    AutomationState,
    ParsedTask,
    RunProfile,
    SpecIssue,
    TaskAction,
    VerificationResult,
)
from agent_console_mod_sdd.testing import integration_module, verification_module
from agent_console_sdd import SpecContext
from agent_console_sdd.testing import FakeTaskIntegration, FakeVerificationSource

API = "/api/v1"


@dataclass
class RunsLike(FakeTaskIntegration):
    """실행 연결을 내는 연동(``link_kinds``) + 자동 진행·프로필 검사 능력."""

    link_kinds: tuple[str, ...] = ("run",)
    state: AutomationState = field(
        default_factory=lambda: AutomationState(enabled=True, running=True)
    )
    ops: list[str] = field(default_factory=list)

    async def actions(self, ctx: SpecContext, task: ParsedTask) -> list[TaskAction]:
        found = await super().actions(ctx, task)
        if task.key == "2.1":  # 이 작업에서는 쓸 수 없다
            return [a.model_copy(update={"disabled": _issue()}) for a in found]
        return found

    def automation_state(self, ctx: SpecContext) -> AutomationState | None:
        return self.state

    async def control(self, ctx: SpecContext, op: str) -> AutomationState | None:
        self.ops.append(op)
        self.state = self.state.model_copy(update={"running": op == "resume"})
        return self.state

    async def check_profile(self, ctx: SpecContext, profile: RunProfile) -> list[SpecIssue]:
        return [
            SpecIssue(
                severity="warning",
                code="sdd.profile_graph_missing",
                message="없음",
                details={"profile": profile.id},
            )
        ]


def _issue() -> Issue:
    return Issue(severity="info", code="sdd.action_unavailable", message="안 됨")


def _spec(client: Any) -> None:
    made = client.post(f"{API}/sdd/specs", json={"name": "S", "template": "flow"})
    assert made.status_code == 201, made.text


def test_no_integration_means_empty_actions_and_404_automation(tmp_path: Path, kit: Any) -> None:
    kit.write_template(kit.spec_store(tmp_path / "ws" / "sdd"))
    with kit.client_for(kit.make_assembly(tmp_path)) as client:
        _spec(client)
        assert client.get(f"{API}/sdd/specs/s/tasks/1.1/actions").json() == []
        bulk = client.post(f"{API}/sdd/specs/s/bulk-actions", json={"task_keys": ["1.1", "1.2"]})
        assert bulk.json() == {"actions": [], "per_task": {"1.1": [], "1.2": []}}
        assert client.post(f"{API}/sdd/specs/s/automation/stop").status_code == 404
        view = client.get(f"{API}/sdd/specs/s").json()
        assert view["automation_state"] is None
        start = client.post(
            f"{API}/sdd/specs/s/bulk-start",
            json={"task_keys": ["1.1"], "action": {"integration": "runs", "id": "impl"}},
        )
        assert start.status_code == 409
        assert start.json()["error"]["code"] == "sdd.action_unavailable"


def test_integration_actions_links_bulk_and_automation(tmp_path: Path, kit: Any) -> None:
    kit.write_template(kit.spec_store(tmp_path / "ws" / "sdd"))
    runs = RunsLike(integration_id="runs")
    source = FakeVerificationSource(
        results=[VerificationResult(source="fake", status="pass", requirement_ids=["R1"], at=5.0)]
    )
    assembly = kit.make_assembly(
        tmp_path,
        integration_module(runs),
        verification_module(source),
        options={"max_bulk_start": 2},
    )
    with kit.client_for(assembly) as client:
        info = client.get(f"{API}/sdd/info").json()
        assert info["capabilities"]["runs"] is True
        assert info["capabilities"]["automation"] is True
        assert info["capabilities"]["verification"] is True
        _spec(client)
        actions = client.get(f"{API}/sdd/specs/s/tasks/1.1/actions").json()
        assert [(a["integration"], a["id"]) for a in actions] == [("runs", "impl")]
        invoked = client.post(f"{API}/sdd/specs/s/tasks/1.1/actions/runs/impl", json={"args": {}})
        assert invoked.status_code == 200, invoked.text
        assert invoked.json()["status"] == "started"
        assert client.post(f"{API}/sdd/specs/s/tasks/1.1/actions/nope/impl").status_code == 409
        assert client.get(f"{API}/sdd/specs/s/tasks/9.9/actions").status_code == 404

        tasks = client.get(f"{API}/sdd/specs/s/tasks").json()
        links = {t["key"]: [link["ref"] for link in t["links"]] for t in tasks}
        assert links == {"1.1": ["runs-1"], "1.2": [], "2.1": []}
        view = client.get(f"{API}/sdd/specs/s").json()
        assert view["automation_state"]["running"] is True
        assert "sdd.profile_graph_missing" in {i["code"] for i in view["issues"]}

        bulk = client.post(
            f"{API}/sdd/specs/s/bulk-actions", json={"task_keys": ["1.2", "2.1", "zz"]}
        ).json()
        assert [a["id"] for a in bulk["actions"]] == ["impl"]
        assert bulk["actions"][0].get("disabled") is None
        assert bulk["per_task"] == {
            "1.2": [{"integration": "runs", "id": "impl"}],
            "2.1": [],
            "zz": [],
        }

        action = {"integration": "runs", "id": "impl"}
        too_many = client.post(
            f"{API}/sdd/specs/s/bulk-start",
            json={"task_keys": ["1.1", "1.2", "2.1"], "action": action},
        )
        assert too_many.status_code == 422
        started = client.post(
            f"{API}/sdd/specs/s/bulk-start", json={"task_keys": ["1.2", "2.1"], "action": action}
        ).json()
        assert [(i["task_key"], i["status"]) for i in started["items"]] == [
            ("1.2", "started"),
            ("2.1", "failed"),
        ]
        assert started["items"][1]["issue"]["code"] == "sdd.action_unavailable"

        trace = client.get(f"{API}/sdd/specs/s/trace").json()
        rows = {r["id"]: r for r in trace["rows"]}
        assert rows["R1"]["verification"]["status"] == "pass"
        assert [r["ref"] for r in rows["R1"]["runs"]]  # 실행 칩

        # 자동 진행: 규칙에서 꺼져 있으면 다시 시작 409, 멈춤은 연동에 위임
        assert client.post(f"{API}/sdd/specs/s/automation/resume").status_code == 409
        stopped = client.post(f"{API}/sdd/specs/s/automation/stop")
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["running"] is False
        assert runs.ops == ["stop"]
        assert client.post(f"{API}/sdd/specs/s/automation/jump").status_code == 404


def test_verification_source_can_be_turned_off_in_settings(tmp_path: Path, kit: Any) -> None:
    source = FakeVerificationSource(source_id="fake")
    settings = {"sdd": {"verification_sources": [{"id": "fake", "enabled": False}]}}
    assembly = kit.make_assembly(tmp_path, verification_module(source), settings=settings)
    with kit.client_for(assembly) as client:
        assert client.get(f"{API}/sdd/info").json()["capabilities"]["verification"] is False
