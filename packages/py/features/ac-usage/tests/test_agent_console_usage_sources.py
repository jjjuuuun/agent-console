"""기본 출처: run-events, statusline-file, fake. 값을 지어내지 않는다."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

from agent_console_contracts import RunEvent
from agent_console_usage import (
    FakeUsageSource,
    RunEventUsageSource,
    StatuslineFileSource,
    UsageSourceContext,
    update_statusline_file,
)

NOW = 1_800_000_000.0


class FakeEvents:
    """`latest_by_type`만 있는 가짜 이벤트 저장소(ts 내림차순)."""

    def __init__(self, events: list[RunEvent]) -> None:
        self.events = events
        self.calls: list[tuple[str, int]] = []

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        self.calls.append((type, limit))
        rows = [e for e in self.events if e.type == type]
        rows.sort(key=lambda e: e.ts, reverse=True)
        return rows[:limit]


def _event(seq: int, ts: float, payload: dict[str, Any], *, actor: str | None = None) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}",
        run_id="r1",
        seq=seq,
        ts=ts,
        node_path=["lead"],
        actor=actor,
        type="usage.rate_limit",
        payload=payload,
    )


async def test_run_events_latest_per_window() -> None:
    events = FakeEvents(
        [
            _event(1, NOW - 100, {"window": "five_hour", "status": "allowed", "utilization": 0.1}),
            _event(
                2,
                NOW - 50,
                {"window": "five_hour", "status": "allowed_warning", "utilization": 0.8},
            ),
            _event(3, NOW - 70, {"window": "seven_day", "status": "allowed"}, actor="pl"),
            _event(4, NOW - 10, {"bad": True}),  # 형식이 틀린 payload는 건너뛴다
        ]
    )
    ctx = UsageSourceContext(source_id="run-events", events=events, now=NOW)
    snaps = await RunEventUsageSource().snapshot(ctx)
    assert [(s.window, s.status, s.used_ratio) for s in snaps] == [
        ("five_hour", "allowed_warning", 0.8),
        ("seven_day", "allowed", None),  # utilization 없음 → None(지어내지 않음)
    ]
    assert snaps[0].observed_at == NOW - 50
    assert snaps[1].resets_at is None
    assert snaps[1].raw["actor"] == "pl"
    assert all(s.source == "run-events" for s in snaps)
    assert events.calls == [("usage.rate_limit", 200)]


async def test_run_events_config_and_no_store() -> None:
    events = FakeEvents([])
    src = RunEventUsageSource()
    ctx = UsageSourceContext(
        source_id="a", config={"event_type": "x.limit", "scan_limit": 5}, events=events
    )
    assert await src.snapshot(ctx) == []
    assert events.calls == [("x.limit", 5)]
    assert await src.snapshot(UsageSourceContext(source_id="a")) == []


async def test_statusline_file_source(tmp_path: Path) -> None:
    state = tmp_path / ".state"
    src = StatuslineFileSource()
    ctx = UsageSourceContext(source_id="statusline-file", state_dir=state, now=NOW)
    assert await src.snapshot(ctx) == []  # 아직 설정 안 함
    update_statusline_file(
        state / "usage" / "statusline.json",
        json.dumps(
            {
                "rate_limits": {
                    "five_hour": {"used_percentage": 12, "resets_at": NOW + 600},
                    "seven_day": {"resets_at": NOW + 6000},
                }
            }
        ),
        now=NOW - 5,
    )
    snaps = await src.snapshot(ctx)
    assert [(s.window, s.used_ratio, s.observed_at) for s in snaps] == [
        ("five_hour", 0.12, NOW - 5),
        ("seven_day", None, NOW - 5),
    ]
    assert all(s.status is None and s.used_tokens is None for s in snaps)


async def test_statusline_file_paths(tmp_path: Path) -> None:
    src = StatuslineFileSource()
    custom = tmp_path / "elsewhere.json"
    update_statusline_file(custom, '{"rate_limits": {"w": {"used_percentage": 1}}}', now=NOW)
    ctx = UsageSourceContext(source_id="s", config={"path": str(custom)})
    assert [s.window for s in await src.snapshot(ctx)] == ["w"]
    # 상대 경로인데 state_dir가 없으면 읽지 않는다
    assert await src.snapshot(UsageSourceContext(source_id="s")) == []
    rel = UsageSourceContext(source_id="s", config={"path": "x/y.json"}, state_dir=tmp_path)
    assert src.resolve_path(rel) == tmp_path / "x" / "y.json"


async def test_fake_source_returns_only_configured() -> None:
    src = FakeUsageSource()
    assert await src.snapshot(UsageSourceContext(source_id="fake", now=NOW)) == []
    ctx = UsageSourceContext(
        source_id="fake",
        now=NOW,
        config={
            "windows": [
                {"window": "five_hour", "used_ratio": 0.4, "resets_in_seconds": 60},
                {"window": "w2", "observed_seconds_ago": 30},
            ]
        },
    )
    a, b = await src.snapshot(ctx)
    assert (a.used_ratio, a.resets_at, a.observed_at) == (0.4, NOW + 60, NOW)
    assert (b.used_ratio, b.status, b.resets_at, b.observed_at) == (None, None, None, NOW - 30)
    assert src.descriptor.trust == "fake"  # 알려진 등급 밖의 값도 선언할 수 있다
