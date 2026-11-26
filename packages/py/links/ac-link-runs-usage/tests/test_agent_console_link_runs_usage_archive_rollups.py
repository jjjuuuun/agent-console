"""사용량 집계의 보관 제외와 ``token_rollups`` 값 대조(단위 테스트, VB107).

설계 문장(design §요청 11/08 표): "계정 전체 = 앱 + 등록 프로젝트 기록 DB(보관 제외),
``GET /usage?project=``면 그 프로젝트 기록 + 앱 DB의 같은 ``project_id`` Run".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from agent_console_contracts import NodeRun, Run, RunEvent, Usage
from agent_console_link_runs_usage import IncrementalTokenRollups, project_rollup_sources
from agent_console_store import (
    InMemoryStorage,
    RecordsDb,
    RecordsSpaces,
    RecordsStores,
    SqliteStorage,
    open_records_db,
)
from agent_console_usage import token_rollup, usage_records

DAY = 86400.0


@dataclass
class _Project:
    id: str
    archived: bool = False


class _Lookup:
    def __init__(self, projects: list[_Project]) -> None:
        self.projects = projects

    def list_projects(self) -> list[_Project]:
        return list(self.projects)


class _Spaces:
    def __init__(self, dbs: dict[str, RecordsDb]) -> None:
        self.dbs = dbs

    def open(self, space: str) -> RecordsDb:
        if space not in self.dbs:
            raise LookupError(space)
        return self.dbs[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass


def _save(
    storage: Any, run_id: str, *, graph: str, at: float, inp: int, out: int = 0, **extra: Any
) -> None:
    storage.runs.save(
        Run(
            id=run_id,
            graph_id=graph,
            graph_version="v",
            status="completed",
            input={},
            origin="api",
            created_at=at,
            **extra,
        )
    )
    storage.runs.save_node_run(
        NodeRun(
            run_id=run_id,
            node_id="a",
            status="succeeded",
            started_at=at,
            usage=Usage(input_tokens=inp, output_tokens=out),
        )
    )
    storage.events.append_many(
        [
            RunEvent(
                event_id=f"{run_id}-s",
                run_id=run_id,
                seq=1,
                ts=at,
                node_path=["a"],
                attempt=1,
                actor="agent-x",
                type="agent.session_started",
                payload={"model": "m"},
            )
        ]
    )


def _project_db(tmp_path: Path, name: str) -> RecordsDb:
    return open_records_db(tmp_path / name / "records.sqlite3", backup_dir=tmp_path / name / "bk")


def _graph_tokens(rows: list[Any]) -> dict[str, int]:
    found: dict[str, int] = {}
    for row in rows:
        found[row.graph_id] = found.get(row.graph_id, 0) + int(row.usage.input_tokens or 0)
    return found


def test_archived_project_is_left_out_of_account_totals_but_readable_by_choice(
    tmp_path: Path,
) -> None:
    """보관 프로젝트는 계정 전체에서 빠지고, 직접 고르면 읽힌다. 보관을 풀면 들어온다."""
    host = InMemoryStorage()
    _save(host, "h", graph="app", at=1.0, inp=1)
    dbs = {
        "project:live": _project_db(tmp_path, "live"),
        "project:old": _project_db(tmp_path, "old"),
    }
    _save(SqliteStorage(dbs["project:live"].writable_engine()), "l", graph="live", at=2.0, inp=10)
    _save(SqliteStorage(dbs["project:old"].writable_engine()), "o", graph="old", at=3.0, inp=100)
    lookup = _Lookup([_Project("live"), _Project("old", archived=True)])
    stores = RecordsStores(lambda: cast(RecordsSpaces, _Spaces(dbs)), SqliteStorage)
    rollups = IncrementalTokenRollups(
        host.runs, host.events, extra=project_rollup_sources(lambda: lookup, stores)
    )

    def total(project_id: str | None = None) -> dict[str, int]:
        return _graph_tokens(rollups.rollups(limit=50, tz=UTC, project_id=project_id))

    assert total() == {"app": 1, "live": 10}  # 보관한 old의 100은 없다
    assert total("old") == {"old": 100}  # 직접 고르면 보관이어도 읽는다(설계 문장)
    assert total() == {"app": 1, "live": 10}  # 직접 고른 뒤에도 계정 전체는 그대로(캐시 누수 없음)
    lookup.projects[1] = _Project("old")  # 보관 해제
    assert total() == {"app": 1, "live": 10, "old": 100}
    lookup.projects[0] = _Project("live", archived=True)  # 다시 보관: 다음 집계부터 빠진다
    assert total() == {"app": 1, "old": 100}
    for db in dbs.values():
        db.close()


def test_token_rollups_match_the_run_rows(tmp_path: Path) -> None:
    """집계 값 = 기록 행 합: 차원별 합·Run 수·증분 갱신·다시 계산한 값과 같다."""
    host = InMemoryStorage()
    day1 = datetime(2026, 11, 1, 12, tzinfo=UTC).timestamp()
    day2 = day1 + DAY
    _save(host, "a1", graph="ga", at=day1, inp=10, out=1)
    _save(host, "a2", graph="ga", at=day1 + 60, inp=20, out=2)
    _save(host, "b1", graph="gb", at=day2, inp=40, out=4)
    rollups = IncrementalTokenRollups(host.runs, host.events)

    rows = rollups.rollups(limit=50, tz=UTC)
    by_graph_day = {(r.graph_id, r.day): r for r in rows}
    assert by_graph_day[("ga", "2026-11-01")].usage.input_tokens == 30
    assert by_graph_day[("ga", "2026-11-01")].usage.output_tokens == 3
    assert by_graph_day[("ga", "2026-11-01")].runs == 2
    assert by_graph_day[("gb", "2026-11-02")].usage.input_tokens == 40
    assert by_graph_day[("gb", "2026-11-02")].runs == 1
    assert sum(r.usage.input_tokens or 0 for r in rows) == 70

    # 같은 기록을 캐시 없이 직접 계산한 값과 같다
    direct = []
    for run in host.runs.list(root_only=True):
        direct.extend(
            usage_records(run, host.runs.list_node_runs(run.id), host.events.list(run.id))
        )
    assert rows == token_rollup(direct, tz=UTC)

    # 새 Run이 생기면(캐시가 있어도) 합계가 그만큼만 늘고, 다시 읽은 값과 같다
    _save(host, "a3", graph="ga", at=day2 + 60, inp=5, out=0)
    after = rollups.rollups(limit=50, tz=UTC)
    assert sum(r.usage.input_tokens or 0 for r in after) == 75
    rollups.invalidate()
    assert rollups.rollups(limit=50, tz=UTC) == after
