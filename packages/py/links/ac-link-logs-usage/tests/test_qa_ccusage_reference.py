"""QA 독립 검증: ccusage 방식 블록·7일 창을 손 계산 픽스처와 독립 참조 구현으로 대조한다."""

from __future__ import annotations

import random
from pathlib import Path

from agent_console_contracts.logs import TokenSample
from agent_console_link_logs_usage import estimate_windows, load_default_config, parse_config

H = 3600.0
D = 86400.0
T0 = 1_800_000_000.0  # 정시
assert T0 % H == 0
SRC = Path(__file__).resolve().parents[1] / "src"


def s(t: float, n: int, mid: str) -> TokenSample:
    return TokenSample(thread="main", message_id=mid, time=t, input_tokens=n, output_tokens=0)


def run(samples: list[TokenSample], now: float, **config: object):  # type: ignore[no-untyped-def]
    cfg = parse_config(config, load_default_config())
    return {w.window: w for w in estimate_windows(samples, cfg, now=now, source_id="local-logs")}


def ref_blocks(times_tokens: list[tuple[float, int]], length: float):  # type: ignore[no-untyped-def]
    """ccusage 참조: 시 단위 내림 시작. 블록 끝 이후나 길이 이상 공백이면 새 블록."""
    blocks: list[list[float]] = []  # [start, end, tokens, last]
    for t, n in sorted(times_tokens):
        if blocks and t < blocks[-1][1] and t - blocks[-1][3] < length:
            blocks[-1][2] += n
            blocks[-1][3] = t
        else:
            start = (t // H) * H
            blocks.append([start, start + length, n, t])
    return blocks


def test_hand_fixture_1_boundaries() -> None:
    # 블록1 [T0, T0+5h): 0:30(10), 4:59:59(20). 4:59:59 -> 블록 끝(5:00) 전이라 같은 블록.
    # 5:00:00 정각(30) -> 새 블록 [T0+5h, T0+10h). 6:10(40)도 같은 블록.
    ss = [
        s(T0 + 0.5 * H, 10, "a"),
        s(T0 + 5 * H - 1, 20, "b"),
        s(T0 + 5 * H, 30, "c"),
        s(T0 + 6 * H + 600, 40, "d"),
    ]
    w = run(ss, T0 + 7 * H)["local_five_hour"]
    assert w.used_tokens == 70
    assert w.resets_at == T0 + 10 * H
    assert w.status == "active"
    assert w.observed_at == T0 + 6 * H + 600
    # 블록 끝 이후(10h 이후)에 보면 활성 없음
    idle = run(ss, T0 + 10 * H + 1)["local_five_hour"]
    assert idle.used_tokens == 0
    assert idle.status == "idle"
    assert idle.resets_at is None
    # 7일 이동: 전부 포함
    assert run(ss, T0 + 7 * H)["local_seven_day"].used_tokens == 100


def test_hand_fixture_2_gap_and_rolling_edge() -> None:
    # 시작 T0+0:45(5) 후 T0+3:44:59(7) -> 같은 블록. 이후 5h 이상 공백:
    # T0+9:00(11) -> 새 블록 [T0+9h, T0+14h). now=T0+9.5h -> 활성 합 11.
    # 7일 창: now-7d 경계 정각 표본 포함, 1초 이전 표본 제외.
    now = T0 + 9.5 * H
    edge = now - 7 * D
    ss = [
        s(edge - 1, 1000, "old"),
        s(edge, 100, "edge"),
        s(T0 + 0.75 * H, 5, "a"),
        s(T0 + 3 * H + 2699, 7, "b"),
        s(T0 + 9 * H, 11, "c"),
    ]
    r = run(ss, now)
    assert r["local_five_hour"].used_tokens == 11
    assert r["local_five_hour"].resets_at == T0 + 14 * H
    assert r["local_seven_day"].used_tokens == 100 + 5 + 7 + 11
    # 예산 -> 비율, 없으면 None
    r2 = run(ss, now, budgets={"local_five_hour": 110})
    assert r2["local_five_hour"].used_ratio == 0.1
    assert r2["local_seven_day"].used_ratio is None


def test_hand_fixture_3_gap_shorter_than_block_end_not_split() -> None:
    # 블록 시작 T0 (첫 0:59). 마지막 4:58. 둘 다 같은 블록(블록 끝 5:00 전).
    ss = [s(T0 + 0.99 * H, 1, "a"), s(T0 + 4.9 * H, 2, "b")]
    r = run(ss, T0 + 4.95 * H)["local_five_hour"]
    assert r.used_tokens == 3
    assert r.resets_at == T0 + 5 * H


def test_random_matches_reference() -> None:
    rng = random.Random(13)
    for _ in range(200):
        n = rng.randint(1, 25)
        pts = [(T0 + rng.uniform(0, 40 * H), rng.randint(1, 50)) for _ in range(n)]
        pts = [(float(int(t)), k) for t, k in pts]
        ss = [s(t, k, f"m{i}") for i, (t, k) in enumerate(pts)]
        now = max(t for t, _ in pts) + rng.uniform(0, 8 * H)
        got = run(ss, now)["local_five_hour"]
        blocks = ref_blocks(pts, 5 * H)
        last = blocks[-1]
        active = now < last[1] and now - last[3] < 5 * H
        assert (got.status == "active") == active
        if active:
            assert got.used_tokens == last[2]
            assert got.resets_at == last[1]
        assert run(ss, now)["local_seven_day"].used_tokens == sum(k for _, k in pts)


def test_no_window_ids_or_log_format_in_source() -> None:
    ids = [w["id"] for w in load_default_config()["windows"]]
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in [*ids, "claude-code-jsonl", "claude_code", "five_hour", "seven_day"]:
            assert needle not in text, (path, needle)
