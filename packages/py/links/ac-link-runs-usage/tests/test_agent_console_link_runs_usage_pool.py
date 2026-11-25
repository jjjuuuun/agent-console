"""사용량 집계가 기록 공간 풀을 흔들지 않는다(실제 ``link-projects-records`` 풀).

프로젝트가 풀 상한(``max_open_spaces``)보다 많을 때, 집계 한 번이 연결을 쫓아내고 다시 여는 일이
없어야 한다. "열기"는 기록 DB가 파일을 처음부터 살펴 엔진을 만드는 횟수다(``RecordsDb.refresh`` —
처음 열기와 밀려난 뒤 다시 살리기 모두, 그때마다 주입한 ``network_fs``를 한 번 부른다).

- 집계는 ``RecordsStores.batch()`` 안에서 돈다: 그 안에서 연 공간은 끝날 때까지 상한으로 밀어내지
  않고, 끝날 때 상한을 맞춘다. 그래서 집계 한 번의 열기 수 ≤ 프로젝트 수다.
- 연속 두 번째 집계는 풀에 남은(상한 안) 공간을 다시 열지 않는다. 상한 밖 공간(프로젝트 수 - 상한)은
  설계상 다시 연다(상한 = 동시에 열어 둘 DB 개수, 사용자가 정한 값). 상한을 프로젝트 수 이상으로
  올리면 0이다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from agent_console_contracts import NodeRun, Run, RunEvent, Usage
from agent_console_link_projects_records import PoolOptions, RecordsSpacePool, RecordsSpool
from agent_console_link_projects_records.testing import FolderSpaces
from agent_console_link_runs_usage import (
    IncrementalTokenRollups,
    MergedEventQuery,
    project_event_sources,
    project_rollup_sources,
)
from agent_console_mod_runs.storage import BRANCH
from agent_console_store import InMemoryStorage, RecordsStores, SqliteStorage

PROJECTS = 12


@dataclass
class _Project:
    id: str
    archived: bool = False


class _Lookup:
    def __init__(self, ids: list[str]) -> None:
        self.projects = [_Project(i) for i in ids]

    def list_projects(self) -> list[_Project]:
        return list(self.projects)


def _save(storage: Any, run_id: str, *, at: float, tokens: int, graph: str) -> None:
    storage.runs.save(
        Run(
            id=run_id,
            graph_id=graph,
            graph_version="v",
            status="completed",
            input={},
            origin="api",
            created_at=at,
        )
    )
    storage.runs.save_node_run(
        NodeRun(
            run_id=run_id,
            node_id="a",
            status="succeeded",
            started_at=at,
            usage=Usage(input_tokens=tokens, output_tokens=0),
        )
    )
    storage.events.append_many(
        [
            RunEvent(
                event_id=f"{run_id}-1",
                run_id=run_id,
                seq=1,
                ts=at,
                node_path=["a"],
                actor="agent-x",
                type="agent.session_started",
                payload={"model": "m"},
            )
        ]
    )


class _Setup:
    def __init__(self, tmp_path: Path, *, max_open: int) -> None:
        self.ids = [f"p{i:02d}" for i in range(PROJECTS)]
        folders = {pid: tmp_path / pid for pid in self.ids}
        for folder in folders.values():
            folder.mkdir()
        self.opens: Counter[str] = Counter()

        def network_fs(path: Path) -> bool:
            self.opens[path.parent.parent.name] += 1  # <폴더>/.agent-console/records.sqlite3
            return False

        self.pool = RecordsSpacePool(
            lambda: FolderSpaces(folders),
            lambda: [BRANCH],
            host_id="host-aaaa1111",
            spool=RecordsSpool(tmp_path / "spool"),
            options=PoolOptions(max_open=max_open),
            network_fs=network_fs,
        )
        self.stores = RecordsStores(lambda: self.pool, SqliteStorage)
        for n, pid in enumerate(self.ids):
            _save(self.stores.writer(pid), f"{pid}-r", at=float(n + 1), tokens=n + 1, graph=pid)
        self.lookup = _Lookup(self.ids)
        app = InMemoryStorage()
        self.rollups = IncrementalTokenRollups(
            app.runs,
            app.events,
            extra=project_rollup_sources(lambda: self.lookup, self.stores),
            batch=self.stores.batch,
        )
        self.query = MergedEventQuery(
            app.events,
            project_event_sources(lambda: self.lookup, self.stores),
            batch=self.stores.batch,
        )

    def aggregate(self) -> tuple[dict[str, int], Counter[str]]:
        before = Counter(self.opens)
        rows = self.rollups.rollups(limit=100, tz=UTC)
        tokens: dict[str, int] = {}
        for row in rows:
            graph = str(row.graph_id)
            tokens[graph] = tokens.get(graph, 0) + int(row.usage.input_tokens or 0)
        return tokens, self.opens - before


def test_one_rollup_opens_each_project_at_most_once(tmp_path: Path) -> None:
    setup = _Setup(tmp_path, max_open=8)
    setup.pool.close_all()  # 쓰기로 연 것을 닫고 빈 풀에서 시작한다
    tokens, opened = setup.aggregate()
    assert tokens == {pid: n + 1 for n, pid in enumerate(setup.ids)}
    assert sum(opened.values()) <= PROJECTS
    assert max(opened.values()) == 1
    assert len(setup.pool.open_spaces()) == 8  # 끝나면 상한을 맞춘다

    # 연속 두 번째 집계: 상한 안에 남은 8개는 다시 열지 않는다(상한 밖 4개만 다시 연다)
    kept = set(setup.pool.open_spaces())
    again, reopened = setup.aggregate()
    assert again == tokens
    assert sum(reopened.values()) == PROJECTS - 8
    assert max(reopened.values()) == 1
    assert not {f"project:{pid}" for pid in reopened} & kept  # 남아 있던 8개는 다시 열지 않는다
    assert len(setup.pool.open_spaces()) == 8
    setup.pool.shutdown()


def test_second_rollup_reopens_nothing_when_cap_fits(tmp_path: Path) -> None:
    setup = _Setup(tmp_path, max_open=PROJECTS)
    setup.pool.close_all()
    setup.aggregate()
    _, reopened = setup.aggregate()
    assert sum(reopened.values()) == 0
    setup.pool.shutdown()


def test_merged_event_query_does_not_churn_pool(tmp_path: Path) -> None:
    setup = _Setup(tmp_path, max_open=8)
    setup.pool.close_all()
    before = Counter(setup.opens)
    setup.query.latest_by_type("usage.rate_limit", limit=1)
    opened = setup.opens - before
    assert sum(opened.values()) <= PROJECTS
    assert max(opened.values()) == 1
    assert len(setup.pool.open_spaces()) == 8
    setup.pool.shutdown()
