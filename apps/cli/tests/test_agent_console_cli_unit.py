"""agent-console-cli 단위 테스트: 노출 명령·serve 조립·허용 출처 덧붙이기·시작 시 import 범위."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import typer

import agent_console_cli._app as cli_app
from agent_console_cli import main
from agent_console_cli._server import (
    ServerConfigError,
    merge_origins,
    run_server,
    serve_overrides,
)

# ---------------------------------------------------------------- 명령

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain_help_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """도움말 출력을 환경(CI 색 강제·좁은 터미널)과 무관하게 고정한다.

    typer는 `GITHUB_ACTIONS`·`FORCE_COLOR`를 import 시점에 읽어 색을 강제하므로
    환경변수만으로는 부족하다. 출력 쪽에서도 `_strip_ansi`로 색 코드를 지운다.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "200")
    for name in ("FORCE_COLOR", "GITHUB_ACTIONS", "PY_COLORS"):
        monkeypatch.delenv(name, raising=False)


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def test_only_serve_and_statusline_are_exposed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _plain_help_env(monkeypatch)
    monkeypatch.setenv("AGENT_CONSOLE_TOKEN", "sekret-token-should-not-show")
    assert main(["--help"]) == 0
    top = _strip_ansi(capsys.readouterr().out)
    assert "serve" in top
    assert "statusline" in top
    commands: dict[str, object] = getattr(typer.main.get_command(cli_app.app), "commands", {})
    assert sorted(commands) == ["serve", "statusline"]
    assert "sekret-token-should-not-show" not in top
    assert main(["serve", "--help"]) == 0
    serve_help = _strip_ansi(capsys.readouterr().out)
    assert "--apply-preset" in serve_help
    assert "--allow-origin" in serve_help
    assert "--open" in serve_help
    assert "--enable-module" in serve_help
    assert "--disable-module" in serve_help
    assert main(["console"]) == 2  # 삭제된 명령(design §R5.2, 2R.20)
    assert main([]) in (0, 2)  # 인자 없으면 도움말
    assert main(["nope"]) == 2


def test_serve_passes_options_like_server_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, dict[str, Any], tuple[str, ...]]] = []

    def fake_run(
        config: Path | None,
        overrides: dict[str, Any],
        *,
        extra_origins: tuple[str, ...] = (),
        **_: Any,
    ) -> None:
        calls.append((config, dict(overrides), tuple(extra_origins)))

    monkeypatch.setattr(cli_app, "run_server", fake_run)
    code = main(
        [
            "serve",
            "--config",
            "x.yaml",
            "--host",
            "127.0.0.1",
            "--port",
            "9001",
            "--workspace",
            "ws",
            "--apply-preset",
            "a",
            "--apply-preset",
            "b",
            "--allow-origin",
            "http://127.0.0.1:4173",
            "--allow-origin",
            "http://localhost:4173",
        ]
    )
    assert code == 0
    assert calls == [
        (
            Path("x.yaml"),
            {
                "host": "127.0.0.1",
                "port": 9001,
                "workspace": "ws",
                "modules": {"options": {"mod-presets": {"apply_on_start": ["a", "b"]}}},
            },
            ("http://127.0.0.1:4173", "http://localhost:4173"),
        )
    ]
    assert serve_overrides(host=None, port=None, workspace=None, apply_presets=None) == {}


