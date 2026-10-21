"""statusLine 브리지: 파싱(창·필드 누락 허용), 원자적 쓰기, 창별 합치기, 상태 줄."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_usage.statusline import (
    STATUSLINE_FILE_FORMAT,
    StatuslineWindow,
    format_duration,
    format_status_line,
    merge_statusline,
    parse_statusline,
    read_statusline_file,
    statusline_windows,
    update_statusline_file,
    write_statusline_file,
)

NOW = 1_738_420_000.0

# 공식 문서 예시(https://code.claude.com/docs/en/statusline)를 줄인 것.
DOC_INPUT: dict[str, Any] = {
    "session_id": "secret-session",
    "transcript_path": "/home/u/.claude/projects/x.jsonl",
    "cwd": "/work/project",
    "model": {"id": "claude-x", "display_name": "X"},
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": NOW + 3600 * 2 + 13 * 60},
        "seven_day": {"used_percentage": 41.2, "resets_at": NOW + 86400 * 3},
        "spend_limit": {
            "used_percentage": 62.8,
            "resets_at": NOW + 86400 * 20,
            "used_usd": 314.12,
            "limit_usd": 500,
            "period": "monthly",
        },
    },
}


def test_parse_all_windows_from_input_keys() -> None:
    windows = parse_statusline(json.dumps(DOC_INPUT), now=NOW)
    assert [w.window for w in windows] == ["five_hour", "seven_day", "spend_limit"]
    five = windows[0]
    assert five.used_percentage == 23.5
    assert five.used_ratio == pytest.approx(0.235)
    assert five.observed_at == NOW
    assert windows[2].data["period"] == "monthly"  # 창 원문은 data로 보존


def test_parse_unknown_window_name_is_data() -> None:
    windows = parse_statusline({"rate_limits": {"weekly_zz": {"used_percentage": 5}}}, now=NOW)
    assert [w.window for w in windows] == ["weekly_zz"]


@pytest.mark.parametrize(
    "payload",
    [
        {},  # API 키 인증·첫 응답 전: rate_limits 없음
        {"rate_limits": None},
        {"rate_limits": []},
        {"rate_limits": {}},
        {"rate_limits": {"five_hour": "nope", "": {"used_percentage": 1}}},
    ],
)
def test_parse_missing_rate_limits_gives_no_windows(payload: dict[str, Any]) -> None:
    assert parse_statusline(payload, now=NOW) == []


def test_parse_missing_fields_are_none_not_invented() -> None:
    windows = parse_statusline(
        {
            "rate_limits": {
                "five_hour": {},
                "seven_day": {"used_percentage": None, "resets_at": "soon"},
                "x": {"used_percentage": True, "resets_at": -5},
                "y": {"used_percentage": float("nan")},
            }
        },
        now=NOW,
    )
    for w in windows:
        assert w.used_percentage is None
        assert w.used_ratio is None
        assert w.resets_at is None


def test_parse_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON"):
        parse_statusline("[1, 2]", now=NOW)
    with pytest.raises(json.JSONDecodeError):
        parse_statusline("not json", now=NOW)
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
        parse_statusline(b"\xff\xfe", now=NOW)


def test_update_writes_only_rate_limits_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state" / "usage" / "statusline.json"
    windows = update_statusline_file(path, json.dumps(DOC_INPUT).encode(), now=NOW)
    assert {w.window for w in windows} == {"five_hour", "seven_day", "spend_limit"}
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["format"] == STATUSLINE_FILE_FORMAT
    assert doc["updated_at"] == NOW
    assert doc["windows"]["five_hour"]["used_percentage"] == 23.5
    for leaked in ("secret-session", "transcript_path", "/work/project", "claude-x"):
        assert leaked not in text
    assert [p.name for p in path.parent.iterdir()] == ["statusline.json"]  # 임시 파일 없음


def test_update_without_windows_keeps_file(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    update_statusline_file(path, json.dumps(DOC_INPUT), now=NOW)
    before = path.read_bytes()
    kept = update_statusline_file(path, "{}", now=NOW + 10)
    assert path.read_bytes() == before
    assert {w.window for w in kept} == {"five_hour", "seven_day", "spend_limit"}
    assert all(w.observed_at == NOW for w in kept)  # 원래 관측 시각 그대로


def test_update_without_windows_and_no_file_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    assert update_statusline_file(path, "{}", now=NOW) == []
    assert not path.exists()


def test_invalid_input_leaves_file(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    update_statusline_file(path, json.dumps(DOC_INPUT), now=NOW)
    before = path.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        update_statusline_file(path, "{", now=NOW + 1)
    assert path.read_bytes() == before


def test_merge_keeps_other_windows_with_own_observed_at(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    update_statusline_file(path, json.dumps(DOC_INPUT), now=NOW)
    later = NOW + 60
    newer = {"rate_limits": {"five_hour": {"used_percentage": 30, "resets_at": NOW + 7200}}}
    windows = {w.window: w for w in update_statusline_file(path, json.dumps(newer), now=later)}
    assert windows["five_hour"].used_percentage == 30
    assert windows["five_hour"].observed_at == later
    assert windows["seven_day"].used_percentage == 41.2
    assert windows["seven_day"].observed_at == NOW


def test_merge_drops_windows_past_reset() -> None:
    old = merge_statusline(
        None,
        [StatuslineWindow("five_hour", NOW, 90.0, NOW + 10), StatuslineWindow("w", NOW, 1.0)],
        now=NOW,
    )
    doc = merge_statusline(old, [], now=NOW + 11)
    assert set(doc["windows"]) == {"w"}  # 초기화가 지난 창은 값이 무의미하다


def test_corrupt_file_is_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_statusline_file(path)
    windows = update_statusline_file(path, json.dumps(DOC_INPUT), now=NOW)
    assert len(windows) == 3
    assert read_statusline_file(path) is not None


def test_statusline_windows_skips_malformed_entries() -> None:
    doc = {
        "windows": {
            "ok": {"observed_at": NOW, "used_percentage": 3},
            "no_time": {"used_percentage": 3},
            "bad": "x",
        }
    }
    assert [w.window for w in statusline_windows(doc)] == ["ok"]
    assert statusline_windows(None) == []
    assert statusline_windows({"windows": []}) == []


def test_write_failure_cleans_temp(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    with pytest.raises(TypeError):
        write_statusline_file(path, {"x": object()})
    assert list(tmp_path.iterdir()) == []


def test_format_line_labels_missing_and_reset() -> None:
    windows = [
        StatuslineWindow("five_hour", NOW, 23.5, NOW + 2 * 3600 + 13 * 60),
        StatuslineWindow("seven_day", NOW, None, None),
        StatuslineWindow("gone", NOW, 50.0, NOW - 1),
    ]
    line = format_status_line(windows, now=NOW, labels={"five_hour": "5h"})
    assert line == "5h 24% (2h13m) · seven_day -"
    custom = format_status_line(
        windows[:1], now=NOW, template="{window}={percent}|{resets_in}", separator=" "
    )
    assert custom == "five_hour=24%|2h13m"
    assert format_status_line([], now=NOW, empty="(no data)") == "(no data)"
    with pytest.raises(KeyError):
        format_status_line(windows[:1], now=NOW, template="{nope}")


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (10, "<1m"),
        (45 * 60, "45m"),
        (2 * 3600 + 5 * 60, "2h05m"),
        (86400 * 3, "3d"),
        (90000, "1d1h"),
    ],
)
def test_format_duration(seconds: float, text: str) -> None:
    assert format_duration(seconds) == text
