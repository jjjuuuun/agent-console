"""무작위 데이터로 SqliteLogIndex와 MemoryLogIndex의 답이 모든 질의에서 같음을 확인한다."""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC
from typing import Any

import pytest

from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogLane,
    LogProjectGroup,
    LogProjectSettings,
    TokenSample,
)
from agent_console_logs import (
    LogFilter,
    QueryContext,
    SessionTitleRule,
    load_default_session_title_rules,
)
from agent_console_logs._draft import TAG_SESSION_TITLE, TAG_TOOL
from agent_console_logs._filter import DIMENSIONS, METRICS
from agent_console_logs._index import IndexBatch, IndexRecord
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

CWDS = ["/w/a", "/w/a/sub", "/w/b", "/other", ""]
ROOTS = {"/w/a/sub": "/w/a"}
THREADS = ["main", "sub1", "sub2", ""]
MODELS = ["m1", "m2", ""]
CATS = ["input", "llm", "tool_call", "tool_result", "error", "handoff"]
TAG_POOL = ["x", "y", "session_title.renamed", "session_title.generated"]


def _records(seed: int, n: int) -> list[IndexRecord]:
    rng = random.Random(seed)
    out: list[IndexRecord] = []
    for i in range(n):
        cat = rng.choice(CATS)
        cwd = rng.choice(CWDS)
        thread = rng.choice(THREADS)
        call = rng.choice(["", "c1", "c2", "c3", "c4"])
        stage = rng.choice(["info", "start", "complete"])
        msg = rng.choice(["", "m1", "m2", "m3"])
        usage = None
        if msg and rng.random() < 0.7:
            usage = TokenSample(
                thread=thread,
                message_id=msg,
                model=rng.choice(MODELS),
                time=rng.choice([None, 1000.0 + rng.random() * 200000]),
                input_tokens=rng.choice([None, 5, 10]),
                output_tokens=rng.choice([None, 1, 20, 3]),
                cache_read_input_tokens=rng.choice([None, 4]),
            )
        tags = tuple(rng.sample([*TAG_POOL, TAG_TOOL, TAG_SESSION_TITLE], rng.randint(0, 2)))
        frm = tuple(rng.sample(["main", "sub1", "u"], rng.randint(0, 2)))
        to = tuple(rng.sample(["sub1", "sub2", "main"], rng.randint(0, 2)))
        out.append(
            make_record(
                cat,
                source=rng.choice(["s1", "s2"]),
                origin=f"f{i % 7}",
                offset=i,
                session=rng.choice(["S1", "S2", "S3", ""]),
                thread=thread,
                actor=rng.choice(["", "main", "user"]),
                tool=rng.choice(["", "Bash", "Read"]),
                call_id=call,
                stage=stage,
                message_id=msg,
                model=rng.choice(MODELS),
                run_id=rng.choice(["", "r1"]),
                status=rng.choice(["", "ok", "failed"]),
                via=rng.choice(["", "Task"]),
                cwd=cwd,
                repo_root=ROOTS.get(cwd, ""),
                time=rng.choice([None, 1000.0 + rng.random() * 200000]),
                observed_at=1000.0 + rng.random() * 200000,
                title=rng.choice(["Hello", "world", "Err 한글", ""]),
                tags=tags,
                from_=frm,
                to=to,
                correlation=rng.choice([{}, {"k": "a"}, {"k": ["a", "b"]}]),
                detail=rng.choice([None, {"cmd": "ls"}]),
                usage=usage,
                agent=LogLane(id=thread, label=rng.choice([None, "L"]), parent_id=None)
                if thread and rng.random() < 0.3
                else None,
            )
        )
    return out


def _ctx() -> QueryContext:
    return QueryContext(
        projects=LogProjectSettings(
            groups=[LogProjectGroup(id="A", label="A", match=["/w/a/**", "/w/a"])],
            ungrouped="cwd",
        ),
        error_categories=frozenset({"error"}),
        hidden_categories=frozenset({"handoff"}),
        tz=UTC,
    )


@pytest.fixture(scope="module")
def pair(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[MemoryLogIndex, SqliteLogIndex]]:
    mem = MemoryLogIndex()
    sql = open_log_index(tmp_path_factory.mktemp("diff") / "i.sqlite3")
    records = _records(7, 400)
    for i in range(0, len(records), 60):
        batch = IndexBatch(records=records[i : i + 60])
        a, b = mem.write(batch), sql.write(batch)
        assert (a.inserted, a.max_seq) == (b.inserted, b.max_seq)
    yield mem, sql
    sql.close()


FILTERS: list[dict[str, Any]] = [
    {},
    {"category": ("error",)},
    {"category": ("x", "tool_call")},
    {"source": ("s1",), "session": ("S1", "S2")},
    {"cwd": ("/w/a",)},
    {"project": ("A",)},
    {"project": ("~ungrouped",)},
    {"project": ("A", "~ungrouped")},
    {"agent": ("main",)},
    {"from_": ("main",), "to": ("sub1",)},
    {"tool": ("Bash",), "stage": ("start", "complete")},
    {"call_id": ("c1",)},
    {"model": ("m1",), "run_id": ("r1",)},
    {"status": ("failed",), "via": ("Task",)},
    {"since": 50000.0, "until": 120000.0},
    {"q": "hello"},
    {"q": "한글"},
    {"q": "NOPE"},
    {"category": ("tool_call",), "project": ("A",), "since": 20000.0},
]


