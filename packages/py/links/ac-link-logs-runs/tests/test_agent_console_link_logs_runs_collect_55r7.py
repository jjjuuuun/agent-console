"""5.5R.7 수집 보강(design §5.5R.1 C1·C2·C4·C7): 기본 대응표 데이터와 조건부 from·to."""

from __future__ import annotations

from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_runs import load_default_event_map
from agent_console_link_logs_runs.event_map import resolve
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_event, run_record
from agent_console_logs import LogFilter, query_context


def _events(rig: PlatformRunsRig) -> list[LogEvent]:
    return rig.index.query_events(LogFilter(limit=200), query_context(None)).items


def _rig(*events: object) -> PlatformRunsRig:
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(*events)  # type: ignore[arg-type]
    rig.scan()
    return rig


def test_conditional_value_renders_map_and_default_as_templates() -> None:
    spec = {
        "pointer": "/payload/call",
        "map": {"null": "", "7": "{/payload/x}"},
        "default": "{node}",
    }
    names = {"node": "m1"}
    assert resolve(spec, {"payload": {"call": None}}, names) == ""
    assert resolve(spec, {"payload": {"call": 0}}, names) == "m1"
    assert resolve(spec, {"payload": {"call": 7, "x": "칠"}}, names) == "칠"


def test_from_to_accept_conditional_values_in_user_rules() -> None:
    overrides = {
        "x.go": {
            "from": {"pointer": "/payload/who", "default": "{node}"},
            "to": {"pointer": "/payload/to", "map": {"null": ""}, "default": "{/payload/to}"},
        }
    }
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(
        run_event(1, "x.go", {"who": None, "to": "b"}, ("a",)),
        run_event(2, "x.go", {"to": None}, ("a",)),
    )
    rig.scan({"event_map": overrides})  # 설정 검증(RULE_SCHEMA)도 조건부 from·to를 받는다
    first, second = _events(rig)
    assert (first.from_, first.to) == (["a"], ["b"])
    assert (second.from_, second.to) == (["a"], [])


def test_node_events_carry_tool_use_id_and_to_only_for_calls() -> None:
    rig = _rig(
        run_event(1, "node.started", {"status": "running"}, ("lead",)),
        run_event(2, "agent.tool_call", {"tool_use_id": "tu1", "name": "delegate"}, ("lead",)),
        run_event(
            3,
            "node.started",
            {"status": "running", "call": 0, "tool_use_id": "tu1"},
            ("lead", "m1"),
        ),
        run_event(
            4,
            "node.completed",
            {"status": "succeeded", "call": 0, "tool_use_id": "tu1"},
            ("lead", "m1"),
        ),
        run_event(
            5, "node.failed", {"status": "failed", "call": 1, "tool_use_id": "tu2"}, ("lead", "m1")
        ),
    )
    lead, call, m1, done, failed = _events(rig)
    assert (lead.to, "tool_use_id" in lead.correlation) == ([], False)
    assert (m1.from_, m1.to, m1.via) == (["lead"], ["m1"], "delegate")
    assert call.call_id == "tu1"
    assert m1.correlation["tool_use_id"] == done.correlation["tool_use_id"] == "tu1"
    assert failed.correlation["tool_use_id"] == "tu2"


def test_context_prepared_usage_duration_and_mcp_server() -> None:
    resources = [{"id": "house", "kind": "rule", "bytes": 10, "sha256": "ab"}]
    rig = _rig(
        run_event(1, "agent.context_prepared", {"resources": resources, "fragments": 2}),
        run_event(2, "agent.usage", {"usage": {"input_tokens": 1}, "model": "m"}),
        run_event(
            3, "agent.usage", {"usage": {"input_tokens": 2}, "model": "m", "duration_ms": 500}
        ),
        run_event(4, "mcp.call_started", {"server": "docs", "tool": "q", "tool_use_id": "t"}),
        run_event(5, "mcp.call_completed", {"server": "docs", "tool": "q", "tool_use_id": "t"}),
    )
    events = _events(rig)
    [context] = [e for e in events if e.category == "context"]
    assert context.title == "맥락 구성"
    usage = [e for e in events if e.category == "usage"]
    # 소요를 모르는 사용량은 한 이벤트, 아는 것은 시작(inferred)·끝 두 이벤트
    assert [(e.stage, e.evidence) for e in usage] == [
        ("info", "observed"),
        ("start", "inferred"),
        ("complete", "observed"),
    ]
    assert usage[1].time == 103.0 - 0.5
    mcp = [e for e in events if e.category == "mcp"]
    assert [e.correlation.get("mcp_server") for e in mcp] == ["docs", "docs"]


def test_default_rules_are_data() -> None:
    table = load_default_event_map()
    assert table.rule_for("agent.context_prepared").get("category") == "context"
    assert table.rule_for("agent.usage").get("duration_ms") == "/payload/duration_ms"
    assert "usage" not in table.rule_for("agent.usage").spec
