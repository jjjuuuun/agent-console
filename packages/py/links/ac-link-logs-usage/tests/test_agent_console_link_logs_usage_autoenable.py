"""5.2R.27: 이 PC에 Claude Code 로그가 있으면 로그 출처를 읽기 전용 기본으로 켜고, 첫 GET /usage에
local-logs 값이 나온다. 설정 파일 무변경·명시 끔 존중·모듈 끄기·가짜 홈 해시 불변.

실제 ``~/.claude``는 쓰지 않는다. 가짜 홈(tmp_path)에 Claude Code 형식 로그를 만든다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_link_logs_usage import (
    AutoLogSource,
    load_auto_log_sources,
    log_source_defaults,
    module,
)
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_mod_usage import module as usage_module
from agent_console_modkit import BaseServices, Module, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

H0 = 1_800_000_000.0
NOW = datetime.fromtimestamp(H0 + 3600.0, tz=UTC)
TOKEN = "t" * 32
CLAUDE_SOURCE = "claude-code-jsonl"


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _assistant(mid: str, t: float, tokens: int) -> dict[str, Any]:
    return {
        "sessionId": "s-1",
        "cwd": "/work/demo",
        "type": "assistant",
        "uuid": f"u-{mid}-{t}",
        "timestamp": _iso(t),
        "message": {
            "id": mid,
            "type": "message",
            "role": "assistant",
            "model": "claude-test-model",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": tokens, "output_tokens": 1},
        },
    }


def _fake_home(tmp_path: Path) -> Path:
    """가짜 홈: ``~/.claude/projects/<프로젝트>/<세션>.jsonl``.

    같은 message.id 두 행은 한 번만 센다.
    """
    home = tmp_path / "home"
    project = home / ".claude" / "projects" / "-work-demo"
    project.mkdir(parents=True)
    rows = [_assistant("m1", H0 + 600, 40), _assistant("m1", H0 + 601, 40)]
    rows.append(_assistant("m2", H0 + 900, 9))
    (project / "s-1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    return home


def _tree_digest(root: Path) -> str:
    """폴더 아래 모든 파일의 경로·내용·수정 시각 해시(쓰기·이동·삭제 감지)."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        h.update(str(path.relative_to(root)).encode())
        if path.is_file():
            h.update(path.read_bytes())
            h.update(str(path.stat().st_mtime_ns).encode())
    return h.hexdigest()


