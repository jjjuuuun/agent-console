"""저장소 루트 `agent-console.example.yaml`이 서버를 그대로 띄우는지(1R.15, 저장소 통합 검사).

3R.3에서 apps/cli 테스트에서 옮겼다(앱 테스트는 저장소의 다른 파일을 보지 않는다).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "agent-console.example.yaml"


def test_example_config_boots_server(tmp_path: Path) -> None:
    """루트 `agent-console.example.yaml`이 서버 설정·백엔드 설치자 설정으로 그대로 통과한다."""
    from fastapi.testclient import TestClient

    from agent_console_server import create_app, load_settings

    settings = load_settings(
        EXAMPLE_CONFIG, environ={}, overrides={"workspace": str(tmp_path / "ws")}
    )
    assert "http://127.0.0.1:4173" in settings.security.allowed_origins
    assert settings.modules.options["mod-presets"]["directories"] == []
    assert settings.moved_keys == []  # 예시는 새 위치만 쓴다(settings.moved_key 경고 없음)
    assert settings.modules.options["mod-runs"]["backends"]["fake"]["rate_limits"]
    app = create_app(settings, environ={}, token="t")
    with TestClient(app, base_url=f"http://127.0.0.1:{settings.port}") as client:
        models = client.get("/api/v1/backends/fake/models").json()
        assert [m["id"] for m in models] == ["fake-small"]
        statuses = {m["id"]: m["status"] for m in client.get("/api/v1/modules").json()}
        assert all(state == "active" for state in statuses.values()), statuses
        assert client.get("/api/v1/presets").json() == []  # 공개본에는 프리셋 데이터가 없다
        allowed = client.options(
            "/api/v1/agents",
            headers={
                "Origin": "http://127.0.0.1:4173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:4173"


def test_example_config_documents_log_and_probe_options() -> None:
    """5R.19: 예시가 로그 연동·hook probe 옵션을 새 위치에 담고, 그 값으로 모듈이 모두 켜진다."""
    from agent_console_server import load_settings

    settings = load_settings(EXAMPLE_CONFIG, environ={})
    options = settings.modules.options
    assert options["link-logs-runs"]["debounce_seconds"] == 1.0
    assert options["link-logs-usage"]["source_id"] == "local-logs"
    assert options["link-logs-trace"]["link_keys"] == ["tool_use_id"]
    sdk = options["mod-runs"]["backends"]["claude-agent-sdk"]
    assert sdk["hook_probe_folder"] == "hook-probe"
    assert sdk["hook_probe_command"] is None


def test_static_dir_relative_paths_follow_config_folder(tmp_path: Path) -> None:
    """5R.19: `web.static_dir`·`AGENT_CONSOLE_WEB_DIR` 상대 경로는 설정 파일 폴더 기준.

    apps/server README "단일 실행"의 안내와 같다.
    """
    from agent_console_server import load_settings

    from_file = load_settings(EXAMPLE_CONFIG, environ={}, cwd=tmp_path)
    assert from_file.static_path == REPO_ROOT / "apps" / "web" / "dist"

    config = tmp_path / "elsewhere" / "agent-console.yaml"
    config.parent.mkdir()
    config.write_text("port: 8765\n", encoding="utf-8")
    from_env = load_settings(
        config, environ={"AGENT_CONSOLE_WEB_DIR": "apps/web/dist"}, cwd=REPO_ROOT
    )
    assert from_env.static_path == config.parent / "apps" / "web" / "dist"
    absolute = tmp_path / "build"
    from_abs = load_settings(config, environ={"AGENT_CONSOLE_WEB_DIR": str(absolute)})
    assert from_abs.static_path == absolute
