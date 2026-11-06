"""자동 진행(6R.16 완료 기준, 가짜 실행 모듈 — SDK 실호출 없음).

작업 4개·의존 2층 스펙이 끝까지 진행, 멈춤 뒤 새 실행 0·진행 중 실행 유지, ``stopped_reason``
(user·stage_done·spec_done·failures), 실패 대본 → 3회 뒤 건너뜀·멈춤, 단계 끝 멈춤, 다른
``host_id`` 실행 무시, 재시작 뒤 이어 감, 꺼짐 기본에서 아무 실행도 시작하지 않음.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import Run, RunStatus
from agent_console_link_runs_sdd import AUTOMATION_SKIPPED, RunsTaskIntegration, SpecAutomation
from agent_console_link_runs_sdd.ports import SDD_INTEGRATIONS
from agent_console_link_runs_sdd.testing import FakeRuns
from agent_console_store import FileDefinitionStore

SPACE = "p1"
TASKS = (
    "# 작업\n\n## 1단계\n\n"
    "- [ ] 1.1 가 [owner: be]\n"
    "- [ ] 1.2 나 [owner: be]\n\n"
    "## 2단계\n\n"
    "- [ ] 2.1 다 [depends: 1.1, 1.2] [owner: be]\n"
    "- [ ] 2.2 라 [depends: 1.1] [owner: be]\n"
)
TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "auto",
    "name": "자동",
    "documents": [{"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]}],
    "rules": {
        "task_statuses": [
            {"id": "todo", "marker": " "},
            {"id": "doing", "marker": "~"},
            {"id": "done", "marker": ["x", "X"], "done": True},
        ],
        "run_profiles": [
            {
                "id": "impl",
                "title": "구현",
                "graph": "team-x",
                "input": {"request": "작업 {task_id}"},
                "status_on": {"started": "doing", "succeeded": "done", "failed": "todo"},
            },
            {"id": "verify", "title": "검증", "graph": "qa", "purpose": "verify"},
        ],
    },
}


def _template(automation: Mapping[str, Any] | None) -> dict[str, Any]:
    doc = copy.deepcopy(TEMPLATE)
    if automation is not None:
        doc["rules"]["automation"] = dict(automation)
    return doc


def _store(tmp_path: Path, kit: Any, automation: Mapping[str, Any] | None) -> FileDefinitionStore:
    from agent_console_sdd import definition_kinds

    store = FileDefinitionStore(
        tmp_path / SPACE,
        definition_kinds(
            spec_kind="spec",
            spec_directory="specs",
            template_kind="spec-template",
            template_directory="spec-templates",
        ),
    )
    doc = _template(automation)
    created = store.create(doc["kind"], doc)
    store.write_files(
        doc["kind"], doc["id"], {"tasks.md": TASKS.encode()}, expected_version=created.version_hash
    )
    return store


@dataclass
class Auto:
    client: TestClient
    runs: FakeRuns
    store: FileDefinitionStore
    automation: SpecAutomation
    api: str

    def q(self, path: str) -> str:
        sep = "&" if "?" in path else "?"
        return f"{self.api}{path}{sep}project={SPACE}"

    def view(self) -> dict[str, Any]:
        """스펙 보기(자동 진행 상태 — 켜져 있으면 차례를 맡긴다) 뒤 차례가 끝나기를 기다린다."""
        r = self.client.get(self.q("/sdd/specs/s"))
        assert r.status_code == 200, r.text
        self.automation.join()
        body: dict[str, Any] = self.client.get(self.q("/sdd/specs/s")).json()
        self.automation.join()
        return body

    def state(self) -> dict[str, Any]:
        found: dict[str, Any] = self.view()["automation_state"]
        return found

    def statuses(self) -> dict[str, str]:
        tasks = self.client.get(self.q("/sdd/specs/s/tasks")).json()
        return {t["key"]: t["status"] for t in tasks}

    def task(self, key: str) -> dict[str, Any]:
        tasks = self.client.get(self.q("/sdd/specs/s/tasks")).json()
        found: dict[str, Any] = next(t for t in tasks if t["key"] == key)
        return found

    def started_keys(self) -> list[str]:
        return [c["labels"]["sdd.task"] for c in self.runs.started]

    def running(self) -> dict[str, str]:
        """진행 중 Run: 작업 키 → Run id."""
        return {
            r.labels["sdd.task"]: r.id
            for r in self.runs.runs.values()
            if r.status == "running" and "sdd.task" in r.labels
        }

    def finish(self, key: str, status: str = "completed") -> None:
        self.runs.finish(self.running()[key], status)
        self.automation.join()

    def post(self, op: str) -> dict[str, Any]:
        r = self.client.post(self.q(f"/sdd/specs/s/automation/{op}"))
        assert r.status_code == 200, r.text
        self.automation.join()
        body: dict[str, Any] = r.json()
        return body


@contextmanager
def open_auto(
    tmp_path: Path,
    kit: Any,
    automation: Mapping[str, Any] | None,
    *,
    runs: FakeRuns | None = None,
    store: FileDefinitionStore | None = None,
    create: bool = True,
) -> Iterator[Auto]:
    store = store or _store(tmp_path, kit, automation)
    fake = runs or FakeRuns(graphs={SPACE: {"team-x", "qa"}}, host="me")
    assembly, fake, store = kit.build_env(tmp_path, runs=fake, store=store)
    [integration] = assembly.ports(SDD_INTEGRATIONS)
    assert isinstance(integration, RunsTaskIntegration)
    assert integration.automation is not None
    with kit.client_for(assembly) as client:
        env = Auto(client, fake, store, integration.automation, kit.API)
        if create:
            made = client.post(env.q("/sdd/specs"), json={"name": "S", "template": "auto"})
            assert made.status_code == 201, made.text
        yield env


SPEC_SCOPE = {"enabled": True, "profile": "impl", "max_parallel": 2, "scope": "spec"}


def test_off_by_default_starts_nothing(tmp_path: Path, kit: Any) -> None:
    with open_auto(tmp_path, kit, None) as env:
        info = env.client.get(env.q("/sdd/info")).json()
        assert info["capabilities"]["automation"] is True  # 연동이 지원(스펙마다 켬)
        state = env.state()
        assert state == {
            "enabled": False,
            "running": False,
            "active_runs": [],
            "skipped_keys": [],
            "failures": {},
            "stopped_reason": None,
        }
        # 사람이 시작한 실행이 끝나도 자동으로 아무것도 시작하지 않는다
        r = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/runs/impl"), json={})
        assert r.status_code == 200, r.text
        env.finish("1.1")
        env.view()
        assert env.started_keys() == ["1.1"]
        # 꺼진 규칙에서는 다시 시작도 거부(409)
        resume = env.client.post(env.q("/sdd/specs/s/automation/resume"))
        assert resume.status_code == 409
        assert env.started_keys() == ["1.1"]


def test_four_tasks_two_layers_run_to_the_end(tmp_path: Path, kit: Any) -> None:
    with open_auto(tmp_path, kit, SPEC_SCOPE) as env:
        state = env.state()
        assert sorted(env.started_keys()) == ["1.1", "1.2"]  # max_parallel 2, 준비된 것만
        assert state["enabled"] is True
        assert state["running"] is True
        assert len(state["active_runs"]) == 2
        assert env.statuses() == {"1.1": "doing", "1.2": "doing", "2.1": "todo", "2.2": "todo"}
        env.finish("1.1")  # 2.2가 준비됨(1.1에만 의존)
        assert env.started_keys()[-1] == "2.2"
        env.finish("1.2")  # 2.1이 준비됨
        assert env.started_keys()[-1] == "2.1"
        env.finish("2.2")
        env.finish("2.1")
        assert sorted(env.started_keys()) == ["1.1", "1.2", "2.1", "2.2"]
        assert set(env.statuses().values()) == {"done"}
        state = env.state()
        assert state["stopped_reason"] == "spec_done"
        assert state["running"] is False
        assert state["active_runs"] == []


def test_stop_blocks_new_runs_and_keeps_running_ones(tmp_path: Path, kit: Any) -> None:
    with open_auto(tmp_path, kit, {**SPEC_SCOPE, "max_parallel": 1}) as env:
        env.view()
        assert env.started_keys() == ["1.1"]
        run_id = env.running()["1.1"]
        stopped = env.post("stop")
        assert stopped["stopped_reason"] == "user"
        assert stopped["running"] is False
        assert stopped["active_runs"] == [run_id]  # 진행 중 실행은 끊지 않는다
        assert env.runs.runs[run_id].status == "running"
        env.finish("1.1")
        env.view()
        assert env.started_keys() == ["1.1"]  # 멈춤 뒤 새 실행 0
        assert env.statuses()["1.1"] == "done"  # 결과 반영은 그대로
        resumed = env.post("resume")
        assert resumed["stopped_reason"] is None
        assert resumed["running"] is True
        assert env.started_keys() == ["1.1", "1.2"]


def test_stage_scope_stops_at_stage_end(tmp_path: Path, kit: Any) -> None:
    with open_auto(tmp_path, kit, {**SPEC_SCOPE, "scope": "stage"}) as env:
        env.view()
        assert sorted(env.started_keys()) == ["1.1", "1.2"]
        env.finish("1.1")
        assert sorted(env.started_keys()) == ["1.1", "1.2"]  # 2.2는 다음 단계라 시작하지 않음
        env.finish("1.2")
        state = env.state()
        assert state["stopped_reason"] == "stage_done"
        assert state["running"] is False
        assert len(env.started_keys()) == 2
        env.post("resume")  # 다음 단계
        assert sorted(env.started_keys()[2:]) == ["2.1", "2.2"]


def test_three_failures_skip_task_and_stop(tmp_path: Path, kit: Any) -> None:
    with open_auto(tmp_path, kit, {**SPEC_SCOPE, "max_parallel": 1, "max_failures": 3}) as env:
        env.view()
        for attempt in range(1, 4):
            assert env.started_keys().count("1.1") == attempt
            env.finish("1.1", "failed")
        state = env.state()
        assert state["skipped_keys"] == ["1.1"]
        assert state["failures"] == {"1.1": 3}
        assert env.started_keys().count("1.1") == 3  # 3회 뒤 더 시작하지 않음
        assert env.started_keys()[-1] == "1.2"  # 다른 작업은 이어 감
        env.finish("1.2")
        state = env.state()
        # 남은 작업(2.1·2.2)은 건너뛴 1.1에 막힘 → 멈춤
        assert state["stopped_reason"] == "failures"
        assert state["running"] is False
        assert env.started_keys().count("2.1") == 0
        issue = next(i for i in env.task("1.1")["issues"] if i["code"] == AUTOMATION_SKIPPED)
        assert issue["severity"] == "info"
        assert issue["details"]["failures"] == 3
        # 다시 시작 → 실패 수·건너뜀을 지우고 다시 시도
        resumed = env.post("resume")
        assert resumed["skipped_keys"] == []
        assert env.started_keys().count("1.1") == 4


def test_other_host_runs_are_ignored(tmp_path: Path, kit: Any) -> None:
    fake = FakeRuns(graphs={SPACE: {"team-x", "qa"}}, host="me")

    def put(run_id: str, task: str, status: RunStatus, host: str, at: float) -> None:
        fake.runs[run_id] = Run(
            id=run_id,
            graph_id="team-x",
            graph_version="v",
            status=status,
            input={},
            origin="sdd",
            project_id=SPACE,
            host_id=host,
            created_at=at,
            labels={"sdd.spec": "s", "sdd.task": task, "sdd.profile": "impl"},
        )

    for i in range(3):  # 다른 앱에서 1.1이 세 번 실패
        put(f"other-f{i}", "1.1", "failed", "other", 1.0 + i)
    put("other-run", "1.2", "running", "other", 5.0)  # 다른 앱에서 1.2 실행 중
    put("mine-f", "1.2", "failed", "me", 4.0)  # 자기 앱 실패 1회
    with open_auto(tmp_path, kit, SPEC_SCOPE, runs=fake) as env:
        state = env.state()
        assert state["failures"] == {"1.2": 1}  # 다른 앱의 실패는 세지 않는다
        assert state["skipped_keys"] == []
        # 다른 앱의 실행 중 Run은 진행 중으로 세지 않는다 → 두 작업 모두 시작
        assert sorted(env.started_keys()) == ["1.1", "1.2"]
        assert "other-run" not in state["active_runs"]


def test_restart_continues_from_run_records(tmp_path: Path, kit: Any) -> None:
    fake = FakeRuns(graphs={SPACE: {"team-x", "qa"}}, host="me")
    with open_auto(tmp_path, kit, SPEC_SCOPE, runs=fake) as env:
        env.view()
        env.finish("1.1", "failed")  # 1.1 실패 1회 → 다시 시작
        assert sorted(env.started_keys()) == ["1.1", "1.1", "1.2"]
        env.finish("1.2")  # 1.2 끝
        store = env.store
        # 앱이 꺼짐(1.1 실행은 기록에 running으로 남음)
    left = env.running()
    assert list(left) == ["1.1"]
    before = len(fake.started)
    with open_auto(tmp_path, kit, SPEC_SCOPE, runs=fake, store=store, create=False) as env2:
        state = env2.state()
        assert state["enabled"] is True
        assert state["running"] is True
        assert state["failures"] == {"1.1": 1}  # 기록에서 되살림
        # 끊긴 1.1(이 프로세스가 따라가지 않음)을 다시 시작, 1.2는 끝나서 2.x는 1.1을 기다림
        assert [c["labels"]["sdd.task"] for c in fake.started[before:]] == ["1.1"]
        fake.finish(left["1.1"], "interrupted")  # 이전 Run 정리(재시작 복구)
        env2.automation.join()
        env2.finish("1.1")
        env2.finish("2.2")
        env2.finish("2.1")
        assert env2.state()["stopped_reason"] == "spec_done"


async def test_automation_without_server_and_changed_notices() -> None:
    """서버·mod-sdd 없이: 메모리 스펙 + 가짜 실행 + ``SpecAutomation``. 상태가 바뀔 때마다
    ``notify(automation=True)``, 꺼진 규칙은 아무것도 시작하지 않는다."""
    from agent_console_link_runs_sdd import StatusReflector, package_defaults
    from agent_console_link_runs_sdd.testing import LocalSddService
    from agent_console_sdd.testing import TEST_TEMPLATE_KIND

    class Recording(LocalSddService):
        def notify(self, space: str | None, spec_id: str, **kwargs: Any) -> None:
            super().notify(space, spec_id)
            if kwargs.get("automation"):
                changes.append(spec_id)

    changes: list[str] = []
    sdd = Recording()
    repo = sdd.repository
    rules: dict[str, Any] = {
        "run_profiles": [
            {"id": "go", "title": "실행", "graph": "g", "status_on": {"succeeded": "done"}}
        ],
        "automation": {"enabled": True, "max_parallel": 1, "scope": "spec"},  # profile 생략
    }
    for tid, enabled in (("on", True), ("off", False)):
        doc_rules = copy.deepcopy(rules)
        doc_rules["automation"]["enabled"] = enabled
        template = {
            "kind": TEST_TEMPLATE_KIND,
            "id": tid,
            "name": tid,
            "documents": [{"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]}],
            "rules": doc_rules,
        }
        created = repo.store.create(TEST_TEMPLATE_KIND, template)
        repo.store.write_files(
            TEST_TEMPLATE_KIND,
            tid,
            {"tasks.md": b"- [ ] 1 a\n- [ ] 2 b [depends: 1]\n"},
            expected_version=created.version_hash,
        )
    on = repo.create(name="on", template="on").id
    off = repo.create(name="off", template="off").id
    d = package_defaults()
    runs = FakeRuns(graphs={None: {"g"}})
    reflector = StatusReflector(
        sdd,
        run_outcomes=d["run_outcomes"],
        status_events=d["status_events"],
        finished_statuses=d["finished_statuses"],
        max_issues=10,
    )
    runs.emit = reflector.on_event
    integration = RunsTaskIntegration(sdd=sdd, starter=runs, reader=runs, reflector=reflector)
    automation = SpecAutomation(
        sdd=sdd,
        integration=integration,
        reflector=reflector,
        finished_statuses=d["finished_statuses"],
        failure_outcomes=d["automation_failure_outcomes"],
        retry_outcomes=d["automation_retry_outcomes"],
    )
    integration.automation = automation

    await automation.tick(None, off)
    assert runs.started == []  # 꺼진 규칙
    assert automation.state(None, off).running is False

    await automation.tick(None, on)
    assert [c["labels"]["sdd.task"] for c in runs.started] == ["1"]
    assert changes == [on]
    runs.finish("run-1", "completed")  # 처리기 → 지금 도는 루프에 차례를 맡김
    await automation.idle()
    assert [c["labels"]["sdd.task"] for c in runs.started] == ["1", "2"]
    runs.finish("run-2", "completed")
    await automation.idle()
    state = automation.state(None, on)
    assert state.stopped_reason == "spec_done"
    assert repo.read_document(on, "tasks").text == "- [x] 1 a\n- [x] 2 b [depends: 1]\n"
    assert len(changes) >= 3
    ctx = sdd.context(sdd.scope(None), repo.load(on))
    assert await integration.control(ctx, "unknown") is None
    stopped = await integration.control(ctx, "stop")
    assert stopped is not None
    assert stopped.stopped_reason == "user"
    automation.close()


def test_automation_skipped_code_is_contract_constant() -> None:
    """건너뜀 이슈 코드는 계약 문서 상수다(계약 0.13.1 후속)."""
    from agent_console_contracts.constants import KnownIssueCodes

    assert AUTOMATION_SKIPPED == KnownIssueCodes.SDD_AUTOMATION_SKIPPED == "sdd.automation_skipped"
