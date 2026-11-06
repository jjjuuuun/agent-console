"""단위: 라벨 질의 모으기, 시작 예외 → 이슈, 반영기(먼저 온 이벤트·중복·끝남·알림), 설치자 옵션,
확장 지점 프로토콜."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import ErrorInfo, Issue, Run, RunEvent
from agent_console_link_runs_sdd import (
    RunsSddSettings,
    RunsTaskIntegration,
    RunsVerificationSource,
    StatusReflector,
    TrackedRun,
    labeled_runs,
    package_defaults,
    start_issue,
)
from agent_console_link_runs_sdd.testing import FakePreflightError, FakeRuns
from agent_console_sdd import AutomationControl, ProfileChecker, TaskIntegration, VerificationSource


def _run(run_id: str, project: str | None, at: float, **labels: str) -> Run:
    return Run(
        id=run_id,
        graph_id="g",
        graph_version="v",
        status="completed",
        input={},
        origin="sdd",
        project_id=project,
        created_at=at,
        labels=labels,
    )


class TwoSources:
    """공간 질의(project_id 있음) = 공간 DB, 없음 = 호스트 DB(모든 프로젝트)."""

    def __init__(self, space: list[Run], host: list[Run]) -> None:
        self.space, self.host = space, host
        self.calls: list[dict[str, Any]] = []

    def page(self, **filters: Any) -> tuple[list[Run], str | None]:
        self.calls.append(filters)
        rows = self.space if filters.get("project_id") else self.host
        labels = filters["labels"]
        hit = [r for r in rows if all(r.labels.get(k) == v for k, v in labels.items())]
        offset = int(filters.get("cursor") or 0)
        limit = filters["limit"]
        chunk = hit[offset : offset + limit]
        return chunk, (str(offset + limit) if offset + limit < len(hit) else None)

    def get(self, run_id: str) -> Run | None:
        return None


def test_labeled_runs_pages_and_adds_old_app_records() -> None:
    space = [_run(f"s{i}", "p1", 100 - i, spec="a") for i in range(5)]
    host = [
        _run("old", "p1", 10, spec="a"),  # 앱 DB 옛 기록
        _run("s0", "p1", 100, spec="a"),  # 같은 id는 한 번만
        _run("other", "p2", 50, spec="a"),  # 다른 프로젝트
        _run("bare", None, 60, spec="a"),  # 프로젝트 없음
    ]
    reader = TwoSources(space, host)
    found = labeled_runs(reader, project_id="p1", labels={"spec": "a"}, limit=100, page_size=2)
    assert [r.id for r in found] == ["s0", "s1", "s2", "s3", "s4", "old"]
    assert all(c["root_only"] is True for c in reader.calls)
    # 공간 없는 스펙은 프로젝트 없는 Run만
    bare = labeled_runs(reader, project_id=None, labels={"spec": "a"}, limit=100, page_size=10)
    assert [r.id for r in bare] == ["bare"]
    # 상한
    capped = labeled_runs(reader, project_id="p1", labels={"spec": "a"}, limit=3, page_size=2)
    assert [r.id for r in capped] == ["s0", "s1", "s2"]


def test_start_issue_maps_error_shapes() -> None:
    preflight = FakePreflightError(
        ErrorInfo(code="project.folder_missing", message="폴더 없음", details={"project_id": "p"})
    )
    assert start_issue(preflight).code == "project.folder_missing"
    assert start_issue(preflight).details == {"project_id": "p"}

    class CodedError(Exception):
        code = "not_found"

    assert start_issue(CodedError("없음")).code == "not_found"

    class InvalidError(Exception):
        def __init__(self) -> None:
            super().__init__("x")
            self.issues = [Issue(severity="error", code="graph.bad", message="m")]

    invalid = start_issue(InvalidError())
    assert invalid.code == "validation_failed"
    assert invalid.details["issues"][0]["code"] == "graph.bad"
    secret = start_issue(RuntimeError("sk-ant-secret"))
    assert secret.code == "internal"
    assert "sk-ant" not in secret.message


class NoSdd:
    """반영기가 스펙 서비스를 부르면 실패(이 시험에서는 프로필을 못 찾게)."""

    def __init__(self) -> None:
        self.notified: list[str] = []

    def scope(self, space: str | None) -> Any:
        raise LookupError(space)

    def notify(self, space: str | None, spec_id: str, **kwargs: Any) -> None:
        self.notified.append(spec_id)


def _event(
    run_id: str, seq: int, type: str, status: str, node: list[str] | None = None
) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=float(seq),
        node_path=node or [],
        type=type,
        payload={"status": status},
    )


def _reflector(sdd: Any) -> StatusReflector:
    d = package_defaults()
    return StatusReflector(
        sdd,
        run_outcomes=d["run_outcomes"],
        status_events=d["status_events"],
        finished_statuses=d["finished_statuses"],
        max_issues=2,
    )


def test_reflector_buffers_early_events_dedupes_and_notifies_listeners() -> None:
    sdd = NoSdd()
    reflector = _reflector(sdd)
    seen: list[tuple[str, str, bool]] = []
    remove = reflector.add_listener(
        lambda run, outcome, done: seen.append((run.run_id, outcome, done))
    )
    # 시작 요청 밖에서 온 모르는 Run 이벤트는 버린다
    reflector.on_event(_event("x", 1, "run.started", "running"))
    reflector.begin_start()
    reflector.on_event(_event("r1", 1, "run.started", "running"))
    reflector.on_event(_event("r1", 2, "node.started", "running"))  # 반영 이벤트가 아님
    reflector.on_event(_event("r1", 3, "run.started", "running", node=["n"]))  # 노드 수준
    tracked = TrackedRun(
        run_id="r1", space=None, spec_id="s", task_key="1", profile_id="p", line_hash="h"
    )
    reflector.track(tracked)
    reflector.end_start()
    assert seen == [("r1", "started", False)]
    reflector.on_event(_event("r1", 4, "run.started", "running"))  # 같은 결과는 한 번
    reflector.on_event(_event("r1", 5, "run.completed", "completed"))
    assert seen[-1] == ("r1", "succeeded", True)
    assert reflector.active(None, "s") == []  # 끝나면 따라가지 않는다
    # 공간을 열 수 없으면 정보 이슈(reason=error) + 알림
    [issue] = reflector.issues(None, "s", ["1"])
    assert issue.code == "sdd.status_not_applied"
    assert issue.details["reason"] == "error"
    assert sdd.notified
    remove()
    assert reflector.outcome_of("waiting") == "waiting"


def test_reflector_issue_memory_is_bounded() -> None:
    reflector = _reflector(NoSdd())
    for i in range(3):
        run = TrackedRun(
            run_id=f"r{i}", space=None, spec_id="s", task_key=str(i), profile_id="p", line_hash="h"
        )
        reflector.track(run)
        reflector.apply(run, "completed")
    assert [i.task_key for i in reflector.issues(None, "s", ["0", "1", "2"])] == ["1", "2"]


def test_settings_defaults_come_from_package_data() -> None:
    d = package_defaults()
    s = RunsSddSettings()
    assert (s.integration_id, s.verification_source_id, s.origin) == (
        d["integration_id"],
        d["verification_source_id"],
        d["origin"],
    )
    assert s.run_outcomes == d["run_outcomes"]
    # 기본값 사본은 서로 독립(한쪽을 고쳐도 다른 쪽은 그대로)
    s.run_outcomes["x"] = "y"
    assert "x" not in RunsSddSettings().run_outcomes


def test_protocols() -> None:
    runs = FakeRuns()
    integration = RunsTaskIntegration(
        sdd=NoSdd(),  # type: ignore[arg-type]
        starter=runs,
        reader=runs,
        reflector=_reflector(NoSdd()),
    )
    assert isinstance(integration, TaskIntegration)
    assert isinstance(integration, ProfileChecker)
    assert not isinstance(integration, AutomationControl)  # 6R.16 몫
    assert integration.link_kinds == ("run",)
    assert isinstance(RunsVerificationSource(integration), VerificationSource)


def test_custom_options_rename_integration_and_skip_status_events(tmp_path: Path, kit: Any) -> None:
    options = {"integration_id": "team-runs", "status_events": [], "origin": "spec"}
    with kit.open_env(tmp_path, options=options) as env:
        env.approve()
        before = env.tasks_text()
        actions = env.client.get(env.q("/sdd/specs/s/tasks/1.1/actions")).json()
        assert {a["integration"] for a in actions} == {"team-runs"}
        r = env.client.post(env.q("/sdd/specs/s/tasks/1.1/actions/team-runs/impl"), json={})
        assert r.status_code == 200, r.text
        env.runs.finish(r.json()["run_id"], "completed")
        assert env.tasks_text() == before  # 반영 이벤트 없음 → 파일 그대로
        assert env.runs.started[0]["origin"] == "spec"
        assert [link["integration"] for link in env.task("1.1")["links"]] == ["team-runs"]


def test_concurrent_bulk_like_starts_each_track_their_run(tmp_path: Path, kit: Any) -> None:
    with kit.open_env(tmp_path) as env:
        env.approve()
        started = env.client.post(
            env.q("/sdd/specs/s/bulk-start"),
            json={"task_keys": ["1.1", "2.1"], "action": {"integration": "runs", "id": "impl"}},
        ).json()
        ids = [i["run_id"] for i in started["items"]]
        assert [i["status"] for i in started["items"]] == ["started", "started"]
        for run_id in ids:
            env.runs.finish(run_id, "completed")
        assert env.task("1.1")["status"] == "review"
        assert env.task("2.1")["status"] == "review"


async def test_integration_without_server_using_local_service() -> None:
    """서버·mod-sdd 없이: 메모리 스펙 + 가짜 실행으로 실행 → 결과 반영 → 연결."""
    from agent_console_link_runs_sdd.testing import LocalSddService
    from agent_console_sdd import find_task
    from agent_console_sdd.testing import TEST_TEMPLATE_KIND

    sdd = LocalSddService()
    repo = sdd.repository
    template = {
        "kind": TEST_TEMPLATE_KIND,
        "id": "t",
        "name": "틀",
        "documents": [{"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]}],
        "rules": {
            "run_profiles": [
                {"id": "go", "title": "실행", "graph": "g", "status_on": {"succeeded": "done"}}
            ]
        },
    }
    created = repo.store.create(TEST_TEMPLATE_KIND, template)
    repo.store.write_files(
        TEST_TEMPLATE_KIND, "t", {"tasks.md": b"- [ ] 1 a\n"}, expected_version=created.version_hash
    )
    spec_id = repo.create(name="spec", template="t").id
    runs = FakeRuns(graphs={None: {"g"}})
    reflector = _reflector(sdd)
    runs.emit = reflector.on_event
    integration = RunsTaskIntegration(sdd=sdd, starter=runs, reader=runs, reflector=reflector)
    ctx = sdd.context(sdd.scope(None), repo.load(spec_id))
    task = find_task(ctx.index, "1")
    assert task is not None
    result = await integration.invoke(ctx, task, "go", {})
    assert result.status == "started"
    runs.finish(result.run_id or "", "completed")
    loaded = repo.load(spec_id)
    assert repo.read_document(spec_id, "tasks").text == "- [x] 1 a\n"
    links = await integration.links(sdd.context(sdd.scope(None), loaded), loaded.index.tasks)
    assert [(link.ref, link.status) for link in links] == [(result.run_id, "completed")]
    assert sdd.notified == [(None, spec_id)]
