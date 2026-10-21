import pytest

from agent_console_contracts.logs import TokenSample
from agent_console_logs import block_windows, rolling_totals, sum_samples

H = 3600.0


def _s(t: float | None, out: int = 1) -> TokenSample:
    return TokenSample(time=t, output_tokens=out, input_tokens=2)


def test_blocks_floor_to_hour_and_split() -> None:
    samples = [_s(10 * H + 600), _s(11 * H), _s(15 * H + 1), _s(None)]
    blocks = block_windows(samples, hours=5, now=16 * H)
    assert [(b.start, b.end, b.samples) for b in blocks] == [
        (10 * H, 15 * H, 2),
        (15 * H, 20 * H, 1),
    ]
    assert [b.active for b in blocks] == [False, True]
    assert blocks[0].tokens.output == 2
    assert blocks[0].tokens.total == 6


def test_gap_longer_than_block_starts_new_block() -> None:
    blocks = block_windows([_s(0.0), _s(1 * H)], hours=0.5)
    assert len(blocks) == 2
    assert all(not b.active for b in blocks)


def test_invalid_hours() -> None:
    with pytest.raises(ValueError, match="hours"):
        block_windows([], hours=0)


def test_sums_keep_nulls() -> None:
    totals = sum_samples([TokenSample()])
    assert totals.total is None
    assert rolling_totals([_s(5.0), _s(100.0)], seconds=10, now=100.0).output == 1
