"""SQLite 메모리 저장소 규모 시험(design §5.7R.10).

기본 실행은 **작업량**(SQLite 가상 기계 명령 수·질의 계획)을 단언한다: 항목 수가 두 배가 되어도 같은
범위의 읽기·쓰기·목록·검색 비용이 늘지 않아야 한다. 벽시계는 `AGENT_CONSOLE_PERF=strict`일 때만
단언한다(항목 100,000개, 범위 200개, 평균 2 KiB, 한 범위 최대 5,000개). 만든 큰 DB를 다시 쓰려면
`AGENT_CONSOLE_SCALE_DB=<경로>`를 준다(없으면 만든다). 측정값은 `-s`로 본다.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_console_contracts.memory import MemoryScopeRef
from agent_console_memory import MemoryQuery
from agent_console_memory.sqlite import (
    SqliteMemoryStore,
    fts5_trigram_available,
    open_sqlite_memory_store,
)
from agent_console_memory.testing import (
    ScaleLayout,
    WorkCounter,
    build_scale_store,
    percentile,
    perf_strict,
    time_calls,
    user_author,
)

needs_fts = pytest.mark.skipif(not fts5_trigram_available(), reason="FTS5 trigram 없음")
SMALL = {"entries": 3_000, "scopes": 30, "heavy_entries": 600, "avg_bytes": 600}
DOUBLE = {"entries": 6_000, "scopes": 60, "heavy_entries": 600, "avg_bytes": 600}
GROWTH = 1.35  # 같은 범위 연산의 작업량 증가 허용(전체 항목 수가 2배일 때)


@pytest.fixture(scope="module")
def small(tmp_path_factory: pytest.TempPathFactory) -> tuple[SqliteMemoryStore, ScaleLayout]:
    return build_scale_store(tmp_path_factory.mktemp("scale") / "small.sqlite3", **SMALL)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def double(tmp_path_factory: pytest.TempPathFactory) -> tuple[SqliteMemoryStore, ScaleLayout]:
    return build_scale_store(tmp_path_factory.mktemp("scale") / "double.sqlite3", **DOUBLE)  # type: ignore[arg-type]


def _steps(store: SqliteMemoryStore, fn: Callable[[], object], repeat: int = 5) -> int:
    """`fn`을 `repeat`번 부른 작업량의 중앙값."""
    counter = WorkCounter(store)
    runs: list[int] = []
    for _ in range(repeat):
        with counter.measure():
            fn()
        runs.append(counter.steps)
    return int(statistics.median(runs))


def _operations(store: SqliteMemoryStore, layout: ScaleLayout) -> dict[str, Callable[[], object]]:
    heavy = layout.heavy_scope
    others = [s for s in layout.scopes[1:4]]
    key = layout.keys[(heavy.kind, heavy.id)][3]
    counter = {"n": 0}

    def update_existing() -> object:
        counter["n"] += 1
        return store.write(heavy, key, f"updated body {counter['n']} " * 30, author=user_author())

    def create_new() -> object:
        counter["n"] += 1
        return store.write(heavy, f"fresh/{counter['n']}", "new body " * 30, author=user_author())

    return {
        "find": lambda: store.find(heavy, key),
        "write_update": update_existing,
        "write_create": create_new,
        "list_first_page": lambda: store.search(MemoryQuery(scopes=[heavy], limit=50)),
        "search_rare_scoped": lambda: store.search(
            MemoryQuery(scopes=[heavy, *others], text=layout.unique_word_of(0), limit=20)
        ),
        "search_tag_scoped": lambda: store.search(
            MemoryQuery(scopes=[heavy], tags=[layout.common_tag], limit=20)
        ),
    }


@needs_fts
def test_same_scope_work_does_not_grow_with_total_entries(
    small: tuple[SqliteMemoryStore, ScaleLayout], double: tuple[SqliteMemoryStore, ScaleLayout]
) -> None:
    ops_small = _operations(*small)
    ops_double = _operations(*double)
    for name in ops_small:
        a = _steps(small[0], ops_small[name])
        b = _steps(double[0], ops_double[name])
        print(f"work {name}: {a} -> {b} (x{b / max(a, 1):.2f})")
        assert b <= max(a * GROWTH, a + 300), (
            f"{name}: 항목 수가 2배일 때 작업량이 늘었다 ({a} -> {b})"
        )


@needs_fts
def test_work_is_bounded_by_page_not_by_scope_size(
    double: tuple[SqliteMemoryStore, ScaleLayout],
) -> None:
    store, layout = double
    page = _steps(store, lambda: store.search(MemoryQuery(scopes=[layout.heavy_scope], limit=50)))
    find = _steps(store, lambda: store.find(layout.heavy_scope, layout.keys[("sk0", "s0000")][1]))
    assert find < 1_000  # 색인 한 번 찾기
    assert page < 60_000  # 쪽 크기 50 + 개수 세기(색인만)


def _plan(db: Path, sql: str, params: tuple[object, ...] = ()) -> str:
    with sqlite3.connect(db) as conn:
        return " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def test_query_plans_use_designed_indexes(small: tuple[SqliteMemoryStore, ScaleLayout]) -> None:
    db = Path(small[0].path)
    assert "ux_memory_entries_live_key" in _plan(
        db,
        "SELECT rid FROM memory_entries WHERE scope_kind=? AND scope_id=? AND key=? "
        "AND deleted_at IS NULL",
        ("sk0", "s0000", "k"),
    )
    listing = _plan(
        db,
        "SELECT rid FROM memory_entries WHERE deleted_at IS NULL AND archived = 0 "
        "AND scope_kind='sk0' AND scope_id='s0000' ORDER BY updated_at DESC, id ASC LIMIT 50",
    )
    assert "ix_memory_entries_live_summary" in listing
    assert "COVERING" in listing
    scopes = _plan(
        db,
        "SELECT scope_kind, scope_id, count(*), sum(archived), sum(bytes), max(updated_at) "
        "FROM memory_entries WHERE deleted_at IS NULL GROUP BY 1, 2 ORDER BY 1, 2",
    )
    assert "COVERING INDEX ix_memory_entries_live_summary" in scopes
    assert "ix_memory_entries_author_run" in _plan(
        db, "SELECT rid FROM memory_entries WHERE author_run_id = 'run-1'"
    )
    assert "ix_memory_tags_tag" in _plan(
        db, "SELECT entry_id FROM memory_tags WHERE tag = 'tag-a'"
    ) or "autoindex" in _plan(db, "SELECT entry_id FROM memory_tags WHERE tag = 'tag-a'")
    assert "ix_memory_versions_run" in _plan(
        db, "SELECT entry_id FROM memory_versions WHERE run_id = 'run-1'"
    )


def test_total_bytes_check_does_not_scan_entries(
    small: tuple[SqliteMemoryStore, ScaleLayout],
) -> None:
    store, layout = small
    store.write(layout.heavy_scope, "extra", "x" * 10, author=user_author())
    with sqlite3.connect(store.path) as conn:
        counted = conn.execute(
            "SELECT COALESCE(SUM(bytes), 0) FROM memory_entries WHERE deleted_at IS NULL"
        ).fetchone()[0]
        kept = conn.execute("SELECT value FROM memory_stats WHERE name = 'live_bytes'").fetchone()
    assert kept is not None
    assert kept[0] == counted  # 앞선 시험이 쓴 값까지 포함해 통계와 실제 합이 같다
    assert counted >= layout.total_bytes


def test_live_bytes_statistic_follows_every_write_path(tmp_path: Path) -> None:
    store = open_sqlite_memory_store(tmp_path / "m.sqlite3")
    scope = MemoryScopeRef(kind="k", id="")
    author = user_author()

    def live() -> tuple[int, int]:
        with sqlite3.connect(store.path) as conn:
            counted = conn.execute(
                "SELECT COALESCE(SUM(bytes), 0) FROM memory_entries WHERE deleted_at IS NULL"
            ).fetchone()[0]
            kept = conn.execute(
                "SELECT value FROM memory_stats WHERE name = 'live_bytes'"
            ).fetchone()
        return counted, (kept[0] if kept else 0)

    a = store.write(scope, "a", "12345", author=author).entry
    b = store.write(scope, "b", "123", author=author).entry
    assert live() == (8, 8)
    store.write(scope, "a", "12", author=author)
    assert live() == (5, 5)
    store.delete(a.id, author=author)
    assert live() == (3, 3)
    store.restore(a.id, author=author, version=1)
    assert live() == (8, 8)
    store.archive(b.id, author=author)
    store.move(b.id, author=author, to_key="c")
    assert live() == (8, 8)
    store.purge(b.id)
    assert live() == (5, 5)
    store.delete(a.id, author=author)
    store.purge(a.id)
    assert live() == (0, 0)
    store.close()


@needs_fts
def test_fts_and_like_agree_on_a_populated_store(
    small: tuple[SqliteMemoryStore, ScaleLayout],
) -> None:
    store, layout = small
    plain = open_sqlite_memory_store(store.path, use_fts=False)
    heavy = layout.heavy_scope
    queries = [
        MemoryQuery(text=layout.common_word, limit=500),
        MemoryQuery(text=layout.common_word.upper(), scopes=[heavy], limit=500),
        MemoryQuery(text=layout.unique_word_of(7)),
        MemoryQuery(text=layout.unique_prefix + "00001", limit=500),
        MemoryQuery(text="area3/item", limit=500),
        MemoryQuery(text="nothing-matches-this-xyz"),
        MemoryQuery(text=layout.common_tag, limit=500),
    ]
    for query in queries:
        fast = store.search(query)
        slow = plain.search(query)
        assert fast.total == slow.total
        assert [i.id for i in fast.items] == [i.id for i in slow.items]
    assert store.search(queries[2]).total == 1
    plain.close()


def test_count_tags_uses_the_tag_index_and_matches_scanning(
    small: tuple[SqliteMemoryStore, ScaleLayout],
) -> None:
    from agent_console_memory import TagCounter, iter_entries

    store, layout = small
    assert isinstance(store, TagCounter)
    for scopes in (None, [layout.heavy_scope], list(layout.scopes[1:4])):
        for include in (True, False):
            counts: dict[str, int] = {}
            for entry in iter_entries(store, scopes=scopes, include_archived=include):
                for tag in set(entry.tags):
                    counts[tag] = counts.get(tag, 0) + 1
            assert store.count_tags(scopes=scopes, include_archived=include) == counts
    plan = _plan(
        Path(store.path),
        "SELECT t.tag, count(*) FROM memory_tags t JOIN memory_entries e ON e.id = t.entry_id "
        "WHERE e.deleted_at IS NULL GROUP BY t.tag",
    )
    assert "ix_memory_tags_tag" in plan or "pk_memory_tags" in plan or "autoindex" in plan
    assert "ux_memory_entries_id" in plan  # 항목 행은 id 색인으로 맞춘다


# ---- 벽시계(AGENT_CONSOLE_PERF=strict) -------------------------------------------------------

strict_only = pytest.mark.skipif(not perf_strict(), reason="AGENT_CONSOLE_PERF=strict에서만")
FACTOR = float(os.environ.get("AGENT_CONSOLE_PERF_FACTOR", "1"))


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> tuple[SqliteMemoryStore, ScaleLayout]:
    """10만 개 저장소(모듈에서 한 번만 만든다, 약 3분 — FTS5 trigram 색인과 미리보기 비밀
    가림이 대부분). strict 시험들이 나눠 쓴다. 되풀이 측정은 `AGENT_CONSOLE_SCALE_DB`로
    파일을 다시 쓴다.
    """
    given = os.environ.get("AGENT_CONSOLE_SCALE_DB")
    path = Path(given) if given else tmp_path_factory.mktemp("big") / "big.sqlite3"
    kwargs = {"entries": 100_000, "scopes": 200, "avg_bytes": 2048, "heavy_entries": 5_000}
    if given and path.exists():
        # 같은 인자로 만든 파일을 다시 열고 모양만 다시 만든다(데이터는 건드리지 않는다).
        store = open_sqlite_memory_store(path)
        layout = _layout_of(store, kwargs)
        return store, layout
    return build_scale_store(path, **kwargs)  # type: ignore[arg-type]


def _layout_of(store: SqliteMemoryStore, kwargs: dict[str, int]) -> ScaleLayout:
    with sqlite3.connect(store.path) as conn:
        scopes = tuple(
            MemoryScopeRef(kind=k, id=s)
            for k, s in conn.execute(
                "SELECT scope_kind, scope_id FROM memory_entries "
                "WHERE key LIKE 'area%' GROUP BY 1, 2 ORDER BY COUNT(*) DESC, 2"
            )
        )
        keys = {
            (s.kind, s.id): [
                r[0]
                for r in conn.execute(
                    "SELECT key FROM memory_entries WHERE scope_kind=? AND scope_id=? "
                    "AND key LIKE 'area%' LIMIT 200",
                    (s.kind, s.id),
                )
            ]
            for s in scopes
        }
    return ScaleLayout(
        entries=kwargs["entries"],
        scopes=scopes,
        heavy_scope=scopes[0],
        heavy_count=kwargs["heavy_entries"],
        keys=keys,
        common_word="deploy",
        common_tag="tag-common",
        unique_prefix="uniq",
        total_bytes=0,
    )


# 정리 계획 strict 단언: 이 프로세스의 CPU 시간 최솟값(5.5R.36 선례, 부하에 덜 흔들림)
PLAN_RUNS = 3


def _timed_cpu[R](fn: Callable[[], R]) -> tuple[R, float, float]:
    """(결과, 벽시계 초, 이 프로세스의 CPU 초). CPU 시간은 다른 프로세스의 부하에 덜 흔들린다."""
    c0, t0 = time.process_time(), time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0, time.process_time() - c0


def _report(name: str, seconds: list[float], limit_ms: float | None = None) -> float:
    p50 = percentile(seconds, 0.5) * 1000
    p95 = percentile(seconds, 0.95) * 1000
    shown = f" (기준 {limit_ms:g} ms)" if limit_ms else ""
    print(f"PERF {name}: p50={p50:.2f} ms p95={p95:.2f} ms max={max(seconds) * 1000:.2f} ms{shown}")
    return p95


@strict_only
@needs_fts
def test_strict_read_write_p95_20ms(big: tuple[SqliteMemoryStore, ScaleLayout]) -> None:
    store, layout = big
    picks: list[tuple[MemoryScopeRef, str]] = []
    for scope in layout.scopes[:100]:
        picks.append((scope, layout.keys[(scope.kind, scope.id)][5]))
    read = time_calls(lambda i: store.find(*picks[i % len(picks)]), 300)
    assert _report("read(find)", read, 20) * 1 <= 20 * FACTOR
    entry_ids = [e.id for e in (store.find(*p) for p in picks[:50]) if e]
    by_id = time_calls(lambda i: store.get(entry_ids[i % len(entry_ids)]), 300)
    assert _report("read(get)", by_id, 20) <= 20 * FACTOR
    update = time_calls(
        lambda i: store.write(
            *picks[i % len(picks)], f"updated body {i} " * 120, author=user_author()
        ),
        300,
    )
    assert _report("write(update, ~2KiB)", update, 20) <= 20 * FACTOR
    roomy = layout.scopes[1:101]  # 가장 큰 범위(5,000개, 가득 참)는 만들기에서 뺀다
    create = time_calls(
        lambda i: store.write(
            roomy[i % len(roomy)],
            f"bench/{i}",
            f"fresh body {i} " * 150,
            author=user_author(),
            tags=["bench", "t"],
        ),
        200,
    )
    assert _report("write(create, ~2KiB)", create, 20) <= 20 * FACTOR


@strict_only
@needs_fts
def test_strict_list_first_page_50ms(big: tuple[SqliteMemoryStore, ScaleLayout]) -> None:
    store, layout = big
    scopes = layout.scopes[:60]  # 쪽마다 다른 범위: 미리보기 캐시가 비어 있는 경우
    cold = time_calls(
        lambda i: store.search(MemoryQuery(scopes=[scopes[i % len(scopes)]], limit=50)),
        len(scopes),
    )
    assert _report("list first page 50 (cold preview)", cold, 50) <= 50 * FACTOR
    warm = time_calls(lambda i: store.search(MemoryQuery(scopes=[scopes[0]], limit=50)), 50)
    _report("list first page 50 (warm preview, heavy scope)", warm)
    deep = time_calls(
        lambda i: store.search(MemoryQuery(scopes=[scopes[0]], limit=50, cursor="o:2000")), 20
    )
    _report("list page at offset 2000 (heavy scope)", deep)
    started = statistics.fmean(time_calls(lambda i: store.list_scopes(), 5))
    print(f"PERF list_scopes (200 scopes): mean={started * 1000:.2f} ms")


@strict_only
@needs_fts
def test_strict_fulltext_first_page_100ms(big: tuple[SqliteMemoryStore, ScaleLayout]) -> None:
    store, layout = big
    three = list(layout.scopes[:3])
    scoped_common = time_calls(
        lambda i: store.search(MemoryQuery(scopes=three, text=layout.common_word, limit=20)), 20
    )
    assert _report("fts scoped(3 scopes, heavy) common word", scoped_common, 100) <= 100 * FACTOR
    rare_all = time_calls(
        lambda i: store.search(MemoryQuery(text=layout.unique_word_of(i * 997), limit=20)), 40
    )
    assert _report("fts unscoped rare word", rare_all, 100) <= 100 * FACTOR
    tag_scoped = time_calls(
        lambda i: store.search(
            MemoryQuery(scopes=three, text=layout.common_word, tags=[layout.common_tag], limit=20)
        ),
        20,
    )
    assert _report("fts scoped + tag", tag_scoped, 100) <= 100 * FACTOR
    # 기록만(기준 없음): 전체 범위의 흔한 낱말(2만 건 맞음), 3글자 미만(포함 검색)
    _report(
        "fts unscoped common word (record only)",
        time_calls(lambda i: store.search(MemoryQuery(text=layout.common_word, limit=20)), 5),
    )
    _report(
        "like 2-char scoped(3 scopes) (record only)",
        time_calls(lambda i: store.search(MemoryQuery(scopes=three, text="zq", limit=20)), 3),
    )


@strict_only
@needs_fts
def test_strict_retention_plan_and_export_use_the_scanner(
    big: tuple[SqliteMemoryStore, ScaleLayout], tmp_path: Path
) -> None:
    from agent_console_conditions import builtin_operators
    from agent_console_memory import (
        EntryScanner,
        compile_retention_rules,
        retention_plan,
        write_markdown_archive,
    )

    store, layout = big
    assert isinstance(store, EntryScanner)

    def cond(*items: tuple[str, str, object]) -> dict[str, object]:
        return {"all": [{"path": p, "op": o, "value": v} for p, o, v in items]}

    rules = [
        {
            "id": "r1",
            "action": "archive",
            "when": cond(("/tags", "contains", "tag-common"), ("/idle_days", "gte", 30)),
        },
        {
            "id": "r2",
            "action": "delete",
            "when": cond(("/archived", "eq", True), ("/idle_days", "gte", 60)),
        },
        {
            "id": "r3",
            "action": "archive",
            "when": cond(("/scope/kind", "eq", "sk1"), ("/age_days", "gte", 365)),
        },
        {
            "id": "r4",
            "action": "archive",
            "when": cond(("/bytes", "gt", 4096), ("/last_read_days", "gte", 90)),
        },
        {
            "id": "r5",
            "action": "delete",
            "when": cond(("/author_kind", "eq", "agent"), ("/key", "matches", "^draft/")),
        },
    ]
    ops = {op.descriptor.id: op for op in builtin_operators()}
    compiled = compile_retention_rules(rules, ops)
    assert compiled.issues == ()
    walls: list[float] = []
    cpus: list[float] = []
    counts: set[int] = set()
    for _ in range(PLAN_RUNS):
        plan, wall, cpu = _timed_cpu(
            lambda: retention_plan(store, compiled, now=1_800_000_000.0, limit=1_000)
        )
        walls.append(wall)
        cpus.append(cpu)
        counts.add(plan.count)
    print(
        f"PERF retention_plan {layout.entries}+ entries / 5 rules: CPU min {min(cpus):.2f} s "
        f"(기준 2 s) cpu={[round(c, 2) for c in cpus]} wall={[round(w, 2) for w in walls]}, "
        f"planned {plan.count}"
    )
    assert len(counts) == 1  # 같은 저장소·같은 시각 → 같은 계획
    assert plan.count > 0
    assert min(cpus) <= 2 * FACTOR

    tags, wall, cpu = _timed_cpu(lambda: store.count_tags())
    print(f"PERF count_tags (all scopes): {wall:.2f} s wall, {cpu:.2f} s CPU, {len(tags)} tags")
    _, wall, cpu = _timed_cpu(lambda: store.count_tags(scopes=[layout.heavy_scope]))
    print(f"PERF count_tags (heavy scope): {wall * 1000:.0f} ms wall (record only)")

    chosen: list[MemoryScopeRef] = []
    total = 0
    for scope in layout.scopes:
        chosen.append(scope)
        total += len(list(store.scan_entries(scopes=[scope])))
        if total >= 10_000:
            break
    started = time.perf_counter()
    with (tmp_path / "export.zip").open("wb") as target:
        exported = write_markdown_archive(store, target, chosen)
    export_seconds = time.perf_counter() - started
    print(f"PERF export {exported} entries: {export_seconds:.2f} s (기준 5 s)")
    assert exported >= 10_000
    assert export_seconds <= 5 * FACTOR
