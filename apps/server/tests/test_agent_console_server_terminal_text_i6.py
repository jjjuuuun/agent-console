"""I.6: 터미널에 찍히는 문구는 영어 원문, 웹으로 가는 응답 원문은 한국어 그대로(웹이 번역한다).

- 서버 명령행 도움말(모듈이 선언한 옵션 도움말 포함)에 한글이 없다.
- 시작을 거부하는 설정 오류(`settings.removed_key`·값 오류·루프백 아님·모르는 모듈 옵션)는
  영어로 표준 오류에 찍힌다. 이 오류는 서버가 뜨지 않으므로 웹에 가지 않는다.
- 터미널과 웹 둘 다에 보이는 설정 경고(`plugins.unknown_disabled` — `plugins.disabled`의 모르는
  이름)는 로그 줄이 영어, `GET /server-info` 경고 문구는 한국어 원문 그대로이고 코드·`details`가
  붙는다(웹은 코드 문구 묶음으로 영어·한국어를 고른다, I.7c).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pytest

import agent_console_server._app as server_app
from agent_console_modkit import FlagSetting, ModuleDescriptor, ModuleParts, SettingsCompat
from agent_console_server import ConfigError, create_app, main
from agent_console_server.testing import API, make_settings, server

_HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")


class _FlagModule:
    """명령행 옵션 하나를 선언한 모듈(서버는 이름을 모른다)."""

    descriptor = ModuleDescriptor(
        id="mod-i6-demo",
        version="0.0.1",
        kind="feature",
        title="I.6 demo",
        settings_compat=SettingsCompat(
            flags=(FlagSetting("i6-value", ("value",), help="Demo value", metavar="TEXT"),)
        ),
    )

    def build(self, ctx: Any) -> ModuleParts:
        return ModuleParts()


def test_serve_help_is_english(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"], prog="agent-console serve", modules=[_FlagModule()])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--i6-value" in out
    assert "Demo value (module mod-i6-demo)" in out
    assert _HANGUL.findall(out) == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("presets: {}\n", "Invalid settings (settings.removed_key): presets: "),
        ("usage: {}\n", "Move it to modules.options.mod-usage"),
        ("port: not-a-number\n", "Invalid settings: port: "),
        ("- a\n- b\n", "The top level of the settings file must be a mapping"),
    ],
)
def test_startup_config_errors_are_english(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    expected: str,
) -> None:
    monkeypatch.setattr(server_app, "serve", lambda *a, **k: pytest.fail("must not start"))
    config = tmp_path / "agent-console.yaml"
    config.write_text(body, encoding="utf-8")
    assert main(["--config", str(config)], prog="agent-console serve") == 2
    err = capsys.readouterr().err
    assert err.startswith("agent-console serve: ")
    assert expected in err
    assert _HANGUL.findall(err) == []


def test_unknown_module_flag_and_remote_bind_are_english(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as flag:
        server_app.flag_overrides({"nope-flag": "x"}, {})
    assert str(flag.value) == (
        "No installed server module declares the command-line option --nope-flag"
    )
    remote = make_settings(tmp_path, host="192.0.2.10")
    with pytest.raises(ConfigError) as bind:
        create_app(remote, environ={}, modules=[])
    assert "requires security.allow_remote: true" in str(bind.value)
    assert _HANGUL.findall(str(flag.value) + str(bind.value)) == []


def test_settings_warning_terminal_en_web_ko(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = make_settings(tmp_path, plugins={"disabled": ["no-such-plugin-i6"]})
    with caplog.at_level(logging.WARNING), server(settings) as client:
        info = client.get(f"{API}/server-info").json()
    [warning] = [w for w in info["warnings"] if w["code"] == "plugins.unknown_disabled"]
    assert warning["details"] == {"name": "no-such-plugin-i6"}
    # 웹: 한국어 원문 그대로(웹 한국어 화면이 바뀌지 않는다)
    assert "no-such-plugin-i6" in warning["message"]
    assert _HANGUL.search(warning["message"])
    # 터미널: 같은 경고가 영어 한 줄
    lines = [r.getMessage() for r in caplog.records if "no-such-plugin-i6" in r.getMessage()]
    assert lines == [
        "plugins.disabled: 'no-such-plugin-i6' is not an installed plugin name (ignored)"
    ]
