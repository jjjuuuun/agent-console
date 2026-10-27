"""3R.16 QA: 모듈 환경변수가 서버 설정까지 이어진다(옛 최상위 키는 오류, 4R.18).

모듈 명령행 옵션은 모듈이 선언한 것만 받는다(선언한 모듈이 없으면 설정 오류).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_server import ConfigError, flag_overrides, load_settings


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agent-console.yaml"
    path.write_text(
        f"base_dir: {tmp_path}\nworkspace: ws\nsecurity: {{allowed_hosts: [testserver]}}\n{body}",
        encoding="utf-8",
    )
    return path


def test_undeclared_module_flag_is_config_error() -> None:
    """삭제된 프리셋 모듈의 `--apply-preset`처럼 선언한 모듈이 없는 옵션은 설정 오류다."""
    with pytest.raises(ConfigError, match="apply-preset"):
        flag_overrides({"apply-preset": ["x"]})
    assert flag_overrides({}) == {}


def test_old_runtime_keys_rejected_and_env_reach_runs_module(tmp_path: Path) -> None:
    old = _config(tmp_path, "runtime: {max_concurrency: 2}\nworking_directory: proj\n")
    with pytest.raises(ConfigError) as exc:
        load_settings(old, cwd=tmp_path, environ={})
    assert {k.old for k in exc.value.removed} == {"runtime", "working_directory"}
    cfg = _config(
        tmp_path,
        "modules:\n  options:\n"
        "    mod-runs: {runtime: {max_concurrency: 2}, working_directory: proj}\n",
    )
    settings = load_settings(cfg, cwd=tmp_path, environ={})
    runs = settings.modules.options["mod-runs"]
    assert runs["runtime"]["max_concurrency"] == 2
    assert runs["working_directory"] == "proj"
    env = {"AGENT_CONSOLE_MAX_CONCURRENCY": "4", "AGENT_CONSOLE_WORKING_DIRECTORY": "e"}
    s2 = load_settings(cfg, cwd=tmp_path, environ=env)
    assert s2.modules.options["mod-runs"]["working_directory"] == "e"
    assert str(s2.modules.options["mod-runs"]["runtime"]["max_concurrency"]) == "4"
