"""`agent-console statusline`: stdin JSON → 상태 줄 + 원자적 쓰기, 누락 허용, `~/.claude` 무접촉."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_cli import main
from agent_console_cli._server import server_state_dir
from agent_console_cli._statusline import StatuslineOptions, parse_labels, run_statusline

NOW = 1_800_000_000.0

INPUT: dict[str, Any] = {
    "session_id": "sess-should-not-be-stored",
    "cwd": "/w",
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": NOW + 2 * 3600 + 13 * 60},
        "seven_day": {"used_percentage": 41.2, "resets_at": NOW + 3 * 86400},
    },
}


def _run(data: bytes, path: Path, **opts: Any) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = run_statusline(
        data, path, now=lambda: NOW, out=out, err=err, options=StatuslineOptions(**opts)
    )
    return code, out.getvalue(), err.getvalue()


def test_run_statusline_writes_file_and_prints_line(tmp_path: Path) -> None:
    path = tmp_path / "usage" / "statusline.json"
    code, out, err = _run(json.dumps(INPUT).encode(), path, labels={"five_hour": "5h"})
    assert (code, err) == (0, "")
    assert out == "5h 24% (2h13m) · seven_day 41% (3d)\n"
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert set(doc["windows"]) == {"five_hour", "seven_day"}
    assert "sess-should-not-be-stored" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rate_limits": {}},
        {"rate_limits": {"five_hour": {}}},
        {"rate_limits": {"seven_day": {"resets_at": NOW + 60}}},
    ],
)
def test_missing_windows_and_fields_are_tolerated(tmp_path: Path, payload: dict[str, Any]) -> None:
    code, out, err = _run(json.dumps(payload).encode(), tmp_path / "s.json", empty="-")
    assert code == 0
    assert err == ""
    assert "%" not in out  # 사용률이 없으면 숫자를 만들지 않는다


def test_invalid_json_exits_1_and_keeps_file(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    _run(json.dumps(INPUT).encode(), path)
    before = path.read_bytes()
    code, out, err = _run(b"{not json", path, empty="?")
    assert code == 1
    assert out == "?\n"
    assert "JSON" in err
    assert path.read_bytes() == before


def test_write_failure_still_prints_line(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    code, out, err = _run(json.dumps(INPUT).encode(), blocker / "sub" / "s.json")
    assert code == 1
    assert "five_hour 24%" in out
    assert str(tmp_path) not in err  # 경로를 노출하지 않는다


def test_parse_labels() -> None:
    assert parse_labels(["five_hour=5h", "seven_day=주간", "x="]) == {
        "five_hour": "5h",
        "seven_day": "주간",
        "x": "",
    }
    with pytest.raises(ValueError, match="--label"):
        parse_labels(["nolabel"])


def _stdin(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


def test_command_with_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _stdin(monkeypatch, json.dumps(INPUT).encode())
    out_file = tmp_path / "ws" / ".state" / "usage" / "statusline.json"
    code = main(
        ["statusline", "--output", str(out_file), "--label", "five_hour=5h", "--separator", " | "]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert printed.startswith("5h ")
    assert " | seven_day " in printed
    assert out_file.exists()
    assert list(home.iterdir()) == []  # ~/.claude를 만들거나 쓰지 않는다


def test_command_requires_output_or_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AGENT_CONSOLE_CONFIG", raising=False)
    _stdin(monkeypatch, b"{}")
    assert main(["statusline"]) == 2
    assert "--output" in capsys.readouterr().err


def test_command_rejects_bad_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, b"{}")
    assert main(["statusline", "-o", str(tmp_path / "s.json"), "--label", "bad"]) == 2
    _stdin(monkeypatch, b"{}")
    assert main(["statusline", "-o", str(tmp_path / "s.json"), "--template", "{nope}"]) == 2
    assert not (tmp_path / "s.json").exists()


def test_command_uses_server_config_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "agent-console.yaml"
    cfg.write_text("workspace: ws\n", encoding="utf-8")
    assert server_state_dir(cfg, environ={}) == tmp_path / "ws" / ".state"
    _stdin(monkeypatch, json.dumps(INPUT).encode())
    assert main(["statusline", "--config", str(cfg)]) == 0
    assert (tmp_path / "ws" / ".state" / "usage" / "statusline.json").exists()
    # --label이 없으면 데이터의 짧은 이름(창 id가 그대로 보이지 않는다, 5.2R.27)
    printed = capsys.readouterr().out
    assert printed.startswith("5h 24%")
    assert "7d 41%" in printed
    assert "five_hour" not in printed
