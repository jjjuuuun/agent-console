"""link-runs-usage: 토큰 집계 증분 캐시(design §3R.5 수용 기준 2개)·포트·토픽 구독.

수용 기준:
1. 실행 0개와 500개(픽스처)에서 ``parts=windows`` 중앙 응답 시간 차이가 20% 이내다.
2. 전체 응답의 두 번째 호출은 증분만 계산한다(호출 횟수로 단언, 시간 단언 아님).
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import NodeRun, Run, RunEvent, Usage
from agent_console_link_runs_usage import (
    USAGE_EVENT_QUERY,
    USAGE_TOKEN_ROLLUPS,
    IncrementalTokenRollups,
    module,
)
from agent_console_link_runs_usage.testing import local_runs_module
from agent_console_mod_usage import TokenRollups
from agent_console_mod_usage import module as usage
from agent_console_modkit import BaseServices, Topic, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_registry import Registry
from agent_console_store import SqliteDatabase, SqliteStorage
from agent_console_usage import (
    USAGE_SOURCES_EXTENSION,
    RunEventUsageSource,
    UsageEventQuery,
    as_usage_source,
    load_usage_records,
    token_rollup,
)

API = "/api/v1"
TOKEN = "t" * 32


def _seed(storage: Any, count: int, *, start: int = 0, rate_limit: bool = True) -> None:
    """완료된 Run ``count``개(NodeRun 사용량 + 세션 시작 이벤트, ``rate_limit``이면 창 이벤트도)."""
    for i in range(start, start + count):
        run_id = f"r{i:04d}"
        storage.runs.save(
            Run(
                id=run_id,
                graph_id="g",
                graph_version="v",
                status="completed",
                input={},
                origin="api",
                created_at=float(i + 1),
            )
        )
        storage.runs.save_node_run(
            NodeRun(
                run_id=run_id,
                node_id="a",
                status="succeeded",
                started_at=float(i + 1),
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        )
        session = [
            RunEvent(
                event_id=f"{run_id}-1",
                run_id=run_id,
                seq=1,
                ts=float(i + 1),
                node_path=["a"],
                attempt=1,
                actor="agent-x",
                type="agent.session_started",
                payload={"model": "m"},
            )
        ]
        window = [
            RunEvent(
                event_id=f"{run_id}-2",
                run_id=run_id,
                seq=2,
                ts=float(i + 1),
                node_path=[],
                type="usage.rate_limit",
                payload={"window": "five_hour", "status": "allowed", "utilization": 0.5},
            )
        ]
        storage.events.append_many(session + (window if rate_limit else []))


class _Counting:
    """리포지토리 호출 횟수를 센다(메서드 이름 → 횟수)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: dict[str, int] = {}

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] = self.calls.get(name, 0) + 1
            return target(*args, **kwargs)

        return counted


def test_second_call_computes_only_increments(tmp_path: Path) -> None:
    """수용 기준 2: 두 번째 호출은 바뀐 Run만(없으면 아무것도) 다시 읽는다."""
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    _seed(storage, 20)
    runs, events = _Counting(storage.runs), _Counting(storage.events)
    rollups = IncrementalTokenRollups(runs, events)
    first = rollups.rollups(limit=50, tz=UTC)
    expected = token_rollup(load_usage_records(storage.runs, storage.events, limit=50), tz=UTC)
    assert first == expected
    assert runs.calls == {"list": 1, "list_node_runs": 20}
    assert events.calls == {"list": 40}  # Run마다 재료 형식 2개

    runs.calls.clear()
    events.calls.clear()
    assert rollups.rollups(limit=50, tz=UTC) == first
    assert runs.calls == {"list": 1}  # Run 목록만, NodeRun·이벤트는 다시 읽지 않는다
    assert events.calls == {}

    # 이벤트가 생긴 Run(토픽 구독 → mark)과 새 Run만 다시 읽는다
    _seed(storage, 1, start=20)
    rollups.mark(type("E", (), {"run_id": "r0003"})())
    runs.calls.clear()
    events.calls.clear()
    third = rollups.rollups(limit=50, tz=UTC)
    assert runs.calls == {"list": 1, "list_node_runs": 2}
    assert events.calls == {"list": 4}
    assert sum(row.runs or 0 for row in third) == 21

    rollups.invalidate()
    runs.calls.clear()
    rollups.rollups(limit=50, tz=UTC)
    assert runs.calls["list_node_runs"] == 21
    db.close()