def test_serve_open_flag_overrides_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--open`/`--no-open`은 `web.open.enabled`만 덮어쓴다. 없으면 설정 그대로(2R.23)."""
    seen: list[dict[str, Any]] = []

    def fake_run(config: Path | None, overrides: dict[str, Any], **_: Any) -> None:
        seen.append(dict(overrides))

    monkeypatch.setattr(cli_app, "run_server", fake_run)
    assert main(["serve", "--open"]) == 0
    assert main(["serve", "--no-open"]) == 0
    assert main(["serve"]) == 0
    assert seen == [{"web": {"open": {"enabled": True}}}, {"web": {"open": {"enabled": False}}}, {}]


def test_serve_module_flags_are_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def fake_run(
        config: Path | None,
        overrides: dict[str, Any],
        *,
        enable_modules: tuple[str, ...] = (),
        disable_modules: tuple[str, ...] = (),
        **_: Any,
    ) -> None:
        seen.append((tuple(enable_modules), tuple(disable_modules)))

    monkeypatch.setattr(cli_app, "run_server", fake_run)
    argv = ["serve", "--enable-module", "a", "--disable-module", "b", "--disable-module", "c"]
    assert main(argv) == 0
    assert main(["serve"]) == 0
    assert seen == [(("a",), ("b", "c")), ((), ())]


def test_run_server_applies_module_flags_over_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_console_server

    served: list[Any] = []
    monkeypatch.setattr(agent_console_server, "serve", served.append)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENT_CONSOLE_CONFIG", raising=False)
    (tmp_path / "agent-console.yaml").write_text(
        "modules:\n  disabled: [mod-a, mod-b]\n", encoding="utf-8"
    )
    run_server(None, {}, enable_modules=["mod-a"], disable_modules=["mod-c"])
    assert served[0].modules.disabled == ["mod-b", "mod-c"]
    assert served[0].modules.enabled is None


def test_run_server_keeps_open_override_with_extra_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_console_server

    served: list[Any] = []
    monkeypatch.setattr(agent_console_server, "serve", served.append)
    monkeypatch.chdir(tmp_path)
    for name in ("CONFIG", "ALLOWED_ORIGINS", "OPEN"):
        monkeypatch.delenv(f"AGENT_CONSOLE_{name}", raising=False)
    overrides = serve_overrides(
        host=None, port=None, workspace=None, apply_presets=None, open_browser=True
    )
    run_server(None, overrides, extra_origins=["http://127.0.0.1:4173"])
    assert served[0].web.open.enabled is True
    assert served[0].security.allowed_origins == ["http://127.0.0.1:4173"]


def test_serve_config_error_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(config: Path | None, overrides: dict[str, Any], **_: Any) -> None:
        raise ServerConfigError("설정 값 오류: port")

    monkeypatch.setattr(cli_app, "run_server", broken)
    assert main(["serve"]) == 2
    assert "설정 값 오류" in capsys.readouterr().err


def test_serve_real_config_error_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "agent-console.yaml"
    bad.write_text("port: not-a-number\n", encoding="utf-8")
    assert main(["serve", "--config", str(bad)]) == 2
    assert "port" in capsys.readouterr().err


def test_removed_phase1_keys_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "agent-console.yaml"
    old.write_text("console: {command_prefix: '!'}\n", encoding="utf-8")
    assert main(["serve", "--config", str(old)]) == 2
    assert "console" in capsys.readouterr().err


# ---------------------------------------------------------------- 허용 출처 덧붙이기


def test_merge_origins_appends_without_duplicates() -> None:
    assert merge_origins(
        ["http://localhost:5173", "http://127.0.0.1:4173/"],
        ["http://127.0.0.1:4173", " ", "http://localhost:4173"],
    ) == ["http://localhost:5173", "http://127.0.0.1:4173", "http://localhost:4173"]
    assert merge_origins([], []) == []


def test_run_server_adds_origins_to_configured_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_console_server

    cfg = tmp_path / "agent-console.yaml"
    cfg.write_text(
        "security:\n  allowed_origins: [http://localhost:5173]\n  max_ws_subscriptions: 7\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_CONSOLE_ALLOWED_ORIGINS", raising=False)
    seen: list[Any] = []
    monkeypatch.setattr(agent_console_server, "serve", seen.append)
    run_server(cfg, {"port": 9002}, extra_origins=["http://127.0.0.1:4173"])
    (settings,) = seen
    assert settings.port == 9002
    assert settings.security.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:4173"]
    assert settings.security.max_ws_subscriptions == 7  # 다른 보안 값은 그대로
    seen.clear()
    run_server(cfg, {})
    assert seen[0].security.allowed_origins == ["http://localhost:5173"]


# ---------------------------------------------------------------- 시작 시간


def test_import_does_not_load_heavy_packages() -> None:
    """`statusline`은 상태 줄을 그릴 때마다 실행된다.

    서버·입력 라이브러리를 import하지 않는다.
    """
    code = (
        "import json, sys, agent_console_cli; "
        "print(json.dumps(sorted(m for m in sys.modules if '.' not in m)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = set(json.loads(result.stdout))
    heavy = {
        "agent_console_server",
        "agent_console_runtime",
        "agent_console_contracts",
        "pydantic",
        "prompt_toolkit",
        "fastapi",
        "uvicorn",
        "sqlalchemy",
    }
    assert loaded.isdisjoint(heavy), sorted(loaded & heavy)
