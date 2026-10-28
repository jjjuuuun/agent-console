"""프로젝트 넣기·개수(5.7R.33j): 순수 계획 함수와 Run 저장소 3종 + 큰 표 시간."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import AssignProjectRequest, Run
from agent_console_store import (
    AssignCandidate,
    InMemoryStorage,
    SqliteStorage,
    assign_project,
    count_projects,
    open_sqlite,
    plan_assignment,
)
from agent_console_store.schema import runs_project_active


def _run(id: str, root: str | None = None, project: str | None = None, t: float = 1.0) -> Run:
    return Run(
        id=id, graph_id="g", graph_version="h", status="completed", input={}, origin="api",
        created_at=t, root_run_id=root, project_id=project,
    )  # fmt: skip


@pytest.fixture(params=["memory", "sqlite-doc-only", "sqlite-columns", "sqlite-project"])
def runs(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    if request.param == "memory":
        impl: Any = InMemoryStorage()
    else:
        db = open_sqlite(tmp_path / "c.sqlite3")
        if request.param != "sqlite-doc-only":
            with db.engine.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN parent_node_id TEXT")
                conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN root_run_id TEXT")
                conn.exec_driver_sql("DROP TABLE node_runs")
                from agent_console_store.schema import node_runs_v2

                node_runs_v2.create(conn)
                if request.param == "sqlite-project":
                    conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN project_id TEXT")
        impl = SqliteStorage(db.engine)
        assert runs_project_active(db.engine) in (False, request.param == "sqlite-project")
    yield impl
    impl.close()


def _seed(r: Any) -> None:
    r.save(_run("a"))
    r.save(_run("a1", root="a"))
    r.save(_run("a2", root="a", project="x"))
    r.save(_run("b", project="x"))
    r.save(_run("b1", root="b", project="x"))
    r.save(_run("c", project="y"))


def test_counts_roots_only(runs: Any) -> None:
    _seed(runs.runs)
    c = count_projects(runs.runs)
    assert (c.total, c.no_project, c.by_project) == (3, 1, {"x": 1, "y": 1})


def test_from_null_takes_only_null_and_children_follow(runs: Any) -> None:
    _seed(runs.runs)
    res = assign_project(runs.runs, AssignProjectRequest(to="p", from_null=True))
    assert res.assigned == 2  # a, a1 (a2는 다른 프로젝트라 그대로)
    got = {r.id: r.project_id for r in runs.runs.list()}
    assert got == {"a": "p", "a1": "p", "a2": "x", "b": "x", "b1": "x", "c": "y"}
    assert runs.runs.get("a").project_id == "p"
    assert count_projects(runs.runs).no_project == 0


def test_ids_move_even_if_other_project_with_all_children(runs: Any) -> None:
    _seed(runs.runs)
    res = assign_project(runs.runs, AssignProjectRequest(to="p", ids=["a", "c", "nope"]))
    assert res.assigned == 4  # a, a1, a2, c
    assert [(s.id, s.reason) for s in res.skipped] == [("nope", "not_found")]
    got = {r.id: r.project_id for r in runs.runs.list()}
    assert (got["a2"], got["c"], got["b"]) == ("p", "p", "x")
    again = assign_project(runs.runs, AssignProjectRequest(to="p", ids=["a"]))
    assert (again.assigned, again.skipped) == (0, [])


def test_running_tree_is_skipped_as_busy(runs: Any) -> None:
    _seed(runs.runs)
    runs.runs.save(_run("a3", root="a").model_copy(update={"status": "running"}))
    for req in (
        AssignProjectRequest(to="p", from_null=True),
        AssignProjectRequest(to="p", ids=["a"]),
    ):
        res = assign_project(runs.runs, req)
        assert res.assigned == 0
        assert [(s.id, s.reason) for s in res.skipped] == [("a", "busy")]
    assert runs.runs.get("a").project_id is None


def test_child_alone_moves_only_itself(runs: Any) -> None:
    _seed(runs.runs)
    assert assign_project(runs.runs, AssignProjectRequest(to="p", ids=["a1"])).assigned == 1


def test_plan_is_pure_and_skips_orphan_children() -> None:
    cands = [AssignCandidate("r", None), AssignCandidate("k", None, "root-elsewhere")]
    plan = plan_assignment(AssignProjectRequest(to="p", from_null=True), cands)
    assert plan.assign_ids == ["r"]
    assert [(s.id, s.reason) for s in plan.skipped] == [("k", "parent_elsewhere")]


def test_request_needs_exactly_one_selector() -> None:
    with pytest.raises(ValueError, match="하나만"):
        AssignProjectRequest(to="p")
    with pytest.raises(ValueError, match="하나만"):
        AssignProjectRequest(to="p", ids=["a"], from_null=True)


def test_large_table_timing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = open_sqlite(tmp_path / "big.sqlite3")
    try:
        with db.engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO runs "
                    "(id, graph_id, graph_version, status, origin, created_at, doc) "
                    "VALUES (:id, 'g', 'h', 'completed', 'api', :t, :doc)"
                ),
                [
                    {
                        "id": f"r{i}",
                        "t": float(i),
                        "doc": _run(f"r{i}", t=float(i)).model_dump_json(),
                    }
                    for i in range(10_000)
                ],
            )
        t0 = time.perf_counter()
        counts = count_projects(db.runs)
        t1 = time.perf_counter()
        res = assign_project(db.runs, AssignProjectRequest(to="p", from_null=True))
        t2 = time.perf_counter()
        assert (counts.no_project, res.assigned) == (10_000, 10_000)
        assert count_projects(db.runs).by_project == {"p": 10_000}
        print(f"10k rows: counts {t1 - t0:.3f}s, assign {t2 - t1:.3f}s")
        assert t2 - t1 < 30
    finally:
        db.close()
