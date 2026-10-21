"""창 추정(순수 함수): 블록 경계·7일 이동·예산 있음/없음·셀 토큰 종류·값 지어내지 않기."""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest

from agent_console_contracts.logs import TokenSample
from agent_console_link_logs_usage import (
    CONFIG_SCHEMA,
    estimate_windows,
    load_default_config,
    parse_config,
)

HOUR = 3600.0
DAY = 86400.0
H0 = 1_800_000_000.0  # 정시(시 단위로 나누어떨어짐)
assert H0 % HOUR == 0


def sample(t: float, *, inp: int | None = 1, out: int | None = None, mid: str = "") -> TokenSample:
    return TokenSample(
        thread="main", message_id=mid or f"m{t}", time=t, input_tokens=inp, output_tokens=out
    )


def cfg(**config: Any) -> Any:
    return parse_config(config, load_default_config())


def by_window(snaps: list[Any]) -> dict[str, Any]:
    return {s.window: s for s in snaps}


def test_default_data_is_valid_against_schema() -> None:
    defaults = load_default_config()
    jsonschema.validate(defaults, CONFIG_SCHEMA)
    parsed = parse_config({}, defaults)
    assert [(w.id, w.kind, w.seconds) for w in parsed.windows] == [
        ("local_five_hour", "block", 5 * HOUR),
        ("local_seven_day", "rolling", 7 * DAY),
    ]
    assert parsed.budgets == {}


def test_block_starts_at_floored_hour_and_next_block_opens_at_block_end() -> None:
    # 첫 메시지 H0+0:30 → 블록 [H0, H0+5h). H0+4:59는 같은 블록, H0+5:10은 새 블록 [H0+5h, H0+10h)
    samples = [
        sample(H0 + 30 * 60, inp=10),
        sample(H0 + 299 * 60, inp=20),
        sample(H0 + 310 * 60, inp=7),
    ]
    now = H0 + 320 * 60
    snap = by_window(estimate_windows(samples, cfg(), now=now, source_id="local-logs"))[
        "local_five_hour"
    ]
    assert snap.status == "active"
    assert snap.used_tokens == 7
    assert snap.resets_at == H0 + 10 * HOUR
    assert snap.raw["block_start"] == H0 + 5 * HOUR
    assert snap.source == "local-logs"

    # 같은 표본, 블록 안 시각(H0+4:59 직후)이면 첫 블록이 활성
    early = estimate_windows(samples[:2], cfg(), now=H0 + 299 * 60 + 1, source_id="s")
    first = by_window(early)["local_five_hour"]
    assert (first.used_tokens, first.resets_at) == (30, H0 + 5 * HOUR)


def test_gap_longer_than_block_opens_new_block_and_idle_reports_zero_without_reset() -> None:
    samples = [sample(H0 + 10 * 60, inp=5), sample(H0 + 2 * HOUR, inp=5)]
    # 블록 끝(H0+5h)을 지나면 열린 블록이 없다
    snap = by_window(estimate_windows(samples, cfg(), now=H0 + 6 * HOUR, source_id="s"))[
        "local_five_hour"
    ]
    assert (snap.status, snap.used_tokens, snap.resets_at, snap.used_ratio) == (
        "idle",
        0,
        None,
        None,
    )


def test_seven_day_rolling_window_includes_boundary_and_excludes_older() -> None:
    now = H0 + 10 * DAY
    samples = [
        sample(now - 7 * DAY - 1, inp=1000),  # 창 밖
        sample(now - 7 * DAY, inp=3),  # 경계는 포함
        sample(now - HOUR, inp=4, out=6),
        sample(now + 60, inp=99),  # 미래(시계 차이)는 빼고
    ]
    snap = by_window(estimate_windows(samples, cfg(), now=now, source_id="s"))["local_seven_day"]
    assert snap.used_tokens == 13
    assert snap.resets_at is None
    assert snap.raw["tokens"]["input"] == 7
    assert snap.observed_at == now - HOUR  # 범위 안 마지막 표본 시각


def test_budget_gives_ratio_and_missing_budget_gives_none() -> None:
    now = H0 + HOUR
    samples = [sample(H0 + 60, inp=25)]
    with_budget = by_window(
        estimate_windows(samples, cfg(budgets={"local_five_hour": 100}), now=now, source_id="s")
    )
    assert with_budget["local_five_hour"].used_ratio == pytest.approx(0.25)
    assert with_budget["local_five_hour"].raw["budget"] == 100
    assert with_budget["local_seven_day"].used_ratio is None
    without = by_window(estimate_windows(samples, cfg(), now=now, source_id="s"))
    assert all(s.used_ratio is None for s in without.values())


def test_count_kinds_are_data_and_missing_values_stay_none() -> None:
    now = H0 + HOUR
    samples = [sample(H0 + 60, inp=5, out=None)]
    snaps = by_window(estimate_windows(samples, cfg(count=["output"]), now=now, source_id="s"))
    assert snaps["local_five_hour"].used_tokens is None
    assert snaps["local_seven_day"].used_tokens is None
    snaps = by_window(estimate_windows(samples, cfg(count=["input"]), now=now, source_id="s"))
    assert snaps["local_five_hour"].used_tokens == 5


def test_custom_windows_replace_defaults() -> None:
    now = H0 + 3 * HOUR
    config = cfg(
        windows=[
            {"id": "two_h", "kind": "block", "hours": 2},
            {"id": "day", "kind": "rolling", "days": 1},
            {"id": "two_h", "kind": "rolling", "hours": 9},  # 같은 id는 처음 것만
        ]
    )
    snaps = estimate_windows([sample(H0 + 2.5 * HOUR, inp=4)], config, now=now, source_id="s")
    assert [(s.window, s.used_tokens, s.resets_at) for s in snaps] == [
        ("two_h", 4, H0 + 4 * HOUR),
        ("day", 4, None),
    ]


def test_no_samples_in_range_means_no_windows() -> None:
    now = H0 + 100 * DAY
    assert estimate_windows([], cfg(), now=now, source_id="s") == []
    assert estimate_windows([sample(H0, inp=1)], cfg(), now=now, source_id="s") == []
    no_time = TokenSample(message_id="x", input_tokens=3)
    assert estimate_windows([no_time], cfg(), now=now, source_id="s") == []


@pytest.mark.parametrize(
    "config",
    [
        {"filter": {"since": "1"}},
        {"windows": [{"id": "w", "kind": "block"}]},
        {"windows": [{"id": "w", "kind": "monthly", "days": 30}]},
        {"budgets": {"w": 0}},
        {"count": ["everything"]},
        {"unknown": 1},
    ],
)
def test_schema_rejects_bad_config(config: dict[str, Any]) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(config, CONFIG_SCHEMA)
