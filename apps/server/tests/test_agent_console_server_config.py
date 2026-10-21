"""설정 로드(`agent-console.yaml` + 환경변수 + 명령행 덮어쓰기)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_server import (
    CONFIG_FILENAME,
    SETTINGS_REMOVED_KEY,
    ConfigError,
    is_loopback_host,
    load_settings,
)

YAML = """\
port: 9000
workspace: data/ws
plugins:
  enabled: [input, output]
  modules: [my_pkg.plugin:register]
security:
  token: from-file-token
  allowed_origins: ["http://localhost:5173"]
modules:
  options:
    mod-presets:
      directories: [presets, /abs/presets]
      apply_on_start: [dev-team]
    mod-runs:
      backends:
        claude-agent-sdk:
          models: [{id: m1}]
"""


def test_agent_console_server_settings_defaults(tmp_path: Path) -> None:
    settings = load_settings(environ={}, cwd=tmp_path)
    assert settings.host == "127.0.0.1"
    assert settings.is_loopback
    assert settings.workspace_path == tmp_path / ".agent-console"
    assert settings.database_path == tmp_path / ".agent-console" / ".state" / "console.sqlite3"
    assert settings.modules.options == {}
    assert settings.moved_keys == []
    assert settings.plugins.enabled is None
    assert settings.security.token is None


def test_agent_console_server_settings_file_and_env(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(YAML, encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    settings = load_settings(environ={}, cwd=tmp_path)
    assert settings.port == 9000
    assert settings.workspace_path == tmp_path / "data" / "ws"  # 설정 파일 폴더 기준
    # 모듈 설정은 modules.options 아래. 상대 경로는 모듈이 base_dir(설정 파일 폴더) 기준으로 푼다.
    presets = settings.modules.options["mod-presets"]
    assert presets == {"directories": ["presets", "/abs/presets"], "apply_on_start": ["dev-team"]}
    assert settings.base_dir == tmp_path
    assert settings.moved_keys == []
    assert settings.plugins.enabled == ["input", "output"]
    runs = settings.modules.options["mod-runs"]
    assert runs["backends"]["claude-agent-sdk"]["models"] == [{"id": "m1"}]
    assert settings.security.token is not None
    assert "from-file-token" not in repr(settings)  # SecretStr

    env = {
        "AGENT_CONSOLE_CONFIG": str(tmp_path / CONFIG_FILENAME),
        "AGENT_CONSOLE_PORT": "9100",
        "AGENT_CONSOLE_PLUGINS_ENABLED": "input, router",
        "AGENT_CONSOLE_PRESET_DIRS": os.pathsep.join(["p1", "p2"]),
        "AGENT_CONSOLE_ALLOW_REMOTE": "true",
        "AGENT_CONSOLE_HOST": "",  # 빈 값은 무시
    }
    from_env = load_settings(environ=env, cwd=other)
    assert from_env.port == 9100
    assert from_env.host == "127.0.0.1"
    assert from_env.plugins.enabled == ["input", "router"]
    assert from_env.modules.options["mod-presets"]["directories"] == ["p1", "p2"]  # 환경변수가 이김
    assert from_env.security.allow_remote is True
    assert from_env.security.allowed_origins == ["http://localhost:5173"]  # 파일 값 유지

    cli = load_settings(environ=env, cwd=other, overrides={"port": 9200})
    assert cli.port == 9200


def test_agent_console_server_settings_errors_hide_values(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(environ={"AGENT_CONSOLE_PORT": "not-a-port-secretish"}, cwd=tmp_path)
    assert "port" in str(exc.value)
    assert "secretish" not in str(exc.value)
    (tmp_path / "bad.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "bad.yaml", environ={})
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.yaml", environ={})
    with pytest.raises(ConfigError):
        load_settings(environ={}, cwd=tmp_path, overrides={"unknown_key": 1})


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.0.10", False),
        ("example.com", False),
    ],
)
def test_agent_console_server_loopback(host: str, expected: bool) -> None:
    assert is_loopback_host(host) is expected


def test_removed_keys_are_rejected_with_reason(tmp_path: Path) -> None:
    """1R에서 삭제한 키(console, default_manual_route_pattern)는 이유가 담긴 오류로 거부한다."""
    for key, value in (("console", {"buffer_size": 1}), ("default_manual_route_pattern", "x")):
        config = tmp_path / f"{key}.yaml"
        config.write_text(
            f"{key}: {value!r}\n" if isinstance(value, str) else f"{key}: {{buffer_size: 1}}\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="1R에서 삭제") as exc:
            load_settings(config, environ={})
        assert key in str(exc.value)
        # 지운 키는 코드 settings.removed_key로 나오고, pydantic 접두어·빈 위치가 없다(1R.26).
        assert exc.value.code == SETTINGS_REMOVED_KEY
        assert str(exc.value).startswith(f"설정 값 오류({SETTINGS_REMOVED_KEY}): {key}: ")
        assert "Value error" not in str(exc.value)
        assert ": :" not in str(exc.value)


def test_old_presets_with_set_default_entry_points_to_new_location(tmp_path: Path) -> None:
    """2R.20에서 지운 `presets.set_default_entry`도 4R.18부터는 옛 최상위 `presets`로 안내한다."""
    config = tmp_path / "agent-console.yaml"
    config.write_text("presets:\n  set_default_entry: false\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"modules\.options\.mod-presets") as exc:
        load_settings(config, environ={})
    assert [k.old for k in exc.value.removed] == ["presets"]
    # 같은 이름이 모듈 설정 아래에 있는 것은 상관없다(경로 단위 검사, 모듈 스키마가 검증).
    other = tmp_path / "other.yaml"
    other.write_text(
        "modules:\n  options:\n    mod-runs: {backends: {fake: {set_default_entry: true}}}\n",
        encoding="utf-8",
    )
    load_settings(other, environ={})


def test_runs_keys_are_rejected_and_env_goes_to_mod_runs(tmp_path: Path) -> None:
    """4R.18: 옛 `runtime`·`backends`·`working_directory`는 새 위치를 알려 주는 오류다.
    환경변수는 `modules.options.mod-runs`로 들어간다. 가져오기 project_dir는 따라가지 않는다(H3)."""
    config = tmp_path / "agent-console.yaml"
    config.write_text("runtime: {shutdown_timeout: 3}\nworking_directory: proj\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(config, environ={})
    assert [(k.old, k.new) for k in exc.value.removed] == [
        ("runtime", "modules.options.mod-runs.runtime"),
        ("working_directory", "modules.options.mod-runs.working_directory"),
    ]
    config.write_text(
        "secrets: {min_redact_chars: 6}\n"
        "modules:\n  options:\n    mod-runs: {working_directory: proj}\n",
        encoding="utf-8",
    )
    settings = load_settings(config, environ={})
    runs = settings.modules.options["mod-runs"]
    assert runs["working_directory"] == "proj"
    assert runs["min_redact_chars"] == 6  # 호스트 secrets.*에서 넘긴 기본값
    assert "project_dir" not in settings.modules.options.get("mod-imports", {})

    env = {
        "AGENT_CONSOLE_WORKING_DIRECTORY": "from-env",
        "AGENT_CONSOLE_MAX_CONCURRENCY": "3",
    }
    from_env = load_settings(environ=env, cwd=tmp_path / "nowhere")
    runs = from_env.modules.options["mod-runs"]
    assert runs["working_directory"] == "from-env"
    assert runs["runtime"] == {"max_concurrency": "3"}
    assert from_env.moved_keys == []
    assert "project_dir" not in from_env.modules.options.get("mod-imports", {})
