"""6R.12(M-15): ``run-tree`` 자손 = 저장소 ``descendants`` 질의 한 번, 자손 1,000개 측정."""

from __future__ import annotations

import builtins
import time
from pathlib import Path
from typing import Any

from agent_console_contracts import Run
from agent_console_link_logs_runs import run_tree_ids
from agent_console_link_logs_runs.testing import MemoryRunRecords, run_record
from agent_console_store import open_sqlite


class Counting:
    """``list``·``descendants`` 호출 수를 센다."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.lists = 0
        self.descendant_calls = 0

    def get(self, run_id: str) -> Run | None:
        found: Run | None = self.inner.get(run_id)
        return found

    def list(self, **kw: Any) -> list[Run]:
        self.lists += 1
        found: list[Run] = self.inner.list(**kw)
        return found

    def descendants(self, root_run_id: str) -> builtins.list[Run]:
        self.descendant_calls += 1
        found: builtins.list[Run] = self.inner.descendants(root_run_id)
        return found

    def list_node_runs(self, run_id: str) -> builtins.list[Any]:
        return []


def _child(run_id: str, parent: str, root: str, at: float) -> Run:
    return run_record(run_id, created_at=at, parent_run_id=parent).model_copy(
        update={"root_run_id": root}
    )


def test_thousand_descendants_one_query_and_same_set_as_walk(tmp_path: Path) -> None:
    storage = open_sqlite(tmp_path / "db" / "c.sqlite3")
    storage.runs.save(run_record("root"))
    parents = ["root"]
    for i in range(1000):  # 넓고 깊은 나무: 부모 = 앞서 만든 Run 중 하나
        parent = parents[i // 4]
        storage.runs.save(_child(f"c{i:04d}", parent, "root", 2.0 + i))
        parents.append(f"c{i:04d}")
    counting = Counting(storage.runs)
    started = time.perf_counter()
    fast = run_tree_ids(counting, "root")
    fast_s = time.perf_counter() - started
    assert (counting.descendant_calls, counting.lists) == (1, 0)
    assert len(fast) == 1001
    assert fast[0] == "root"

    class WalkOnly:  # descendants 없는 읽기 = 예전 넓이 우선
        get = storage.runs.get
        list = storage.runs.list

    started = time.perf_counter()
    walk = run_tree_ids(WalkOnly(), "root")  # type: ignore[arg-type]
    walk_s = time.perf_counter() - started
    assert set(walk) == set(fast)
    print(f"run-tree 1000: descendants {fast_s * 1000:.1f}ms, walk {walk_s * 1000:.1f}ms")
    assert fast_s < 1.0


def test_middle_run_and_unstamped_records_fall_back_to_walk(tmp_path: Path) -> None:
    storage = open_sqlite(tmp_path / "db" / "c.sqlite3")
    storage.runs.save(run_record("root"))
    storage.runs.save(_child("c1", "root", "root", 2.0))
    storage.runs.save(_child("g1", "c1", "root", 3.0))
    counting = Counting(storage.runs)
    assert run_tree_ids(counting, "c1") == ["c1", "g1"]  # 중간 Run은 직접 자식을 따라간다
    assert counting.descendant_calls == 0
    records = MemoryRunRecords()  # root_run_id를 적지 않은 기록: 자손 질의가 비면 따라간다
    records.runs.save(run_record("a"))
    records.runs.save(run_record("b", parent_run_id="a", created_at=2.0))
    assert run_tree_ids(records.runs, "a") == ["a", "b"]