def test_unfinished_runs_read_only_new_events(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    _seed(storage, 1)
    run = storage.runs.get("r0000")
    assert run is not None
    storage.runs.save(run.model_copy(update={"status": "running"}))
    events = _Counting(storage.events)
    rollups = IncrementalTokenRollups(storage.runs, events)
    rollups.rollups(limit=5, tz=UTC)
    events.calls.clear()
    seen: list[int] = []
    original = storage.events.list

    def spy(run_id: str, **kwargs: Any) -> Any:
        seen.append(kwargs.get("since_seq", 0))
        return original(run_id, **kwargs)

    events._inner = type("Spy", (), {"list": staticmethod(spy)})()
    rollups.rollups(limit=5, tz=UTC)
    assert seen == [1, 0]  # session_started는 seq 1까지 반영, subagent_stopped는 아직 없음
    db.close()


def test_limit_counts_only_root_runs_so_children_do_not_distort_it(tmp_path: Path) -> None:
    """5.2R.32: 자식 Run이 많아도 ``limit``은 루트 Run 수로 센다(목록 limit 왜곡 해소)."""
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    _seed(storage, 3)  # 루트 r0000~r0002 (created_at 1~3)
    for i in range(10):  # 가장 최근에 몰린 자식 Run 10개
        storage.runs.save(
            Run(
                id=f"c{i}",
                graph_id="g",
                graph_version="v",
                status="completed",
                input={},
                origin="api",
                created_at=100.0 + i,
                parent_run_id="r0002",
                root_run_id="r0002",
            )
        )
    rollups = IncrementalTokenRollups(storage.runs, storage.events)
    rows = rollups.rollups(limit=3, tz=UTC)
    assert sum(r.runs or 0 for r in rows) == 3  # 예전에는 자식 3개가 limit을 먹어 0이었다
    assert rows == token_rollup(load_usage_records(storage.runs, storage.events, limit=3), tz=UTC)
    db.close()


def _registries() -> Any:
    class _Registries:
        def __init__(self) -> None:
            self.extensions: dict[str, Registry[Any]] = {}

        def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
            if name not in self.extensions:
                self.extensions[name] = Registry(name, validator=validator)
            return self.extensions[name]

    regs = _Registries()
    sources = regs.extension(USAGE_SOURCES_EXTENSION, validator=as_usage_source)
    sources.register("run-events", RunEventUsageSource())
    return regs


@contextmanager
def _client(storage: Any) -> Iterator[TestClient]:
    assembly = assemble(
        [usage, module, local_runs_module(storage=storage)],
        base=BaseServices(registries=_registries()),
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        yield client


def _median_ms(client: TestClient, rounds: int) -> list[float]:
    out: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter()
        response = client.get(f"{API}/usage", params={"parts": "windows"})
        out.append((time.perf_counter() - start) * 1000)
        assert response.status_code == 200
    return out


def test_windows_only_latency_does_not_depend_on_run_count(tmp_path: Path) -> None:
    """수용 기준 1: 실행 0개와 500개에서 ``parts=windows`` 중앙 응답 시간 차이가 20% 이내.

    창은 출처 수집뿐이라(여기서는 ``run-events`` 출처가 창 이벤트를 읽는다) 실행 수와 무관해야 한다.

    두 서버에 번갈아 요청해 시간 흐름에 따른 잡음을 같이 받게 하고, 잡음으로 한 번 넘칠 수 있어
    최대 3회까지 다시 잰다(어느 한 번이라도 20% 이내면 통과).
    """
    empty_db = SqliteDatabase.open(tmp_path / "empty.sqlite3")
    full_db = SqliteDatabase.open(tmp_path / "full.sqlite3")
    for db in (empty_db, full_db):
        db.upgrade()
    # 두 DB 모두 창 이벤트가 있는 Run 하나(같은 창 결과), 한쪽에만 실행 500개를 더한다
    empty = SqliteStorage(empty_db.engine)
    full = SqliteStorage(full_db.engine)
    _seed(empty, 1, start=9000)
    _seed(full, 1, start=9000)
    _seed(full, 500, rate_limit=False)
    ratios: list[float] = []
    with ExitStack() as stack:
        none = stack.enter_context(_client(empty))
        many = stack.enter_context(_client(full))
        body = many.get(f"{API}/usage", params={"parts": "windows"}).json()
        assert [w["window"] for w in body["windows"]] == ["five_hour"]  # 출처가 이벤트를 읽는다
        assert body["rollups"] is None
        for _ in range(3):
            _median_ms(none, 5)  # 데우기
            _median_ms(many, 5)
            a: list[float] = []
            b: list[float] = []
            for _ in range(30):
                a += _median_ms(none, 1)
                b += _median_ms(many, 1)
            m0, m500 = statistics.median(a), statistics.median(b)
            ratios.append(abs(m500 - m0) / m0)
            if ratios[-1] <= 0.2:
                break
    assert min(ratios) <= 0.2, ratios
    empty_db.close()
    full_db.close()


def test_module_ports_topic_and_consumer_protocols(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    _seed(storage, 3)
    runs = _Counting(storage.runs)
    counted = type("Storage", (), {"runs": runs, "events": storage.events})()
    assembly = assemble([usage, module, local_runs_module(storage=counted)])
    assert {r.state.value for r in assembly.report} == {"active"}
    rollups = assembly.port(USAGE_TOKEN_ROLLUPS)
    assert isinstance(rollups, IncrementalTokenRollups)
    assert isinstance(rollups, TokenRollups)  # mod-usage 소비 프로토콜
    as_rollups: TokenRollups = rollups
    assert sum(r.runs or 0 for r in as_rollups.rollups(limit=10, tz=UTC)) == 3
    query = assembly.port(USAGE_EVENT_QUERY)
    assert isinstance(query, UsageEventQuery)
    assert query.latest_by_type("usage.rate_limit", limit=1)
    # 토픽 runs.event(실행 모듈이 낸다) → 그 Run만 다시 읽는다
    runs.calls.clear()
    assembly.services.events.publish(Topic("runs.event"), type("E", (), {"run_id": "r0001"})())
    as_rollups.rollups(limit=10, tz=UTC)
    assert runs.calls == {"list": 1, "list_node_runs": 1}
    db.close()


def test_child_runs_are_counted_only_through_root(tmp_path: Path) -> None:
    """중첩 팀의 자식 Run은 따로 세지 않는다 — 부모 노드 usage(= 자식 totals)로 한 번만(5R.13)."""
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    _seed(storage, 1)  # 루트 r0000: 노드 a usage 10/5(= 자식 totals라고 본다)
    before = IncrementalTokenRollups(storage.runs, storage.events).rollups(limit=50, tz=UTC)
    storage.runs.save(
        Run(
            id="child",
            graph_id="inner",
            graph_version="v",
            status="completed",
            input={},
            origin="api",
            parent_run_id="r0000",
            parent_node_id="a",
            root_run_id="r0000",
            created_at=2.0,
        )
    )
    storage.runs.save_node_run(
        NodeRun(
            run_id="child",
            node_id="inner-a",
            status="succeeded",
            started_at=2.0,
            usage=Usage(input_tokens=10, output_tokens=5),
        )
    )
    runs = _Counting(storage.runs)
    rows = IncrementalTokenRollups(runs, storage.events).rollups(limit=50, tz=UTC)
    assert rows == before  # 자식 Run을 더해도 집계가 같다
    assert runs.calls["list_node_runs"] == 1  # 자식 Run 기록은 읽지도 않는다
    db.close()
