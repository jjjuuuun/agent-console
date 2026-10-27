"""필터 `thread`·`scope`·`max_seq`와 질의 확장 X27(범위 종류)·X28(필터 확장) (5.5R.5).

- 등록이 없을 때 결과가 그대로다(회귀).
- 모르는 범위 종류·필터 이름은 `LogQueryError`(모듈이 422로 바꾼다).
- 가짜 범위 종류·가짜 필터로 페이지를 넘길 때 메모리·SQLite 색인 결과가 같다(차등 0).
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC
from typing import Any

import pytest

from agent_console_contracts.logs import LogAggregateRequest, LogLane, TokenSample
from agent_console_logs import (
    LogFilter,
    LogQueryError,
    LogQueryExtensions,
    LogScope,
    QueryContext,
    filter_to_params,
    parse_log_filter,
    query_schema,
)
from agent_console_logs._draft import TAG_TOOL
from agent_console_logs._filter import DIMENSIONS, METRICS
from agent_console_logs._index import IndexBatch, IndexRecord
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import FieldFilter, MemoryLogIndex, TableScopeKind, make_record

THREADS = ["main", "sub1", "sub2", ""]
SESSIONS = ["S1", "S2", "S3", "S4", ""]
RUNS = ["", "", "r1", "r2", "r3"]


def _records(seed: int, n: int) -> list[IndexRecord]:
    rng = random.Random(seed)
    out: list[IndexRecord] = []
    for i in range(n):
        thread = rng.choice(THREADS)
        msg = rng.choice(["", "m1", "m2", "m3"])
        usage = None
        if msg and rng.random() < 0.7:
            usage = TokenSample(
                thread=thread,
                message_id=msg,
                model="m",
                time=rng.choice([None, 1000.0 + rng.random() * 1000]),
                input_tokens=rng.choice([None, 5, 10]),
                output_tokens=rng.choice([None, 1, 20]),
            )
        out.append(
            make_record(
                rng.choice(["input", "llm", "tool_call", "tool_result", "error"]),
                source=rng.choice(["s1", "s2"]),
                origin=f"f{i % 5}",
                offset=i,
                session=rng.choice(SESSIONS),
                thread=thread,
                actor=rng.choice(["", "main"]),
                tool=rng.choice(["", "Bash", "Read"]),
                call_id=rng.choice(["", "c1", "c2"]),
                stage=rng.choice(["info", "start", "complete"]),
                message_id=msg,
                run_id=rng.choice(RUNS),
                time=rng.choice([None, 1000.0 + rng.random() * 1000]),
                observed_at=1000.0 + rng.random() * 1000,
                tags=tuple(rng.sample(["x", TAG_TOOL], rng.randint(0, 1))),
                from_=tuple(rng.sample(["main", "u"], rng.randint(0, 1))),
                to=tuple(rng.sample(["sub1", "main"], rng.randint(0, 1))),
                detail=rng.choice([None, {"cmd": "ls"}, {"other": 1}]),
                usage=usage,
                agent=LogLane(id=thread) if thread and rng.random() < 0.3 else None,
            )
        )
    return out


def _ctx() -> QueryContext:
    return QueryContext(error_categories=frozenset({"error"}), tz=UTC)


SCOPES = TableScopeKind(
    "fake",
    {
        "a": (["S1"], []),
        "b": ([], ["r1"]),
        "c": (["S2", "S4"], ["r2", "r3"]),
        "none": ([], []),
    },
)
EXT = LogQueryExtensions.collect(
    [SCOPES], [FieldFilter("fake_tool", "tool", detail_key="cmd"), FieldFilter("fake_th", "thread")]
)


@pytest.fixture(scope="module")
def pair(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[MemoryLogIndex, SqliteLogIndex]]:
    mem = MemoryLogIndex()
    sql = open_log_index(tmp_path_factory.mktemp("ext") / "i.sqlite3")
    records = _records(11, 300)
    for i in range(0, len(records), 50):
        batch = IndexBatch(records=records[i : i + 50])
        a, b = mem.write(batch), sql.write(batch)
        assert (a.inserted, a.max_seq) == (b.inserted, b.max_seq)
    yield mem, sql
    sql.close()


def dump(x: Any) -> Any:
    if isinstance(x, list):
        return [dump(i) for i in x]
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


PARAMS: list[dict[str, Any]] = [
    {"thread": "main"},
    {"thread": "sub1,sub2"},
    {"max_seq": "150"},
    {"max_seq": "0"},
    {"scope": "fake:a"},
    {"scope": "fake:b"},
    {"scope": "fake:c", "thread": "main,sub1"},
    {"scope": "fake:none"},
    {"fake_tool": "Bash"},
    {"fake_tool": "!Read", "fake_th": "sub1,main"},
    {"fake_tool": "Bash", "fake_tool_has": "1"},
    {"scope": "fake:c", "fake_tool": "Bash", "max_seq": "200"},
    {"scope": "fake:b", "category": "tool_call", "fake_th": "main"},
]


def _resolved(params: dict[str, Any], **extra: Any) -> tuple[LogFilter, QueryContext]:
    flt = EXT.parse(params).with_(**extra)
    return flt, EXT.refine(flt, _ctx())


# ---------------------------------------------------------------- 필터 읽기


def test_parse_new_fields() -> None:
    flt = parse_log_filter({"thread": "a,b", "scope": "run:x:y", "max_seq": "7"})
    assert flt.thread == ("a", "b")
    assert flt.scope == "run:x:y"  # 값에 `:`가 있어도 된다(앞 `:`에서 나눈다)
    assert flt.max_seq == 7
    for bad in ({"scope": "nokind"}, {"scope": ":v"}, {"scope": "k:"}):
        with pytest.raises(LogQueryError) as err:
            parse_log_filter(bad)
        assert err.value.path == "scope"
    for bad_seq in ("x", "-1"):
        with pytest.raises(LogQueryError) as err:
            parse_log_filter({"max_seq": bad_seq}, path="filter")
        assert err.value.path == "filter.max_seq"


def test_extension_names_only_when_registered() -> None:
    with pytest.raises(LogQueryError) as err:
        parse_log_filter({"fake_tool": "Bash"})
    assert err.value.path == "fake_tool"
    flt = EXT.parse({"fake_tool": "Bash,Read", "fake_th": "main"})
    assert flt.extra == (("fake_th", ("main",)), ("fake_tool", ("Bash", "Read")))
    # 보관본 범위 직렬화가 되돌아온다
    assert EXT.parse(filter_to_params(flt)) == flt


def test_extension_blank_value_is_kept() -> None:
    """5.5R.10: 확장 필터의 빈 값(`name=`)은 값 `""` 하나다(이름 없는 묶음 `arch_group=`)."""
    flt = EXT.parse({"fake_tool": ""})
    assert flt.extra == (("fake_tool", ("",)),)
    assert EXT.parse({"fake_tool": [""]}).extra == (("fake_tool", ("",)),)
    assert EXT.parse({"fake_tool": None}).extra == ()
    assert EXT.parse(filter_to_params(flt)) == flt
    # 기본 필드의 빈 값은 지금처럼 버린다
    assert parse_log_filter({"tool": ""}).tool == ()


def test_schema_lists_new_and_extension_filters() -> None:
    names = [f.id for f in query_schema().filters]
    assert {"thread", "scope", "max_seq"} <= set(names)
    ext_names = [f.id for f in EXT.schema().filters]
    assert ext_names[: len(names)] == names
    assert ext_names[len(names) :] == ["fake_tool", "fake_tool_has", "fake_th"]


def test_collect_skips_duplicates_and_builtin_clashes() -> None:
    ext = LogQueryExtensions.collect(
        [SCOPES, TableScopeKind("fake"), TableScopeKind("a:b")],
        [FieldFilter("x", "tool"), FieldFilter("x", "thread"), FieldFilter("thread", "thread")],
    )
    assert list(ext.scope_kinds) == ["fake"]
    assert ext.scope_kinds["fake"] is SCOPES
    assert ext.filter_names == frozenset({"x"})
    assert len(ext.skipped) == 4


def test_refine_errors() -> None:
    ctx = _ctx()
    with pytest.raises(LogQueryError) as err:
        EXT.refine(parse_log_filter({"scope": "nope:1"}), ctx)
    assert err.value.path == "scope"
    with pytest.raises(LogQueryError) as err:
        EXT.refine(parse_log_filter({"scope": "fake:missing"}), ctx, path="filter")
    assert err.value.path == "filter.scope"
    with pytest.raises(LogQueryError) as err:
        EXT.refine(EXT.parse({"fake_tool_has": "2"}), ctx)
    assert err.value.path == "fake_tool_has"
    # 등록이 없는 묶음은 확장 이름을 모른다
    with pytest.raises(LogQueryError):
        LogQueryExtensions().refine(EXT.parse({"fake_tool": "Bash"}), ctx)


def test_no_registration_keeps_context() -> None:
    ctx = _ctx()
    flt = parse_log_filter({"thread": "main", "max_seq": "3"})
    assert LogQueryExtensions().refine(flt, ctx) is ctx


def test_unrefined_scope_or_extension_is_rejected(pair: Any) -> None:
    mem, sql = pair
    for flt in (LogFilter(scope="fake:a"), EXT.parse({"fake_tool": "Bash"})):
        for idx in (mem, sql):
            with pytest.raises(LogQueryError):
                idx.query_events(flt, _ctx())
            with pytest.raises(LogQueryError):
                idx.list_sessions(flt, _ctx())
            with pytest.raises(LogQueryError):
                idx.token_samples(flt, _ctx())


# ---------------------------------------------------------------- 의미


def test_scope_thread_max_seq_semantics(pair: Any) -> None:
    mem, _sql = pair
    every = mem.query_events(LogFilter(limit=200), _ctx()).items
    every += mem.query_events(LogFilter(limit=200, cursor=str(every[-1].seq)), _ctx()).items
    assert len(every) == mem.query_events(LogFilter(limit=1), _ctx(), with_total=True).total
    flt, ctx = _resolved({"scope": "fake:c"}, limit=200)
    got = {e.uid for e in mem.query_events(flt, ctx).items}
    want = {
        e.uid
        for e in every
        if (e.session and e.session in {"S2", "S4"}) or (e.run_id and e.run_id in {"r2", "r3"})
    }
    assert got == want
    assert got
    flt, ctx = _resolved({"max_seq": "40", "thread": "main"}, limit=200)
    got_seq = [e.seq for e in mem.query_events(flt, ctx).items]
    assert got_seq == [e.seq for e in every if e.seq <= 40 and e.thread == "main"]
    flt, ctx = _resolved({"fake_tool": "Bash", "fake_tool_has": "1"}, limit=200)
    picked = mem.query_events(flt, ctx).items
    assert picked
    assert all(e.tool == "Bash" for e in picked)
    full = {e.uid: mem.get_event(e.uid, _ctx()) for e in picked}
    assert all(d is not None and d.event.detail == {"cmd": "ls"} for d in full.values())


def test_scope_limits_token_samples() -> None:
    idx = MemoryLogIndex()
    sample = TokenSample(thread="t", message_id="m", model="x", input_tokens=1, output_tokens=1)
    other = sample.model_copy(update={"message_id": "n"})
    idx.write(
        IndexBatch(
            records=[
                make_record(
                    "llm", session="S9", thread="t", message_id="m", run_id="rX", usage=sample
                ),
                make_record("llm", session="S8", thread="t", message_id="n", offset=1, usage=other),
            ]
        )
    )
    by_run = LogQueryExtensions.collect([TableScopeKind("k", {"r": ([], ["rX"])})])
    flt = by_run.parse({"scope": "k:r"})
    assert [s.message_id for s in idx.token_samples(flt, by_run.refine(flt, _ctx()))] == ["m"]
    by_session = LogQueryExtensions.collect([TableScopeKind("k", {"s": (["S8"], [])})])
    flt = by_session.parse({"scope": "k:s"})
    assert [s.message_id for s in idx.token_samples(flt, by_session.refine(flt, _ctx()))] == ["n"]


# ---------------------------------------------------------------- 차등(메모리 = SQLite)


@pytest.mark.parametrize("params", PARAMS)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_pages_match(pair: Any, params: dict[str, Any], order: str) -> None:
    mem, sql = pair
    flt, ctx = _resolved(params, order=order, limit=13)
    pages = 0
    for _ in range(40):
        a = mem.query_events(flt, ctx, with_total=True)
        b = sql.query_events(flt, ctx, with_total=True)
        assert dump(a) == dump(b)
        pages += 1
        if a.next_cursor is None:
            break
        flt = flt.with_(cursor=a.next_cursor)
    assert pages < 40


@pytest.mark.parametrize("params", PARAMS)
def test_sessions_handoffs_samples_timeline_match(pair: Any, params: dict[str, Any]) -> None:
    mem, sql = pair
    flt, ctx = _resolved(params, limit=200)
    assert dump(mem.list_sessions(flt, ctx)) == dump(sql.list_sessions(flt, ctx))
    assert dump(mem.handoffs(flt, ctx)) == dump(sql.handoffs(flt, ctx))
    assert dump(mem.token_samples(flt, ctx)) == dump(sql.token_samples(flt, ctx))
    for session in ("S1", "S2", "S4"):
        for limit in (5000, 4):
            a = mem.timeline(session, ctx, flt=flt, limit=limit)
            b = sql.timeline(session, ctx, flt=flt, limit=limit)
            assert dump(a) == dump(b)


@pytest.mark.parametrize("metric", [m.id for m in METRICS])
def test_aggregate_matches(pair: Any, metric: str) -> None:
    mem, sql = pair
    for params in PARAMS:
        flt = EXT.parse(params)
        ctx = EXT.refine(flt, _ctx(), path="filter")
        for dims in (["session"], ["agent", "day"], [d.id for d in DIMENSIONS[:2]]):
            req = LogAggregateRequest(group_by=dims, metric=metric, filter=dict(params))
            assert dump(mem.aggregate(req, ctx)) == dump(sql.aggregate(req, ctx))


def test_registration_without_use_changes_nothing(pair: Any) -> None:
    """등록만 있고 필터가 쓰지 않으면 등록이 없을 때와 결과가 같다(회귀)."""
    mem, sql = pair
    base = LogFilter(limit=50, category=("tool_call",))
    plain = _ctx()
    refined = EXT.refine(base, plain)
    assert refined.scope is None
    assert refined.predicates == ()
    for idx in (mem, sql):
        assert dump(idx.query_events(base, plain, with_total=True)) == dump(
            idx.query_events(base, refined, with_total=True)
        )
        assert dump(idx.list_sessions(base, plain)) == dump(idx.list_sessions(base, refined))


def test_scope_object_contains() -> None:
    scope = LogScope.of(["S", ""], ["", "r"])
    assert scope.sessions == frozenset({"S"})
    assert scope.run_ids == frozenset({"r"})
    assert scope.contains("S", "")
    assert scope.contains("", "r")
    assert not scope.contains("", "")
    assert not LogScope().contains("S", "r")