def _client(
    tmp_path: Path,
    home: Path,
    *,
    settings: WorkspaceSettings | None = None,
    disabled: Sequence[str] = (),
) -> TestClient:
    paths = Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    base = BaseServices(clock=lambda: NOW, paths=paths, environ={"HOME": str(home)})
    stack: list[Module] = [
        logs_module,
        usage_module,
        static_settings_module(settings or WorkspaceSettings()),
        module,
    ]
    assembly = assemble(stack, ModulesConfig(disabled=list(disabled)), base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _local(body: dict[str, Any]) -> dict[str, Any]:
    return {w["window"]: w for w in body["windows"] if w["source"] == "local-logs"}


def _log_source(client: TestClient) -> dict[str, Any]:
    sources = client.get("/api/v1/logs/sources").json()
    [found] = [s for s in sources if s["descriptor"]["id"] == CLAUDE_SOURCE]
    return dict(found)


# ---------------------------------------------------------------- 순수 함수


def test_package_rules_are_data() -> None:
    [rule] = load_auto_log_sources()
    assert rule.id == CLAUDE_SOURCE
    assert rule.path == "~/.claude/projects"


def test_defaults_follow_folder_existence_and_env(tmp_path: Path) -> None:
    rule = AutoLogSource(id="x", path="~/.claude/projects", env="CFG", env_subpath="projects")
    assert log_source_defaults([rule], {"HOME": str(tmp_path)}) == {}
    (tmp_path / ".claude" / "projects").mkdir(parents=True)
    assert log_source_defaults([rule], {"HOME": str(tmp_path)}) == {"x": True}
    # 환경 변수가 있으면 그 아래만 본다(출처의 기본 루트 규칙과 같다)
    other = tmp_path / "other"
    assert log_source_defaults([rule], {"HOME": str(tmp_path), "CFG": str(other)}) == {}
    (other / "projects").mkdir(parents=True)
    assert log_source_defaults([rule], {"HOME": str(tmp_path), "CFG": str(other)}) == {"x": True}
    # 홈을 모르면 작업 폴더 기준 상대 경로로 보지 않는다
    assert log_source_defaults([rule], {}) == {}


def test_rules_file_must_have_ids(tmp_path: Path) -> None:
    bad = tmp_path / "rules.json"
    bad.write_text(json.dumps({"log_sources": [{"path": "~/x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="id"):
        load_auto_log_sources(bad)


# ---------------------------------------------------------------- 서버 조립


def test_first_usage_response_has_local_logs_without_settings(tmp_path: Path) -> None:
    home = _fake_home(tmp_path)
    before = _tree_digest(home / ".claude")
    with _client(tmp_path, home) as client:
        # 설정이 비어 있어도 첫 응답에 로컬 로그 추정 값이 있다(첫 조회가 시작 수집을 기다림)
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        local = _local(body)
        assert local["local_five_hour"]["used_tokens"] == 51  # m1(41) 한 번 + m2(10)
        assert local["local_seven_day"]["used_tokens"] == 51
        info = _log_source(client)
        assert info["enabled"] is True
        assert (
            info["descriptor"]["default_enabled"] is False
        )  # 기본(자동) 켜짐 = 디스크립터 기본과 다름
        sources = {s["descriptor"]["id"]: s for s in client.get("/api/v1/usage/sources").json()}
        assert sources["local-logs"]["enabled"] is True
        assert sources["local-logs"]["descriptor"]["auto_enable"] is True
        titles = {w["id"]: w["title"] for w in sources["local-logs"]["descriptor"]["windows"]}
        assert titles["local_five_hour"] == "5시간(로그 추정)"
    # 원본은 읽기 전용: 가짜 ~/.claude는 그대로, 설정 파일은 만들지 않는다
    assert _tree_digest(home / ".claude") == before
    assert not (tmp_path / "ws").exists() or not any((tmp_path / "ws").rglob("settings*"))


def test_user_explicit_off_is_respected(tmp_path: Path) -> None:
    home = _fake_home(tmp_path)
    settings = WorkspaceSettings.model_validate(
        {"logs": {"sources": [{"id": CLAUDE_SOURCE, "enabled": False}]}}
    )
    with _client(tmp_path, home, settings=settings) as client:
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        assert _local(body) == {}
        assert _log_source(client)["enabled"] is False


def test_no_claude_folder_means_no_auto_enable(tmp_path: Path) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    with _client(tmp_path, home) as client:
        assert _log_source(client)["enabled"] is False
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        assert _local(body) == {}


@pytest.mark.parametrize("off", ["link-logs-usage", "mod-usage"])
def test_turning_off_link_or_usage_removes_auto_enable(tmp_path: Path, off: str) -> None:
    home = _fake_home(tmp_path)
    with _client(tmp_path, home, disabled=[off]) as client:
        assert _log_source(client)["enabled"] is False


def test_turning_off_mod_logs_turns_off_link(tmp_path: Path) -> None:
    home = _fake_home(tmp_path)
    with _client(tmp_path, home, disabled=["mod-logs"]) as client:
        sources = {s["descriptor"]["id"] for s in client.get("/api/v1/usage/sources").json()}
        assert "local-logs" not in sources
        assert client.get("/api/v1/logs/sources").status_code == 404


def test_installer_option_turns_auto_enable_off(tmp_path: Path) -> None:
    home = _fake_home(tmp_path)
    paths = Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    base = BaseServices(clock=lambda: NOW, paths=paths, environ={"HOME": str(home)})
    assembly = assemble(
        [logs_module, usage_module, static_settings_module(WorkspaceSettings()), module],
        ModulesConfig(options={"link-logs-usage": {"auto_enable_log_sources": False}}),
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert _log_source(client)["enabled"] is False
