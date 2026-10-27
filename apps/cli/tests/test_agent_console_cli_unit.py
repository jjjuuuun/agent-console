"""agent-console-cli 단위 테스트: 노출 명령·serve 위임(서버 `main`)·시작 시 import 범위.

`logs purge`는 `test_agent_console_cli_logs_purge.py`.
"""

from __future__ import annotations

import functools
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
import agent_console_server
import agent_console_server._app as server_app
from agent_console_cli import main
from agent_console_modkit import FlagSetting, ModuleDescriptor, ModuleParts, SettingsCompat

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


def test_only_serve_statusline_and_logs_are_exposed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _plain_help_env(monkeypatch)
    monkeypatch.setenv("AGENT_CONSOLE_TOKEN", "sekret-token-should-not-show")
    assert main(["--help"]) == 0
    top = _strip_ansi(capsys.readouterr().out)
    assert "serve" in top
    assert "statusline" in top
    commands: dict[str, object] = getattr(typer.main.get_command(cli_app.app), "commands", {})
    assert sorted(commands) == ["logs", "serve", "statusline"]
    assert "logs" in top
    assert "sekret-token-should-not-show" not in top
    assert main(["serve", "--help"]) == 0
    serve_help = _strip_ansi(capsys.readouterr().out)
    assert "agent-console serve" in serve_help
    assert "--allow-origin" in serve_help
    assert "--open" in serve_help
    assert "--enable-module" in serve_help
    assert "--disable-module" in serve_help
    assert main([]) in (0, 2)  # 인자 없으면 도움말
    assert main(["nope"]) == 2


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """서버 `serve`를 가로채 받은 설정을 모은다(현재 폴더·환경변수 설정은 비운다)."""
    seen: list[Any] = []

    def fake_serve(settings: Any, **_: Any) -> None:
        seen.append(settings)

    monkeypatch.setattr(server_app, "serve", fake_serve)
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("AGENT_CONSOLE_"):
            monkeypatch.delenv(name)
    return seen


def test_serve_passes_options_to_server_main(served: list[Any]) -> None:
    code = main(
        [
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "9001",
            "--workspace",
            "ws",
            "--allow-origin",
            "http://127.0.0.1:4173",
            "--allow-origin",
            "http://localhost:4173",
        ]
    )
    assert code == 0
    (settings,) = served
    assert (settings.host, settings.port) == ("127.0.0.1", 9001)
    assert settings.workspace.name == "ws"
    assert settings.security.allowed_origins == ["http://127.0.0.1:4173", "http://localhost:4173"]


def test_serve_open_flag_overrides_setting(served: list[Any]) -> None:
    """`--open`/`--no-open`은 `web.open.enabled`만 덮어쓴다. 없으면 설정 그대로(2R.23)."""
    assert main(["serve", "--open"]) == 0
    assert main(["serve", "--no-open"]) == 0
    assert main(["serve"]) == 0
    assert [s.web.open.enabled for s in served] == [True, False, False]


def test_serve_module_flags_win_over_config(tmp_path: Path, served: list[Any]) -> None:
    (tmp_path / "agent-console.yaml").write_text(
        "modules:\n  disabled: [mod-a, mod-b]\n", encoding="utf-8"
    )
    argv = ["serve", "--enable-module", "mod-a", "--disable-module", "mod-c"]
    assert main(argv) == 0
    assert served[0].modules.disabled == ["mod-b", "mod-c"]
    assert served[0].modules.enabled is None


def test_serve_allow_origin_appends_to_configured_list(tmp_path: Path, served: list[Any]) -> None:
    cfg = tmp_path / "agent-console.yaml"
    cfg.write_text(
        "security:\n  allowed_origins: [http://localhost:5173]\n  max_ws_subscriptions: 7\n",
        encoding="utf-8",
    )
    argv = ["serve", "-c", str(cfg), "--port", "9002", "--open"]
    assert main([*argv, "--allow-origin", "http://127.0.0.1:4173"]) == 0
    assert main(["serve", "--config", str(cfg)]) == 0
    first, plain = served
    assert first.port == 9002
    assert first.web.open.enabled is True  # 출처를 더해도 다른 덮어쓰기는 그대로
    assert first.security.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:4173"]
    assert first.security.max_ws_subscriptions == 7  # 다른 보안 값은 그대로
    assert plain.security.allowed_origins == ["http://localhost:5173"]


class _FlagModule:
    """명령행 옵션 `--demo-value`를 선언한 예제 모듈(R0.3: 서버·CLI가 이름을 모른다)."""

    descriptor = ModuleDescriptor(
        id="mod-flag-demo",
        version="0.0.1",
        kind="feature",
        title="Flag demo",
        settings_compat=SettingsCompat(
            flags=(
                FlagSetting("demo-value", ("values",), help="예제 값", metavar="TEXT", repeat=True),
            )
        ),
    )

    def build(self, ctx: Any) -> ModuleParts:
        return ModuleParts()


def test_module_declared_flag_reaches_serve(
    served: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """모듈이 `SettingsCompat.flags`로 선언한 옵션은 하드코딩 없이 도움말과 실행에 나온다."""
    _plain_help_env(monkeypatch)
    real = agent_console_server.main
    monkeypatch.setattr(
        agent_console_server, "main", functools.partial(real, modules=[_FlagModule()])
    )
    assert main(["serve", "--help"]) == 0
    help_text = _strip_ansi(capsys.readouterr().out)
    assert "--demo-value" in help_text
    assert "mod-flag-demo" in help_text
    assert main(["serve", "--demo-value", "x", "--demo-value", "y"]) == 0
    assert served[0].modules.options["mod-flag-demo"]["values"] == ["x", "y"]


def test_serve_config_error_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "agent-console.yaml"
    bad.write_text("port: not-a-number\n", encoding="utf-8")
    assert main(["serve", "--config", str(bad)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("agent-console serve:")
    assert "port" in err


def test_removed_phase1_keys_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "agent-console.yaml"
    old.write_text("console: {command_prefix: '!'}\n", encoding="utf-8")
    assert main(["serve", "--config", str(old)]) == 2
    assert "console" in capsys.readouterr().err


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


def test_statusline_run_does_not_load_server(tmp_path: Path) -> None:
    """`statusline` 실행 전체(import + 명령)에서 서버·FastAPI를 import하지 않는다."""
    out = tmp_path / "bridge.json"
    code = (
        "import json, sys, agent_console_cli\n"
        "try:\n"
        f"    agent_console_cli.main(['statusline', '--output', {str(out)!r}])\n"
        "finally:\n"
        "    names = sorted(m for m in sys.modules if '.' not in m)\n"
        "    print(json.dumps(names), file=sys.stderr)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        input='{"rate_limits": {}}',
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = set(json.loads(result.stderr.strip().splitlines()[-1]))
    assert "agent_console_cli" in loaded
    assert loaded.isdisjoint({"agent_console_server", "fastapi", "uvicorn"})
