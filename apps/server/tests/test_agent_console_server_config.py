"""설정 로드(`agent-console.yaml` + 환경변수 + 명령행 덮어쓰기)."""

from __future__ import annotations

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
    mod-imports:
      project_dir: proj
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
    assert settings.modules.options["mod-imports"] == {"project_dir": "proj"}
    assert settings.base_dir == tmp_path
    assert settings.plugins.enabled == ["input", "output"]
    runs = settings.modules.options["mod-runs"]
    assert runs["backends"]["claude-agent-sdk"]["models"] == [{"id": "m1"}]
    assert settings.security.token is not None
    assert "from-file-token" not in repr(settings)  # SecretStr

    env = {
        "AGENT_CONSOLE_CONFIG": str(tmp_path / CONFIG_FILENAME),
        "AGENT_CONSOLE_PORT": "9100",
        "AGENT_CONSOLE_PLUGINS_ENABLED": "input, router",
        "AGENT_CONSOLE_WORKING_DIRECTORY": "from-env",
        "AGENT_CONSOLE_ALLOW_REMOTE": "true",
        "AGENT_CONSOLE_HOST": "",  # 빈 값은 무시
    }
    from_env = load_settings(environ=env, cwd=other)
    assert from_env.port == 9100
    assert from_env.host == "127.0.0.1"
    assert from_env.plugins.enabled == ["input", "router"]
    assert from_env.modules.options["mod-runs"]["working_directory"] == "from-env"  # 모듈 환경변수
    assert from_env.modules.options["mod-imports"] == {"project_dir": "proj"}  # 파일 값 유지
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


def test_unknown_top_level_key_is_a_plain_config_error(tmp_path: Path) -> None:
    """선언된 지운 키가 아닌 옛 키(예: `console`)는 일반 설정 오류로 시작을 거부한다."""
    config = tmp_path / "agent-console.yaml"
    config.write_text("console: {buffer_size: 1}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_settings(config, environ={})
    assert exc.value.code is None
    assert exc.value.removed == []
    assert "console" in str(exc.value)


def test_removed_preset_keys_are_rejected(tmp_path: Path) -> None:
    """삭제된 프리셋 기능의 설정(`presets`, `modules.options.mod-presets`)은 이유가 담긴 오류다."""
    for name, body in (
        ("top", "presets:\n  directories: [p]\n"),
        ("module", "modules:\n  options:\n    mod-presets: {apply_on_start: [x]}\n"),
    ):
        config = tmp_path / f"{name}.yaml"
        config.write_text(body, encoding="utf-8")
        with pytest.raises(ConfigError, match="프리셋 기능은 삭제되었습니다") as exc:
            load_settings(config, environ={})
        assert exc.value.code == SETTINGS_REMOVED_KEY
        [key] = exc.value.removed
        assert key.new is None
        assert str(exc.value).startswith(f"설정 값 오류({SETTINGS_REMOVED_KEY}): {key.old}: ")
        assert "Value error" not in str(exc.value)
    # 같은 이름이 다른 모듈 설정 아래에 있는 것은 상관없다(경로 단위 검사, 모듈 스키마가 검증).
    other = tmp_path / "other.yaml"
    other.write_text(
        "modules:\n  options:\n    mod-runs: {backends: {fake: {presets: true}}}\n",
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
    assert "project_dir" not in from_env.modules.options.get("mod-imports", {})
