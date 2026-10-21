from agent_console_contracts.logs import LogAggregateRequest
from agent_console_logs import QueryContext, link_events, pair_durations
from agent_console_logs.query import aggregate_rows
from agent_console_logs.testing import make_record


def _ev(**kw: object):  # type: ignore[no-untyped-def]
    return make_record(**kw).event  # type: ignore[arg-type]


def test_link_events_explicit_ids_only() -> None:
    a = _ev(category="x", call_id="c", time=1.0)
    b = _ev(category="x", call_id="c", time=50.0)
    near = _ev(category="x", time=1.1)  # 시간상 이웃이지만 id 공유 없음
    c = _ev(category="x", correlation={"task": ["t1", "t2"]})
    d = _ev(category="x", correlation={"task": "t2"})
    links = link_events([a, b, near, c, d])
    assert [(x.uid, x.basis) for x in links[a.uid]] == [(b.uid, "call_id")]
    assert near.uid not in links
    assert [(x.uid, x.value) for x in links[c.uid]] == [(d.uid, "t2")]
    hidden = link_events([a, b], visible=lambda e: e.uid != b.uid)
    assert hidden[a.uid] == []


def test_pair_durations_need_explicit_pairs() -> None:
    s = _ev(category="t", thread="T", call_id="k", stage="start", time=1.0)
    e = _ev(category="t", thread="T", call_id="k", stage="complete", time=3.0)
    other_thread = _ev(category="t", thread="U", call_id="k", stage="complete", time=2.0)
    untimed = _ev(category="t", thread="V", call_id="z", stage="start")
    out = pair_durations([s, e, other_thread, untimed])
    assert out == {s.uid: 2000.0, e.uid: 2000.0}


def test_duration_avg_and_p95() -> None:
    events = []
    for i, dur in enumerate((1.0, 2.0, 3.0, 10.0)):
        for stage, t in (("start", 0.0), ("complete", dur)):
            events.append(_ev(category="t", thread="T", call_id=f"c{i}", stage=stage, time=t))
    ctx = QueryContext()
    avg = aggregate_rows(LogAggregateRequest(metric="duration_ms.avg"), events, [], ctx)
    p95 = aggregate_rows(LogAggregateRequest(metric="duration_ms.p95"), events, [], ctx)
    assert avg[0].value == 4000.0
    assert p95[0].value == 10000.0
    request = LogAggregateRequest(metric="duration_ms.sum")
    assert aggregate_rows(request, [_ev(category="x")], [], ctx) == []