def _flt(spec: dict[str, Any], **extra: Any) -> LogFilter:
    return LogFilter(**spec, **extra)


def dump(x: Any) -> Any:
    if isinstance(x, list):
        return [dump(i) for i in x]
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else x


@pytest.mark.parametrize("spec", FILTERS)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_events_pages_match(pair: Any, spec: dict[str, Any], order: str) -> None:
    mem, sql = pair
    flt = _flt(spec, order=order, limit=17)
    for _ in range(40):
        a = mem.query_events(flt, _ctx(), with_total=True)
        b = sql.query_events(flt, _ctx(), with_total=True)
        assert dump(a) == dump(b)
        if a.next_cursor is None:
            break
        flt = flt.with_(cursor=a.next_cursor)


@pytest.mark.parametrize("spec", FILTERS)
def test_sessions_and_handoffs_and_samples_match(pair: Any, spec: dict[str, Any]) -> None:
    mem, sql = pair
    flt = _flt(spec, limit=200)
    assert dump(mem.list_sessions(flt, _ctx())) == dump(sql.list_sessions(flt, _ctx()))
    assert dump(mem.handoffs(flt, _ctx())) == dump(sql.handoffs(flt, _ctx()))
    assert dump(mem.token_samples(flt, _ctx())) == dump(sql.token_samples(flt, _ctx()))


@pytest.mark.parametrize("session", ["S1", "S2", "S3", "none"])
@pytest.mark.parametrize("spec", FILTERS[:8])
def test_timeline_matches(pair: Any, session: str, spec: dict[str, Any]) -> None:
    mem, sql = pair
    for limit in (5000, 7):
        a = mem.timeline(session, _ctx(), flt=_flt(spec), limit=limit)
        b = sql.timeline(session, _ctx(), flt=_flt(spec), limit=limit)
        assert dump(a) == dump(b)


@pytest.mark.parametrize("metric", [m.id for m in METRICS])
@pytest.mark.parametrize("dim", [d.id for d in DIMENSIONS])
def test_aggregate_single_dim_matches(pair: Any, metric: str, dim: str) -> None:
    mem, sql = pair
    for spec in (FILTERS[0], FILTERS[5], FILTERS[14], FILTERS[1]):
        req = LogAggregateRequest(
            group_by=[dim], metric=metric, filter=_json(spec), tz="Asia/Seoul"
        )
        assert dump(mem.aggregate(req, _ctx())) == dump(sql.aggregate(req, _ctx()))


@pytest.mark.parametrize("metric", [m.id for m in METRICS])
def test_aggregate_multi_dim_matches(pair: Any, metric: str) -> None:
    mem, sql = pair
    for dims in ([], ["project", "day"], ["tag", "agent"], ["session", "model", "hour"]):
        req = LogAggregateRequest(group_by=dims, metric=metric)
        assert dump(mem.aggregate(req, _ctx())) == dump(sql.aggregate(req, _ctx()))


def _json(spec: dict[str, Any]) -> dict[str, Any]:
    return {k.rstrip("_"): list(v) if isinstance(v, tuple) else v for k, v in spec.items()}


def test_details_match(pair: Any) -> None:
    mem, sql = pair
    page = mem.query_events(LogFilter(limit=200), _ctx())
    for ev in page.items[::7]:
        for kwargs in ({}, {"max_evidence": 3}, {"max_detail_bytes": 4}):
            a = mem.get_event(ev.uid, _ctx(), **kwargs)
            b = sql.get_event(ev.uid, _ctx(), **kwargs)
            assert dump(a) == dump(b)
    assert sql.get_event("nope", _ctx()) is None
    assert dump(mem.lanes()) == dump(sql.lanes())


def test_prune_matches() -> None:
    mem, sql = MemoryLogIndex(), open_log_index(":memory:")
    for idx in (mem, sql):
        idx.write(IndexBatch(records=_records(3, 120)))
    assert mem.prune(60000.0) == sql.prune(60000.0)
    f = LogFilter(limit=200)
    assert dump(mem.query_events(f, _ctx(), with_total=True)) == dump(
        sql.query_events(f, _ctx(), with_total=True)
    )
    assert dump(mem.token_samples(f, _ctx())) == dump(sql.token_samples(f, _ctx()))
    req = LogAggregateRequest(group_by=["tag"], metric="events")
    assert dump(mem.aggregate(req, _ctx())) == dump(sql.aggregate(req, _ctx()))


@pytest.mark.parametrize(
    "rules",
    [
        (),
        (SessionTitleRule("x", "last"), SessionTitleRule(TAG_SESSION_TITLE, "first")),
        load_default_session_title_rules(),
    ],
)
@pytest.mark.parametrize("spec", [{}, {"category": ("error", "llm")}, {"since": 50000.0}])
def test_session_title_rules_match(pair: Any, rules: Any, spec: dict[str, Any]) -> None:
    """5R.19: 세션 제목 순위 규칙(데이터)이 두 색인에서 같은 제목을 고른다."""
    mem, sql = pair
    ctx = replace(_ctx(), session_title_rules=rules)
    a, b = mem.list_sessions(_flt(spec), ctx), sql.list_sessions(_flt(spec), ctx)
    assert [(s.session, s.title) for s in a] == [(s.session, s.title) for s in b]
